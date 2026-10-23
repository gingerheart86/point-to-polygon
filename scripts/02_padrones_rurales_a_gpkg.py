"""Convierte el parcelario rural de Catastro (DNC) a una capa de GeoPackage.

Fuente: catalogodatos.gub.uy, conjunto "Shapes del parcelario rural y urbano",
recurso "Total País - Rural" (paisrural_shp.zip, aprox. 146 MB):
https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-shapes-del-parcelario-rural-y-urbano

El shape ya viene en EPSG:32721 (WGS 84 / UTM 21S). Versión 2026-09-09: 251.919 padrones.
Campos: NOMDEPTO, CODDEPTO, PADRON, SECCAT, LAMINA, CUADRICULA, AREAHA, AREAMC, VALCAT.

Se lee directo del zip, sin descomprimir. Se convierte a MultiPolygon, se corrigen
geometrías inválidas (makeValid) y se crea índice espacial, necesario para buscar
rápido el padrón que contiene cada punto.

Uso, con el python de QGIS (OSGeo4W Shell):
    python 02_padrones_rurales_a_gpkg.py <paisrural_shp.zip> <salida.gpkg>

Equivalente con ogr2ogr:
    ogr2ogr -f GPKG salida.gpkg /vsizip/paisrural_shp.zip/PaisRural.shp -nln padrones_rurales
            -nlt PROMOTE_TO_MULTI -makevalid -lco SPATIAL_INDEX=YES -gt 65536

Consejo: si la salida va a una carpeta de red, conviene generarla en un disco local
y copiarla después, porque es mucho más rápido.
"""
import sys

from osgeo import gdal

gdal.UseExceptions()


def padrones_a_gpkg(zip_path, dst, capa="padrones_rurales"):
    src = f"/vsizip/{zip_path.replace(chr(92), '/')}/PaisRural.shp"
    gdal.VectorTranslate(
        dst,
        src,
        format="GPKG",
        layerName=capa,
        geometryType="PROMOTE_TO_MULTI",
        makeValid=True,
        layerCreationOptions=["SPATIAL_INDEX=YES"],
        groupTransactions=65536,
    )
    ds = gdal.OpenEx(dst)
    print(capa, ds.GetLayerByName(capa).GetFeatureCount())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    padrones_a_gpkg(*sys.argv[1:])
