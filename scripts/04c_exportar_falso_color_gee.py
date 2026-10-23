"""Exporta composiciones en falso color de Sentinel-2 para cada zona de búsqueda (para ver en QGIS).

Composiciones (mediana del mes indicado, con nubes enmascaradas por Cloud Score+):
  - agri_<id>.tif     "Agriculture" de Copernicus: R=B11 (SWIR), G=B8 (NIR), B=B2 (azul)
                      Vegetación sana = verde intenso; suelo desnudo o rastrojo = marrón/rosado.
  - nir_swir_<id>.tif R=B8 (NIR), G=B11 (SWIR), B=B2 (azul)
                      Vegetación sana = rojo/naranja; suelo = verde/celeste.
Se exportan como Byte (0-255), estirando la reflectancia 0-0.5 (B8, B11) y 0-0.2 (B2).

Uso:
    python 04c_exportar_falso_color_gee.py <carpeta_entrada> <carpeta_salida> <mes_inicio> <mes_fin> [proyecto_gee]
    ej.: ... datos/gee/entrada salida 2026-08-15 2026-09-15 mi-proyecto
"""
import json
import os
import sys

import ee
import requests

COMPOSICIONES = {
    "agri": [("B11", 5000), ("B8", 5000), ("B2", 2000)],
    "nir_swir": [("B8", 5000), ("B11", 5000), ("B2", 2000)],
}


def main(carpeta, salida, inicio, fin, proyecto=None):
    ee.Initialize(project=proyecto)
    zonas = {f["properties"]["id"]: f["geometry"]
             for f in json.load(open(os.path.join(carpeta, "zonas_busqueda.geojson"), encoding="utf-8"))["features"]}
    os.makedirs(salida, exist_ok=True)
    hechas = set()
    for pid, gz in zonas.items():
        clave = json.dumps(gz, sort_keys=True)
        if clave in hechas:
            continue
        hechas.add(clave)
        zona = ee.Geometry(gz)
        s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(zona).filterDate(inicio, fin)
              .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs_cdf"])
              .map(lambda im: im.updateMask(im.select("cs_cdf").gte(0.6))))
        med = s2.median()
        for nombre, bandas in COMPOSICIONES.items():
            img = ee.Image.cat([med.select(b).divide(mx).multiply(255).clamp(1, 255) for b, mx in bandas]).toByte()
            url = img.getDownloadURL({"region": zona.bounds(1), "scale": 10, "crs": "EPSG:32721",
                                      "format": "GEO_TIFF", "filePerBand": False})
            r = requests.get(url, timeout=600)
            r.raise_for_status()
            ruta = os.path.join(salida, f"{nombre}_{pid.replace(' ', '_')}.tif")
            with open(ruta, "wb") as fh:
                fh.write(r.content)
            print(os.path.basename(ruta), f"{len(r.content) / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
