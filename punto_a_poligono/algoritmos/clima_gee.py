"""Algoritmo "Lluvia y temperatura de las chacras (GEE)".

Agrega a cada polígono de chacra la precipitación (CHIRPS v3), la temperatura de superficie
(Landsat 8/9, 30 m) y la temperatura de piel y de suelo (ERA5-Land) del período indicado. El
cálculo se hace en Google Earth Engine con el script gee/04e_clima_chacras_gee.py.
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
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProject,
)
from qgis.PyQt.QtCore import QVariant

from .. import config

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
CAMPOS = [  # (nombre, tipo)
    ("precip_acum_mm", QVariant.Double), ("precip_media_mm_dia", QVariant.Double), ("precip_dias", QVariant.Int),
    ("precip_hasta", QVariant.String),
    ("lst_media_c", QVariant.Double), ("lst_max_c", QVariant.Double), ("lst_min_c", QVariant.Double),
    ("lst_escenas", QVariant.Int),
    ("era5_piel_media_c", QVariant.Double), ("era5_piel_max_c", QVariant.Double),
    ("era5_suelo_media_c", QVariant.Double),
]


class ClimaGEE(QgsProcessingAlgorithm):
    CHACRAS, CAMPO_ID, INICIO, FIN, OUTPUT = "CHACRAS", "CAMPO_ID", "INICIO", "FIN", "OUTPUT"

    def name(self):
        return "clima_gee"

    def displayName(self):
        return "Lluvia y temperatura de las chacras (GEE)"

    def group(self):
        return "Piezas del modelo"

    def groupId(self):
        return "piezas"

    def shortHelpString(self):
        return ("Agrega a cada chacra, para el período indicado:\n"
                "• Precipitación (CHIRPS v3 diario, ~5,5 km): acumulada (mm), promedio diario (mm/día), días con "
                "dato y último día disponible.\n"
                "• Temperatura de superficie (Landsat 8/9 C2 L2, ST_B10, 30 m): media, máxima y mínima de las "
                "escenas sin nubes (°C) y cantidad de escenas.\n"
                "• Temperatura de piel y de suelo (ERA5-Land diario, ~11 km): piel media y máxima, suelo 0-7 cm "
                "medio (°C).\n\nCHIRPS y ERA5 tienen píxeles más grandes que una chacra: chacras vecinas suelen "
                "tener el mismo valor. Landsat sí distingue entre chacras.")

    def createInstance(self):
        return ClimaGEE()

    def initAlgorithm(self, config_=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CHACRAS, "Chacras (polígonos)", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_ID, "Campo identificador", parentLayerParameterName=self.CHACRAS))
        self.addParameter(QgsProcessingParameterString(self.INICIO, "Inicio del período (AAAA-MM-DD)", "2026-05-01"))
        self.addParameter(QgsProcessingParameterString(self.FIN, "Fin del período (AAAA-MM-DD)", "2026-12-31"))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Chacras con lluvia y temperatura", QgsProcessing.TypeVectorPolygon))

    def processAlgorithm(self, parameters, context, feedback):
        chacras = self.parameterAsSource(parameters, self.CHACRAS, context)
        campo = self.parameterAsString(parameters, self.CAMPO_ID, context)
        inicio = self.parameterAsString(parameters, self.INICIO, context)
        fin = self.parameterAsString(parameters, self.FIN, context)
        python, proyecto = config.python_gee(), config.valor("proyecto_gee")
        if not os.path.exists(python):
            raise QgsProcessingException(f"No encuentro el Python de Earth Engine: {python}. "
                                         "Corré 'Configurar Punto a polígono'.")

        tmp = tempfile.mkdtemp(prefix="pap_clima_")
        tr = QgsCoordinateTransform(chacras.sourceCrs(), WGS84, QgsProject.instance())
        feats = []
        for f in chacras.getFeatures():
            g = QgsGeometry(f.geometry())
            g.transform(tr)
            feats.append({"type": "Feature", "properties": {"id": str(f[campo])}, "geometry": json.loads(g.asJson(6))})
        entrada, salida = os.path.join(tmp, "chacras.geojson"), os.path.join(tmp, "clima.json")
        with open(entrada, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)
        feedback.pushInfo(f"{len(feats)} chacras. Calculando lluvia y temperatura en Earth Engine...")

        cmd = [python, "-I", "-u", os.path.join(config.GEE_DIR, "04e_clima_chacras_gee.py"), entrada, salida,
               inicio, fin] + ([proyecto] if proyecto else [])
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=config.entorno_gee(),  # nosec B603
                                text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for linea in proc.stdout:
            feedback.pushInfo(linea.rstrip())
            if feedback.isCanceled():
                proc.kill()
                return {}
        if proc.wait() != 0 or not os.path.exists(salida):
            raise QgsProcessingException("Falló el cálculo de lluvia y temperatura en Earth Engine (ver el registro)")
        datos = json.load(open(salida, encoding="utf-8"))

        campos = chacras.fields()
        for n, t in CAMPOS:
            if campos.indexOf(n) < 0:
                campos.append(QgsField(n, t))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, campos, chacras.wkbType(),
                                          chacras.sourceCrs())
        for f in chacras.getFeatures():
            d = datos.get(str(f[campo]), {})
            attrs = dict(zip(f.fields().names(), f.attributes()))
            attrs.update({n: d.get(n) for n, _ in CAMPOS})
            o = QgsFeature(campos)
            o.setGeometry(f.geometry())
            o.setAttributes([attrs.get(n) for n in campos.names()])
            sink.addFeature(o, QgsFeatureSink.FastInsert)
        return {self.OUTPUT: dest}
