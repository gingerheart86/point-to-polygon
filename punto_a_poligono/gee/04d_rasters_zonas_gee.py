"""Descarga de Google Earth Engine los rásters de Sentinel-2 de las zonas analizadas, para ver
debajo de los polígonos cómo se decidió cada chacra.

Entrada (carpeta, GeoJSON EPSG:4326):
  - puntos.geojson   puntos de las chacras (campo "id")
  - zonas.geojson    zonas de búsqueda (campo "id"), una por punto
  - grupos.geojson   zonas unidas en grupos que se tocan (campo "grupo"): se exporta una
                     imagen por grupo, no una por zona, para no repetir el mismo terreno

Salida (carpeta), GeoTIFF en EPSG:32721 a 10 m:
  - g<N>_ndvi.tif       NDVI por período (una banda por período de DIAS_PERIODO días)
  - g<N>_rgb.tif        color real (B4, B3, B2), mediana del período de mayor NDVI
  - g<N>_nir_swir.tif   falso color para agricultura R:B08 G:B11 B:B02 (Byte)
  - g<N>_lluvia.tif     lluvia acumulada del período, CHIRPS v3 (mm)
  - g<N>_lst.tif        temperatura de superficie media, Landsat 8/9 ST_B10, 30 m (°C)
  - g<N>_era5.tif       temperatura de piel media, ERA5-Land (°C)
  - dist_<id>.tif       distancia (RMS de NDVI) al perfil de la semilla de cada punto, en su zona
  - fechas.txt          fecha de inicio de cada período (una por línea)

Uso (python con earthengine-api y requests):
    python 04d_rasters_zonas_gee.py <carpeta_entrada> <carpeta_salida> <inicio> <fin> [proyecto_gee]
"""
import importlib.util
import json
import os
import sys

import ee
import requests

_spec = importlib.util.spec_from_file_location(
    "seg", os.path.join(os.path.dirname(os.path.abspath(__file__)), "04_segmentar_s2_gee.py"))
seg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seg)
_spec_c = importlib.util.spec_from_file_location(
    "clima", os.path.join(os.path.dirname(os.path.abspath(__file__)), "04e_clima_chacras_gee.py"))
clima = importlib.util.module_from_spec(_spec_c)
_spec_c.loader.exec_module(clima)

CRS = "EPSG:32721"


def descargar(img, region, ruta, escala=10):
    for esc in (escala, escala * 2, escala * 4):  # si la zona es muy grande, baja la resolución
        try:
            url = img.getDownloadURL({"region": region, "scale": esc, "crs": CRS, "format": "GEO_TIFF"})
            r = requests.get(url, timeout=900)
            r.raise_for_status()
            with open(ruta, "wb") as fh:
                fh.write(r.content)
            print(f"  {os.path.basename(ruta)}: {len(r.content) / 1e6:.1f} MB a {esc} m", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            print(f"  {os.path.basename(ruta)} a {esc} m falló ({str(e)[:120]}); reintento más grueso", flush=True)
    raise RuntimeError(f"No se pudo descargar {ruta}")


def s2_mediana(zona, d0, d1):
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(zona).filterDate(d0, d1)
            .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs_cdf"])
            .map(lambda im: im.updateMask(im.select("cs_cdf").gte(seg.UMBRAL_CS))).median())


def main(carpeta, salida, inicio, fin, proyecto=None):
    ee.Initialize(project=proyecto)

    def leer(n):
        with open(os.path.join(carpeta, n), encoding="utf-8") as f:
            return json.load(f)["features"]

    puntos = {f["properties"]["id"]: f["geometry"] for f in leer("puntos.geojson")}
    zonas = {f["properties"]["id"]: f["geometry"] for f in leer("zonas.geojson")}
    grupos = [(f["properties"]["grupo"], f["geometry"]) for f in leer("grupos.geojson")]
    os.makedirs(salida, exist_ok=True)

    n = None
    for g, geom in grupos:
        zona = ee.Geometry(geom)
        region = zona.bounds(1)
        print(f"grupo {g}", flush=True)
        col, _ = seg.coleccion_ndvi(zona, inicio, fin)
        stack = seg.stack_temporal(col, inicio, fin)
        if n is None:
            n = stack.bandNames().size().getInfo()
            fechas = [ee.Date(inicio).advance(i * seg.DIAS_PERIODO, "day").format("YYYY-MM-dd").getInfo()
                      for i in range(n)]
            with open(os.path.join(salida, "fechas.txt"), "w") as fh:
                fh.write("\n".join(fechas))
        descargar(stack.toFloat(), region, os.path.join(salida, f"g{g}_ndvi.tif"))
        # período de mayor NDVI medio en el grupo → color real y falsos colores
        medias = stack.reduceRegion(ee.Reducer.mean(), zona, 60, maxPixels=1e9, bestEffort=True).getInfo()
        nombres = stack.bandNames().getInfo()
        i_max = max(range(n), key=lambda i: medias.get(nombres[i]) or -1)
        d0 = ee.Date(inicio).advance(i_max * seg.DIAS_PERIODO, "day")
        med = s2_mediana(zona, d0, d0.advance(seg.DIAS_PERIODO, "day"))
        descargar(med.select(["B4", "B3", "B2"]).divide(2500).multiply(255).clamp(1, 255).toByte(), region,
                  os.path.join(salida, f"g{g}_rgb.tif"))
        for nombre, bandas in (("nir_swir", [("B8", 5000), ("B11", 5000), ("B2", 2000)]),):
            img = ee.Image.cat([med.select(b).divide(mx).multiply(255).clamp(1, 255) for b, mx in bandas]).toByte()
            descargar(img, region, os.path.join(salida, f"g{g}_{nombre}.tif"))
        # lluvia y temperatura del período
        chirps = (ee.ImageCollection("UCSB-CHC/CHIRPS/V3/DAILY_SAT").filterDate(inicio, fin).filterBounds(zona)
                  .select("precipitation"))
        descargar(chirps.sum().toFloat(), region, os.path.join(salida, f"g{g}_lluvia.tif"), escala=100)
        lst = clima.lst_landsat(zona, inicio, fin)
        descargar(lst.mean().toFloat(), region, os.path.join(salida, f"g{g}_lst.tif"), escala=30)
        era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(inicio, fin).filterBounds(zona)
        descargar(era5.select("skin_temperature").mean().subtract(clima.K).toFloat(), region,
                  os.path.join(salida, f"g{g}_era5.tif"), escala=500)

    for pid, gp in puntos.items():
        zona = ee.Geometry(zonas[pid])
        col, _ = seg.coleccion_ndvi(zona, inicio, fin)
        stack = seg.stack_temporal(col, inicio, fin)
        semilla = stack.reduceRegion(ee.Reducer.mean(), ee.Geometry(gp).buffer(seg.RADIO_SEMILLA), seg.ESCALA)
        perfil = ee.Image.constant(stack.bandNames().map(lambda b: semilla.get(b))).rename(stack.bandNames())
        dist = stack.subtract(perfil).pow(2).reduce(ee.Reducer.mean()).sqrt().focalMedian(1, "square", "pixels")
        descargar(dist.clip(zona).toFloat(), zona.bounds(1),
                  os.path.join(salida, f"dist_{pid.replace(' ', '_').replace('-', '_')}.tif"))
    print("listo", flush=True)


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
