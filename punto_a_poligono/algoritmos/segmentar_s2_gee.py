"""Algoritmo "Segmentar chacras con Sentinel-2 (GEE)".

Para cada punto toma el perfil temporal de NDVI de Sentinel-2 y busca los píxeles con un perfil
parecido que estén conectados con él, dentro de su zona de búsqueda. El cálculo lo hace Google
Earth Engine, mediante el script gee/04_segmentar_s2_gee.py, que corre en el Python configurado
con earthengine-api.
"""
import json
import os
import subprocess  # nosec B404
import tempfile

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from .. import config

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


class SegmentarS2GEE(QgsProcessingAlgorithm):
    PUNTOS, ZONAS, CAMPO_ID, INICIO, FIN, UMBRAL, OUTPUT = (
        "PUNTOS", "ZONAS", "CAMPO_ID", "INICIO", "FIN", "UMBRAL", "OUTPUT")

    def name(self):
        return "segmentar_s2_gee"

    def displayName(self):
        return "Segmentar chacras con Sentinel-2 (GEE)"

    def group(self):
        return "Piezas del modelo"

    def groupId(self):
        return "piezas"

    def shortHelpString(self):
        return ("Para cada punto, toma el perfil temporal de NDVI (Sentinel-2) en el punto y busca los píxeles con un "
                "perfil parecido que estén conectados con él, dentro de su zona de búsqueda. El resultado es el "
                "polígono de la chacra.\n\nUmbral: distancia máxima (RMS de NDVI) al perfil del punto. Con valores "
                "bajos el polígono queda más chico y seguro; con valores altos, más completo, pero puede pasarse a "
                "chacras vecinas. En la prueba inicial, 0,15–0,20 funcionó bien y por encima de 0,25 se pasaba a "
                "las vecinas.\n\nLas zonas de búsqueda deben tener el mismo campo identificador que los puntos.")

    def createInstance(self):
        return SegmentarS2GEE()

    def initAlgorithm(self, config_=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PUNTOS, "Puntos de las chacras", [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_ID, "Campo identificador", parentLayerParameterName=self.PUNTOS))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ZONAS, "Zonas de búsqueda (con el mismo campo identificador)", [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterString(self.INICIO, "Inicio de la temporada (AAAA-MM-DD)", "2026-05-01"))
        self.addParameter(QgsProcessingParameterString(self.FIN, "Fin de la temporada (AAAA-MM-DD)", "2026-12-31"))
        self.addParameter(QgsProcessingParameterNumber(
            self.UMBRAL, "Umbral de similitud (RMS de NDVI)", QgsProcessingParameterNumber.Type.Double, 0.15,
            minValue=0.01, maxValue=1))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "Chacras", QgsProcessing.SourceType.TypeVectorPolygon))

    @staticmethod
    def _geojson(fuente, campo, ruta):
        tr = QgsCoordinateTransform(fuente.sourceCrs(), WGS84, QgsProject.instance())
        feats = []
        for f in fuente.getFeatures():
            g = QgsGeometry(f.geometry())
            g.transform(tr)
            feats.append({"type": "Feature", "properties": {"id": str(f[campo])}, "geometry": json.loads(g.asJson(7))})
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)
        return len(feats)

    def processAlgorithm(self, parameters, context, feedback):
        puntos = self.parameterAsSource(parameters, self.PUNTOS, context)
        zonas = self.parameterAsSource(parameters, self.ZONAS, context)
        campo = self.parameterAsString(parameters, self.CAMPO_ID, context)
        inicio = self.parameterAsString(parameters, self.INICIO, context)
        fin = self.parameterAsString(parameters, self.FIN, context)
        umbral = self.parameterAsDouble(parameters, self.UMBRAL, context)
        python, proyecto = config.python_gee(), config.valor("proyecto_gee")
        if not os.path.exists(python):
            raise QgsProcessingException(f"No encuentro el Python de Earth Engine: {python}. "
                                         "Corré 'Configurar Punto a polígono'.")
        if campo not in zonas.fields().names():
            raise QgsProcessingException(f"Las zonas de búsqueda no tienen el campo '{campo}'")

        tmp = tempfile.mkdtemp(prefix="pap_seg_")
        n = self._geojson(puntos, campo, os.path.join(tmp, "puntos.geojson"))
        self._geojson(zonas, campo, os.path.join(tmp, "zonas_busqueda.geojson"))
        salida = os.path.join(tmp, "segmentos.geojson")
        feedback.pushInfo(f"{n} puntos. Segmentando en Earth Engine (puede tardar unos minutos)...")
        cmd = [python, "-I", "-u", config.SCRIPT_04, tmp, salida, inicio, fin] + ([proyecto] if proyecto else []) + [
            "--umbrales", str(umbral)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=config.entorno_gee(),  # nosec B603
                                text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for linea in proc.stdout:
            feedback.pushInfo(linea.rstrip())
            if feedback.isCanceled():
                proc.kill()
                return {}
        if proc.wait() != 0 or not os.path.exists(salida):
            raise QgsProcessingException("Falló la segmentación en Earth Engine (ver el registro)")

        seg = QgsVectorLayer(salida, "seg", "ogr")
        campos = QgsFields()
        for nombre, tipo in ((campo, QVariant.String), ("umbral", QVariant.Double), ("area_ha", QVariant.Double),
                             ("n_img", QVariant.Int), ("inicio", QVariant.String), ("fin", QVariant.String)):
            campos.append(QgsField(nombre, tipo))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, campos,
                                          QgsWkbTypes.Type.MultiPolygon, puntos.sourceCrs())
        tr = QgsCoordinateTransform(seg.crs(), puntos.sourceCrs(), QgsProject.instance())
        for f in seg.getFeatures():
            if not f.hasGeometry():
                feedback.reportError(f"{f['id']}: no se encontró chacra conectada al punto")
                continue
            g = f.geometry().makeValid()
            g.transform(tr)
            o = QgsFeature(campos)
            o.setGeometry(g)
            o.setAttributes([f["id"], f["umbral"], f["area_ha"], f["n_img"], f["inicio"], f["fin"]])
            sink.addFeature(o, QgsFeatureSink.Flag.FastInsert)
        return {self.OUTPUT: dest}
