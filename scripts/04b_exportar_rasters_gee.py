"""Exporta a GeoTIFF los rásters intermedios de la segmentación (paso 04), para verlos en QGIS.

Sirve para entender y revisar cómo se infiere el polígono. Para cada zona de búsqueda genera:
  - rgb_<id>.tif        color real (B4, B3, B2): mediana del mes de mayor NDVI de la temporada
  - ndvi_<id>.tif       stack de NDVI: una banda por período (por ejemplo, mensual)
  - distancia_<id>.tif  distancia (RMS de NDVI) de cada píxel al perfil del punto semilla.
                        Valores bajos = "se comporta igual que la chacra del punto".

Si varios puntos comparten la misma zona, la zona se exporta una sola vez, pero cada
punto genera su propio ráster de distancia.

Todo se exporta en EPSG:32721 a 10 m, recortado al rectángulo que envuelve la zona.

Uso (python con earthengine-api y requests):
    python 04b_exportar_rasters_gee.py <carpeta_entrada> <carpeta_salida> <inicio> <fin> [proyecto_gee]
"""
import importlib.util
import json
import os
import sys

import ee
import requests

# reutiliza las funciones del paso 04
_spec = importlib.util.spec_from_file_location(
    "seg", os.path.join(os.path.dirname(os.path.abspath(__file__)), "04_segmentar_s2_gee.py"))
seg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seg)

CRS = "EPSG:32721"


def descargar(img, region, ruta):
    url = img.getDownloadURL({"region": region, "scale": seg.ESCALA, "crs": CRS,
                              "format": "GEO_TIFF", "filePerBand": False})
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    with open(ruta, "wb") as fh:
        fh.write(r.content)
    print("  ", os.path.basename(ruta), f"{len(r.content) / 1e6:.1f} MB")


def main(carpeta, salida, inicio, fin, proyecto=None):
    ee.Initialize(project=proyecto)
    leer = lambda n: {f["properties"]["id"]: f["geometry"]
                      for f in json.load(open(os.path.join(carpeta, n), encoding="utf-8"))["features"]}
    puntos, zonas = leer("puntos.geojson"), leer("zonas_busqueda.geojson")
    os.makedirs(salida, exist_ok=True)
    hechas = {}
    for pid, gp in puntos.items():
        punto, zona = ee.Geometry(gp), ee.Geometry(zonas[pid])
        region = zona.bounds(1)
        clave = json.dumps(zonas[pid], sort_keys=True)
        col, _ = seg.coleccion_ndvi(zona, inicio, fin)
        stack = seg.stack_temporal(col, inicio, fin)
        nombre = pid.replace(" ", "_")
        print(pid)
        if clave not in hechas:
            # nombres de banda legibles: fecha de inicio de cada período
            n = stack.bandNames().size().getInfo()
            fechas = [ee.Date(inicio).advance(i * seg.DIAS_PERIODO, "day").format("YYYY-MM-dd").getInfo()
                      for i in range(n)]
            descargar(stack.rename([f"ndvi_{f}" for f in fechas]).toFloat(), region,
                      os.path.join(salida, f"ndvi_{nombre}.tif"))
            # color real del período de mayor NDVI medio en la zona
            medias = stack.reduceRegion(ee.Reducer.mean(), zona, 30, maxPixels=1e9).getInfo()
            i_max = max(range(n), key=lambda i: medias[stack.bandNames().getInfo()[i]] or -1)
            d0 = ee.Date(inicio).advance(i_max * seg.DIAS_PERIODO, "day")
            s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(zona)
                  .filterDate(d0, d0.advance(seg.DIAS_PERIODO, "day"))
                  .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs_cdf"])
                  .map(lambda im: im.updateMask(im.select("cs_cdf").gte(seg.UMBRAL_CS))))
            descargar(s2.median().select(["B4", "B3", "B2"]).toUint16(), region,
                      os.path.join(salida, f"rgb_{nombre}.tif"))
            hechas[clave] = nombre
        else:
            print("   (misma zona que", hechas[clave] + ")")
        semilla = stack.reduceRegion(ee.Reducer.mean(), punto.buffer(seg.RADIO_SEMILLA), seg.ESCALA)
        perfil = ee.Image.constant(stack.bandNames().map(lambda b: semilla.get(b))).rename(stack.bandNames())
        dist = stack.subtract(perfil).pow(2).reduce(ee.Reducer.mean()).sqrt().focalMedian(1, "square", "pixels")
        descargar(dist.rename("distancia").toFloat(), region, os.path.join(salida, f"distancia_{nombre}.tif"))


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
