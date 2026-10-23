"""Lluvia y temperatura de cada chacra en Google Earth Engine, para el período indicado.

Entrada: chacras.geojson (EPSG:4326, campo "id"), con los polígonos de las chacras.
Salida:  JSON {id: {variable: valor}} con:

  Precipitación, CHIRPS v3 diario (UCSB-CHC/CHIRPS/V3/DAILY_SAT, ~5,5 km):
    precip_acum_mm       lluvia acumulada del período
    precip_media_mm_dia  promedio diario
    precip_dias          días con dato
    precip_hasta         último día con dato (CHIRPS tiene unas semanas de demora)

  Temperatura de superficie, Landsat 8 y 9 Collection 2 Level 2, banda ST_B10 (30 m):
    lst_media_c / lst_max_c / lst_min_c   media, máxima y mínima de las escenas sin nubes (°C)
    lst_escenas          cantidad de escenas usadas
    Se enmascaran nubes, sombras y cirros con QA_PIXEL. Factor: ST_B10*0.00341802 + 149 (K).

  Temperatura de piel y de suelo, ERA5-Land diario (ECMWF/ERA5_LAND/DAILY_AGGR, ~11 km):
    era5_piel_media_c    skin_temperature media (temperatura de la superficie de la cobertura)
    era5_piel_max_c      máxima de las máximas diarias de skin_temperature
    era5_suelo_media_c   soil_temperature_level_1 media (suelo, 0–7 cm)

Para los datos de baja resolución (CHIRPS, ERA5) se toma el valor del píxel en el que cae la
chacra (escala de muestreo de 500 m), porque una chacra suele ser más chica que un píxel.

Uso: python 04e_clima_chacras_gee.py <chacras.geojson> <salida.json> <inicio> <fin> [proyecto_gee]
"""
import json
import sys

import ee

K = 273.15


def lst_landsat(geom, ini, fin):
    def prep(img):
        qa = img.select("QA_PIXEL")
        # bits 1 nube dilatada, 2 cirro, 3 nube, 4 sombra de nube
        limpia = qa.bitwiseAnd(0b11110).eq(0)
        st = img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(K).rename("lst")
        return st.updateMask(limpia).copyProperties(img, ["system:time_start"])

    col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
           .filterBounds(geom).filterDate(ini, fin).map(prep))
    # solo las escenas donde la chacra tiene pixeles sin nubes
    col = col.map(lambda i: i.set("n", i.reduceRegion(ee.Reducer.count(), geom, 30, maxPixels=1e8).get("lst")))
    col = col.filter(ee.Filter.gt("n", 0))
    return col


def stats(geom, ini, fin):
    chirps = (ee.ImageCollection("UCSB-CHC/CHIRPS/V3/DAILY_SAT").filterDate(ini, fin).filterBounds(geom)
              .select("precipitation"))
    era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(ini, fin).filterBounds(geom)
    lst = lst_landsat(geom, ini, fin)

    def val(img, escala, banda):
        return img.reduceRegion(ee.Reducer.mean(), geom, escala, maxPixels=1e9, bestEffort=True).get(banda)

    lst_med = lst.mean()
    return ee.Dictionary({
        "precip_acum_mm": val(chirps.sum(), 500, "precipitation"),
        "precip_media_mm_dia": val(chirps.mean(), 500, "precipitation"),
        "precip_dias": chirps.size(),
        "precip_hasta": ee.Algorithms.If(chirps.size().gt(0),
                                         ee.Date(chirps.aggregate_max("system:time_start")).format("YYYY-MM-dd"),
                                         None),
        "lst_media_c": ee.Algorithms.If(lst.size().gt(0), val(lst_med, 30, "lst"), None),
        "lst_max_c": ee.Algorithms.If(lst.size().gt(0), val(lst.max(), 30, "lst"), None),
        "lst_min_c": ee.Algorithms.If(lst.size().gt(0), val(lst.min(), 30, "lst"), None),
        "lst_escenas": lst.size(),
        "era5_piel_media_c": ee.Number(val(era5.select("skin_temperature").mean(), 500, "skin_temperature"))
        .subtract(K),
        "era5_piel_max_c": ee.Number(val(era5.select("skin_temperature_max").max(), 500, "skin_temperature_max"))
        .subtract(K),
        "era5_suelo_media_c": ee.Number(val(era5.select("soil_temperature_level_1").mean(), 500,
                                            "soil_temperature_level_1")).subtract(K),
    })


def main(entrada, salida, inicio, fin, proyecto=None):
    ee.Initialize(project=proyecto)
    feats = json.load(open(entrada, encoding="utf-8"))["features"]
    out = {}
    for f in feats:
        pid = f["properties"]["id"]
        try:
            d = stats(ee.Geometry(f["geometry"]), inicio, fin).getInfo()
        except Exception as e:  # noqa: BLE001
            print(f"{pid}: error {str(e)[:150]}", flush=True)
            continue
        out[pid] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()}
        print(f"{pid}: lluvia {out[pid]['precip_acum_mm']} mm | LST {out[pid]['lst_media_c']} °C "
              f"({out[pid]['lst_escenas']} escenas) | ERA5 piel {out[pid]['era5_piel_media_c']} °C", flush=True)
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump(out, fh)


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
