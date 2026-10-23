"""Compara los polígonos automáticos (paso 04) con polígonos de referencia dibujados a mano.

Métricas por chacra:
  - IoU = área(intersección) / área(unión). 1 = idénticos.
  - precision = intersección / automático  (qué parte de lo detectado es la chacra real)
  - recall    = intersección / referencia  (qué parte de la chacra real se detectó)
  - dif_area_pct = (automático - referencia) / referencia * 100

Opcionalmente guarda los segmentos (EPSG:32721) con las métricas en un GeoPackage.

Uso: desde la consola Python de QGIS, o con execute_code:
    validar(segmentos_geojson, referencia_uri, campo_id_ref, salida_gpkg=None, capa="segmentos")
Devuelve una lista de diccionarios con las métricas.
"""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsField,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

CRS = QgsCoordinateReferenceSystem("EPSG:32721")


def validar(segmentos_geojson, referencia_uri, campo_id_ref, salida_gpkg=None, capa="segmentos"):
    seg = QgsVectorLayer(segmentos_geojson, "seg", "ogr")
    ref = QgsVectorLayer(referencia_uri, "ref", "ogr")
    tr = QgsCoordinateTransform(seg.crs(), CRS, QgsProject.instance())
    R = {str(f[campo_id_ref]): f.geometry().makeValid() for f in ref.getFeatures()}

    out = QgsVectorLayer("MultiPolygon?crs=EPSG:32721", capa, "memory")
    pr = out.dataProvider()
    nombres = ["id", "umbral", "area_ha", "iou", "precision", "recall", "dif_area_pct"]
    pr.addAttributes([QgsField("id", QVariant.String)] + [QgsField(n, QVariant.Double) for n in nombres[1:]])
    out.updateFields()

    filas = []
    for f in seg.getFeatures():
        g = f.geometry()
        if g.isNull() or g.isEmpty():
            fila = dict(id=f["id"], umbral=f["umbral"], area_ha=0, iou=0, precision=0, recall=0, dif_area_pct=-100)
        else:
            g = g.makeValid()
            g.transform(tr)
            r = R[str(f["id"])]
            inter, union = g.intersection(r).area(), g.combine(r).area()
            fila = dict(
                id=f["id"], umbral=f["umbral"], area_ha=round(g.area() / 1e4, 1),
                iou=round(inter / union, 3), precision=round(inter / g.area(), 3),
                recall=round(inter / r.area(), 3), dif_area_pct=round(100 * (g.area() - r.area()) / r.area(), 1),
            )
            nf = out.fields()
            from qgis.core import QgsFeature
            o = QgsFeature(nf)
            o.setGeometry(g)
            o.setAttributes([fila[n] for n in nombres])
            pr.addFeature(o)
        filas.append(fila)

    if salida_gpkg:
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = capa
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        QgsVectorFileWriter.writeAsVectorFormatV3(out, salida_gpkg, QgsProject.instance().transformContext(), opts)
    return filas
