"""Segmenta la chacra que contiene cada punto con Sentinel-2 en Google Earth Engine.

Idea: los píxeles de una misma chacra tienen la misma **historia de NDVI** durante la
temporada (misma siembra, crecimiento y cosecha). Desde el punto (semilla) se toma
el perfil temporal de NDVI y se buscan los píxeles con un perfil parecido que estén
**conectados** con la semilla, dentro de la zona de búsqueda (paso 03).

Algoritmo, para cada punto:
  1. Sentinel-2 SR armonizado, con nubes enmascaradas usando Cloud Score+ (cs_cdf >= UMBRAL_CS).
  2. Compuestos de NDVI (mediana) por período (por defecto, mensuales) dentro de la temporada.
     Los huecos se rellenan con la mediana de toda la temporada.
  3. Perfil de la semilla: media del stack en un buffer de RADIO_SEMILLA m alrededor del punto.
  4. Distancia de cada píxel al perfil de la semilla: RMS de la diferencia de NDVI.
  5. Máscara: distancia < umbral, dentro de la zona de búsqueda.
     Se aplica apertura morfológica (erosión + dilatación) para cortar "puentes" finos
     hacia chacras vecinas.
  6. Se vectoriza y se queda con el polígono que contiene el punto.
     Se prueban varios umbrales; cada resultado lleva el campo "umbral".

Entrada (GeoJSON EPSG:4326, salida del paso 03): puntos.geojson y zonas_busqueda.geojson, con campo "id".
Salida: GeoJSON EPSG:4326 con un polígono por punto y umbral (campos id, umbral, area_ha, n_img).

Uso (python con earthengine-api):
    python 04_segmentar_s2_gee.py <carpeta_entrada> <salida.geojson> <inicio> <fin> [proyecto_gee] [--umbrales 0.15,0.2]
    ej.: python 04_segmentar_s2_gee.py datos/gee/entrada datos/gee/segmentos.geojson 2026-05-01 2026-10-15 mi-proyecto --umbrales 0.15

Detrás de un proxy, definir HTTP_PROXY y HTTPS_PROXY antes de correrlo.
"""
import json
import os
import sys

import ee

UMBRALES = [0.11, 0.15, 0.20, 0.25, 0.30]  # RMS de diferencia de NDVI (v1 probó 0.05-0.15)
UMBRAL_CS = 0.6                      # Cloud Score+: 1 = despejado
RADIO_SEMILLA = 20                   # m
DIAS_PERIODO = 30                    # largo de cada compuesto
APERTURA_PX = 1                      # radio (píxeles de 10 m) de la apertura morfológica
ESCALA = 10
# Variables del perfil temporal. "ndvi" = (B8-B4)/(B8+B4); las bandas (B2, B8, B11, ...) van
# como reflectancia 0-1. Ej.: ["ndvi", "B8", "B11", "B2"] suma NIR, SWIR y azul al NDVI.
BANDAS = ["ndvi"]


def coleccion_ndvi(zona, inicio, fin):
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(zona).filterDate(inicio, fin)
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED").filterBounds(zona).filterDate(inicio, fin)
    s2 = s2.linkCollection(cs, ["cs_cdf"])
    refl = [b for b in BANDAS if b != "ndvi"]

    def variables(img):
        img = img.updateMask(img.select("cs_cdf").gte(UMBRAL_CS))
        out = img.normalizedDifference(["B8", "B4"]).rename("ndvi")
        if refl:
            out = out.addBands(img.select(refl).divide(10000))
        return out.select(BANDAS).copyProperties(img, ["system:time_start"])

    return s2.map(variables), s2.size()


def stack_temporal(col, inicio, fin):
    ini, fin = ee.Date(inicio), ee.Date(fin)
    n = fin.difference(ini, "day").divide(DIAS_PERIODO).ceil().int()
    base = col.median()
    def compuesto(i):
        d0 = ini.advance(ee.Number(i).multiply(DIAS_PERIODO), "day")
        return col.filterDate(d0, d0.advance(DIAS_PERIODO, "day")).median().unmask(base).rename(BANDAS)
    imgs = ee.List.sequence(0, n.subtract(1)).map(compuesto)
    return ee.ImageCollection.fromImages(imgs).toBands()


def segmentar(punto, zona, inicio, fin):
    col, n_img = coleccion_ndvi(zona, inicio, fin)
    stack = stack_temporal(col, inicio, fin).clip(zona)
    semilla = stack.reduceRegion(ee.Reducer.mean(), punto.buffer(RADIO_SEMILLA), ESCALA)
    perfil = ee.Image.constant(stack.bandNames().map(lambda b: semilla.get(b))).rename(stack.bandNames())
    dist = stack.subtract(perfil).pow(2).reduce(ee.Reducer.mean()).sqrt().focalMedian(1, "square", "pixels")

    salida = []
    for u in UMBRALES:
        m = dist.lt(u)
        m = m.focalMin(APERTURA_PX, "circle", "pixels").focalMax(APERTURA_PX, "circle", "pixels")
        m = m.updateMask(m).clip(zona).int()
        vec = m.reduceToVectors(geometry=zona, scale=ESCALA, geometryType="polygon",
                                eightConnected=False, maxPixels=1e9, bestEffort=False)
        sel = vec.filterBounds(punto)
        salida.append(ee.Feature(ee.Algorithms.If(
            sel.size().gt(0),
            ee.Feature(sel.first()).set("umbral", u),
            ee.Feature(None, {"umbral": u}))))
    return ee.FeatureCollection(salida), n_img


def main(carpeta, salida, inicio, fin, proyecto=None, umbrales=None, bandas=None):
    global UMBRALES, BANDAS
    if umbrales:
        UMBRALES = list(umbrales)
    if bandas:
        BANDAS = list(bandas)
    ee.Initialize(project=proyecto)
    leer = lambda n: {f["properties"]["id"]: f["geometry"]
                      for f in json.load(open(os.path.join(carpeta, n), encoding="utf-8"))["features"]}
    puntos, zonas = leer("puntos.geojson"), leer("zonas_busqueda.geojson")
    feats = []
    for pid, gp in puntos.items():
        punto, zona = ee.Geometry(gp), ee.Geometry(zonas[pid])
        fc, n_img = segmentar(punto, zona, inicio, fin)
        res = fc.getInfo()
        n_img = n_img.getInfo()
        for f in res["features"]:
            g = f.get("geometry")
            area = ee.Geometry(g).area(1).divide(1e4).getInfo() if g else 0
            f["properties"] = {"id": pid, "umbral": f["properties"]["umbral"],
                               "area_ha": round(area, 1), "n_img": n_img,
                               "inicio": inicio, "fin": fin}
            feats.append(f)
            print(f"{pid} umbral {f['properties']['umbral']}: {area:.1f} ha")
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)
    print("guardado:", salida)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta_entrada")
    ap.add_argument("salida")
    ap.add_argument("inicio")
    ap.add_argument("fin")
    ap.add_argument("proyecto", nargs="?", default=None, help="proyecto de Google Cloud con Earth Engine")
    ap.add_argument("--umbrales", default=None, help="lista separada por comas, ej. 0.15,0.2")
    ap.add_argument("--bandas", default=None, help="variables del perfil, ej. ndvi,B8,B11,B2 (por defecto: ndvi)")
    a = ap.parse_args()
    main(a.carpeta_entrada, a.salida, a.inicio, a.fin, a.proyecto,
         [float(u) for u in a.umbrales.split(",")] if a.umbrales else None,
         a.bandas.split(",") if a.bandas else None)
