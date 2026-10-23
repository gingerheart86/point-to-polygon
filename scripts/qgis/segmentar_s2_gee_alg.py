"""Algoritmo de Processing de QGIS: "Segmentar chacras con Sentinel-2 (GEE)".

Envuelve el script 04_segmentar_s2_gee.py para poder usarlo dentro del Modelador de QGIS.
Como QGIS no trae la librería de Earth Engine, el paso de GEE corre en un Python aparte
(el que tenga earthengine-api instalado) mediante un subproceso.

Instalación: copiar este archivo a la carpeta de scripts de Processing del perfil de QGIS
(<perfil>/processing/scripts/) y refrescar la Caja de herramientas. El script
04_segmentar_s2_gee.py debe estar en la carpeta indicada en el parámetro SCRIPT_04.

Para no repetir la configuración en cada corrida, los valores por defecto se leen de la
configuración de QGIS (Opciones > Avanzado), si existen:
    punto_a_poligono/python_gee   ruta al python con earthengine-api
    punto_a_poligono/script_04    ruta a 04_segmentar_s2_gee.py
    punto_a_poligono/proyecto_gee proyecto de Google Cloud con Earth Engine
    punto_a_poligono/proxy        proxy HTTP(S), si la red lo necesita
"""
import json
import os
import subprocess
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
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


def _conf(clave, defecto=""):
    return QgsSettings().value(f"punto_a_poligono/{clave}", defecto) or defecto


class SegmentarS2GEE(QgsProcessingAlgorithm):
    PUNTOS, ZONAS, CAMPO_ID = "PUNTOS", "ZONAS", "CAMPO_ID"
    INICIO, FIN, UMBRAL = "INICIO", "FIN", "UMBRAL"
    PYTHON_GEE, SCRIPT_04, PROYECTO, PROXY = "PYTHON_GEE", "SCRIPT_04", "PROYECTO", "PROXY"
    OUTPUT = "OUTPUT"

    def name(self):
        return "segmentar_s2_gee"

    def displayName(self):
        return "Segmentar chacras con Sentinel-2 (GEE)"

    def group(self):
        return "Punto a polígono"

    def groupId(self):
        return "punto_a_poligono"

    def shortHelpString(self):
        return (
            "Para cada punto, toma el perfil temporal de NDVI (Sentinel-2) en el punto y busca los "
            "píxeles con un perfil parecido que estén conectados con él, dentro de su zona de búsqueda. "
            "El resultado es el polígono de la chacra.\n\n"
            "Umbral: distancia máxima (RMS de NDVI) al perfil del punto. Con valores bajos, el polígono "
            "queda más chico y seguro; con valores altos, más completo, pero puede pasarse a chacras vecinas. "
            "En la prueba inicial, 0,15–0,20 funcionó bien y por encima de 0,25 se pasaba a las vecinas.\n\n"
            "Las zonas de búsqueda deben tener el mismo campo identificador que los puntos."
        )

    def createInstance(self):
        return SegmentarS2GEE()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PUNTOS, "Puntos de las chacras", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_ID, "Campo identificador", parentLayerParameterName=self.PUNTOS))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ZONAS, "Zonas de búsqueda (con el mismo campo identificador)", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterString(self.INICIO, "Inicio de la temporada (AAAA-MM-DD)", "2026-05-01"))
        self.addParameter(QgsProcessingParameterString(self.FIN, "Fin de la temporada (AAAA-MM-DD)", "2026-10-15"))
        self.addParameter(QgsProcessingParameterNumber(
            self.UMBRAL, "Umbral de similitud (RMS de NDVI)", QgsProcessingParameterNumber.Double, 0.15, minValue=0.01, maxValue=1))
        # opcionales: si quedan vacíos (por ejemplo, dentro de un modelo) se toman de la configuración de QGIS
        self.addParameter(QgsProcessingParameterFile(
            self.PYTHON_GEE, "Python con earthengine-api", defaultValue=_conf("python_gee", "python"), optional=True))
        self.addParameter(QgsProcessingParameterFile(
            self.SCRIPT_04, "Script 04_segmentar_s2_gee.py", defaultValue=_conf("script_04"), extension="py",
            optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.PROYECTO, "Proyecto de Google Cloud (Earth Engine)", _conf("proyecto_gee"), optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.PROXY, "Proxy HTTP(S) (opcional)", _conf("proxy"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "Chacras", QgsProcessing.TypeVectorPolygon))

    def _geojson(self, fuente, campo, ruta, context):
        tr = QgsCoordinateTransform(fuente.sourceCrs(), WGS84, QgsProject.instance())
        feats = []
        for f in fuente.getFeatures():
            g = QgsGeometry(f.geometry())
            g.transform(tr)
            feats.append({"type": "Feature", "properties": {"id": str(f[campo])},
                          "geometry": json.loads(g.asJson(7))})
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
        python = self.parameterAsFile(parameters, self.PYTHON_GEE, context) or _conf("python_gee", "python")
        script = self.parameterAsFile(parameters, self.SCRIPT_04, context) or _conf("script_04")
        proyecto = self.parameterAsString(parameters, self.PROYECTO, context) or _conf("proyecto_gee")
        proxy = self.parameterAsString(parameters, self.PROXY, context) or _conf("proxy")
        if not os.path.exists(script):
            raise QgsProcessingException(f"No encuentro el script 04: {script}")
        if campo not in zonas.fields().names():
            raise QgsProcessingException(f"Las zonas de búsqueda no tienen el campo '{campo}'")

        tmp = tempfile.mkdtemp(prefix="punto_a_poligono_")
        n = self._geojson(puntos, campo, os.path.join(tmp, "puntos.geojson"), context)
        self._geojson(zonas, campo, os.path.join(tmp, "zonas_busqueda.geojson"), context)
        salida = os.path.join(tmp, "segmentos.geojson")
        feedback.pushInfo(f"{n} puntos. Segmentando en Earth Engine (puede tardar unos minutos)...")

        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        # que no herede el Python de QGIS. PYTHONEXECUTABLE (lo define QGIS 3.44) hace que el
        # lanzador de un venv ignore el venv y use el Python base, sin earthengine-api.
        for v in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__"):
            env.pop(v, None)
        if proxy:
            env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
        cmd = [python, "-I", "-u", script, tmp, salida, inicio, fin] + ([proyecto] if proyecto else []) + [
            "--umbrales", str(umbral)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
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
        campos.append(QgsField(campo, QVariant.String))
        campos.append(QgsField("umbral", QVariant.Double))
        campos.append(QgsField("area_ha", QVariant.Double))
        campos.append(QgsField("n_img", QVariant.Int))
        campos.append(QgsField("inicio", QVariant.String))
        campos.append(QgsField("fin", QVariant.String))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, campos,
                                          QgsWkbTypes.MultiPolygon, puntos.sourceCrs())
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
            sink.addFeature(o, QgsFeatureSink.FastInsert)
        return {self.OUTPUT: dest}
