"""Arma la zona de búsqueda de cada punto: la fracción de padrón rural que lo contiene
más las fracciones que la tocan (vecinas).

El padrón es una división catastral (jurídica), no agronómica: una chacra puede cruzar
a la fracción vecina. Por eso la zona de búsqueda incluye las vecinas y la segmentación
(paso 04) define el borde real.

Entrada:
  - capa de puntos (con un campo identificador)
  - capa padrones_rurales (paso 02)
Salida (GeoPackage, EPSG:32721):
  - capa zonas_busqueda: un polígono por punto, con id, PADRON de la fracción del punto,
    cantidad de fracciones y superficie en ha.
  - además exporta puntos y zonas en GeoJSON EPSG:4326 para el paso 04 (GEE).

Uso: desde la consola Python de QGIS, o con execute_code:
    zona_busqueda(puntos_uri, padrones_uri, salida_gpkg, campo_id, carpeta_geojson)
"""
import json
import os

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

CRS = QgsCoordinateReferenceSystem("EPSG:32721")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


def zona_busqueda(puntos_uri, padrones_uri, salida_gpkg, campo_id, carpeta_geojson):
    pts = QgsVectorLayer(puntos_uri, "puntos", "ogr")
    pad = QgsVectorLayer(padrones_uri, "padrones", "ogr")
    a_wgs = QgsCoordinateTransform(CRS, WGS84, QgsProject.instance())

    zonas = QgsVectorLayer("MultiPolygon?crs=EPSG:32721", "zonas_busqueda", "memory")
    pr = zonas.dataProvider()
    pr.addAttributes([
        QgsField("id", QVariant.String),
        QgsField("padron", QVariant.LongLong),
        QgsField("n_fracciones", QVariant.Int),
        QgsField("area_ha", QVariant.Double),
    ])
    zonas.updateFields()

    gj_pts, gj_zonas = [], []
    for p in pts.getFeatures():
        g = p.geometry()
        cand = pad.getFeatures(QgsFeatureRequest().setFilterRect(g.boundingBox()))
        frac = next((f for f in cand if f.geometry().contains(g)), None)
        if frac is None:
            print(f"{p[campo_id]}: el punto no cae en ningún padrón rural; se omite")
            continue
        F = frac.geometry()
        vecinas = [
            f.geometry()
            for f in pad.getFeatures(QgsFeatureRequest().setFilterRect(F.boundingBox()))
            if f.geometry().intersects(F)
        ]  # incluye la propia fracción
        Z = QgsGeometry.unaryUnion(vecinas)
        z = QgsFeature(zonas.fields())
        z.setGeometry(Z)
        z.setAttributes([str(p[campo_id]), frac["PADRON"], len(vecinas), Z.area() / 1e4])
        pr.addFeature(z)

        gp, gz = QgsGeometry(g), QgsGeometry(Z)
        gp.transform(a_wgs)
        gz.transform(a_wgs)
        props = {"id": str(p[campo_id])}
        gj_pts.append({"type": "Feature", "properties": props, "geometry": json.loads(gp.asJson(7))})
        gj_zonas.append({"type": "Feature", "properties": props, "geometry": json.loads(gz.asJson(7))})
        print(f"{p[campo_id]}: padrón {frac['PADRON']}, {len(vecinas)} fracciones, {Z.area() / 1e4:.0f} ha")

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "zonas_busqueda"
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(zonas, salida_gpkg, QgsProject.instance().transformContext(), opts)
    print("gpkg:", err[0] == QgsVectorFileWriter.NoError, err[1])

    os.makedirs(carpeta_geojson, exist_ok=True)
    for nombre, feats in (("puntos", gj_pts), ("zonas_busqueda", gj_zonas)):
        with open(os.path.join(carpeta_geojson, f"{nombre}.geojson"), "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)
