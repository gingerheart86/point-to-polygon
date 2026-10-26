"""Algoritmo "Configurar Punto a polígono": se corre UNA vez por PC.

Guarda en la configuración de QGIS:
  - la ruta al Python con earthengine-api;
  - el proyecto de Google Cloud con Earth Engine;
  - el proxy (si la red lo necesita);
  - la carpeta de trabajo, donde quedan resultados y rásters.
Después prueba la conexión con Earth Engine y avisa si algo falla.
"""
import os
import subprocess  # nosec B404

from qgis.core import (
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
)
from qgis.PyQt.QtCore import QTimer

from .. import config


def _refrescar():
    prov = QgsApplication.processingRegistry().providerById(config.PROVIDER_ID)
    if prov:
        prov.refreshAlgorithms()  # el modelo toma la carpeta de trabajo nueva


class Configurar(QgsProcessingAlgorithm):
    PYTHON, PROYECTO, PROXY, CARPETA, PROBAR, OUTPUT = "PYTHON", "PROYECTO", "PROXY", "CARPETA", "PROBAR", "OUTPUT"

    def name(self):
        return "configurar"

    def displayName(self):
        return "Configurar Punto a polígono (una vez por PC)"

    def shortDescription(self):
        return "Python con earthengine-api, proyecto de Earth Engine, proxy y carpeta de trabajo."

    def group(self):
        return ""

    def groupId(self):
        return ""

    def shortHelpString(self):
        return ("Se corre UNA vez en cada PC, antes de usar el modelo. Guarda dónde está el Python con "
                "earthengine-api, el proyecto de Google Earth Engine, el proxy de la red y la carpeta de trabajo. "
                "Después prueba la conexión con Earth Engine.\n\n"
                "Requisitos previos de la PC:\n"
                "• Python con earthengine-api (y requests; detrás de un proxy con inspección SSL, también "
                "pip-system-certs).\n"
                "• Haber corrido una vez 'earthengine authenticate' con una cuenta que tenga acceso al proyecto.\n"
                "• Salida a *.googleapis.com, directa o por el proxy.")

    def createInstance(self):
        return Configurar()

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.Flag.FlagNoThreading

    def initAlgorithm(self, config_=None):
        self.addParameter(QgsProcessingParameterFile(
            self.PYTHON, "Python con earthengine-api (python.exe)", defaultValue=config.python_gee(), extension="exe"))
        self.addParameter(QgsProcessingParameterString(
            self.PROYECTO, "Proyecto de Google Cloud con Earth Engine", config.valor("proyecto_gee")))
        self.addParameter(QgsProcessingParameterString(
            self.PROXY, "Proxy HTTP(S), ej. http://proxy.empresa:8080 (vacío = sin proxy)", config.valor("proxy"),
            optional=True))
        self.addParameter(QgsProcessingParameterFile(
            self.CARPETA, "Carpeta de trabajo (resultados y rásters)",
            behavior=QgsProcessingParameterFile.Behavior.Folder, defaultValue=config.carpeta_trabajo()))
        self.addParameter(QgsProcessingParameterBoolean(self.PROBAR, "Probar la conexión con Earth Engine", True))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT, "Resultado"))

    def processAlgorithm(self, parameters, context, feedback):
        python = self.parameterAsFile(parameters, self.PYTHON, context)
        proyecto = self.parameterAsString(parameters, self.PROYECTO, context).strip()
        proxy = (self.parameterAsString(parameters, self.PROXY, context) or "").strip()
        carpeta = self.parameterAsFile(parameters, self.CARPETA, context)
        if not os.path.exists(python):
            raise QgsProcessingException(f"No existe {python}")
        for sub in ("", "rasters"):
            os.makedirs(os.path.join(carpeta, sub), exist_ok=True)
        config.guardar("python_gee", python)
        config.guardar("proyecto_gee", proyecto)
        config.guardar("proxy", proxy)
        config.guardar("carpeta_trabajo", carpeta)
        feedback.pushInfo(f"Configuración guardada. Carpeta de trabajo: {carpeta}")

        resultado = "Configuración guardada."
        if self.parameterAsBool(parameters, self.PROBAR, context):
            feedback.pushInfo("Probando Earth Engine...")
            codigo = ("import ee; ee.Initialize(project=%r); "
                      "n = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').limit(1).size().getInfo(); "
                      "print('Earth Engine OK', n)") % (proyecto or None)
            p = subprocess.run([python, "-I", "-c", codigo], capture_output=True, text=True, env=config.entorno_gee(),  # nosec B603
                               timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            salida = (p.stdout + p.stderr).strip()
            feedback.pushInfo(salida[-1500:])
            if p.returncode != 0:
                raise QgsProcessingException(
                    "La configuración se guardó, pero NO se pudo conectar con Earth Engine. Revisá: que "
                    "earthengine-api esté instalado en ese Python, que hayas corrido 'earthengine authenticate', el "
                    "nombre del proyecto y el proxy.")
            resultado += " Earth Engine OK."
        QTimer.singleShot(0, _refrescar)
        return {self.OUTPUT: resultado}
