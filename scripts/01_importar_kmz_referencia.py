"""Importa un KMZ/KML de referencia (puntos + polígonos de chacras) a un GeoPackage en EPSG:32721.

Separa las geometrías en dos capas, manteniendo el campo Name (identificador de la chacra):
  - <prefijo>_poligonos (MULTIPOLYGON)
  - <prefijo>_puntos    (POINT)

Sirve para cargar polígonos dibujados a mano que luego se usan para validar los polígonos automáticos.

Uso, con el python de QGIS (OSGeo4W Shell):
    python 01_importar_kmz_referencia.py <entrada.kmz> <salida.gpkg> [prefijo]

El prefijo por defecto es "referencia". Si el GeoPackage ya existe, se agregan o reemplazan
las capas con ese prefijo y no se tocan las demás.
"""
import os
import sys

from osgeo import gdal

gdal.UseExceptions()

CRS_DESTINO = "EPSG:32721"  # WGS 84 / UTM 21S


def importar_kmz(src, dst, prefijo="referencia"):
    capas = [
        (f"{prefijo}_poligonos", "POLYGON", "MULTIPOLYGON"),
        (f"{prefijo}_puntos", "POINT", "POINT"),
    ]
    for nombre, tipo_kml, tipo_salida in capas:
        existe = os.path.exists(dst)
        gdal.VectorTranslate(
            dst,
            src,
            format="GPKG",
            accessMode="overwrite" if existe else None,  # reemplaza solo esta capa
            where=f"OGR_GEOMETRY='{tipo_kml}'",
            selectFields=["Name"],
            layerName=nombre,
            dstSRS=CRS_DESTINO,
            geometryType=tipo_salida,
            dim="XY",  # el KML trae Z=0; se descarta
        )
    ds = gdal.OpenEx(dst)
    for i in range(ds.GetLayerCount()):
        capa = ds.GetLayer(i)
        print(capa.GetName(), capa.GetFeatureCount())


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    importar_kmz(*sys.argv[1:])
