"""Proveedor de Processing "Punto a polígono": el modelo, la configuración y sus piezas."""
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from . import config
from .algoritmos.clima_gee import ClimaGEE
from .algoritmos.comparar_ha import CompararHa
from .algoritmos.configurar import Configurar
from .algoritmos.rasters_s2_gee import RastersS2GEE
from .algoritmos.segmentar_s2_gee import SegmentarS2GEE
from .modelo import ModeloPuntoAPoligono


class ProveedorPuntoAPoligono(QgsProcessingProvider):
    def id(self):
        return config.PROVIDER_ID

    def name(self):
        return config.NOMBRE

    def longName(self):
        return f"{config.NOMBRE} v{config.version()}"

    def icon(self):
        ruta = os.path.join(config.PLUGIN_DIR, "icon.png")
        return QIcon(ruta) if os.path.exists(ruta) else super().icon()

    def loadAlgorithms(self):
        for alg in (Configurar(), SegmentarS2GEE(), CompararHa(), ClimaGEE(), RastersS2GEE()):
            self.addAlgorithm(alg)
        self.addAlgorithm(ModeloPuntoAPoligono())
