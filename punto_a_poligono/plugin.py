"""Plugin de QGIS "Punto a polígono": registra el proveedor de Processing y agrega un menú."""
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction

from . import config
from .provider import ProveedorPuntoAPoligono

MENU = config.NOMBRE


class PluginPuntoAPoligono:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.acciones = []

    def initProcessing(self):
        self.provider = ProveedorPuntoAPoligono()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        for texto, funcion in (("Ejecutar el modelo punto → polígono…", self.abrir_modelo),
                               ("Abrir carpeta de trabajo", self.abrir_carpeta),
                               ("Configurar (una vez por PC)…", self.abrir_configurar),
                               ("Manual de uso", self.abrir_manual)):
            a = QAction(texto, self.iface.mainWindow())
            a.triggered.connect(funcion)
            self.iface.addPluginToMenu(MENU, a)
            self.acciones.append(a)

    def unload(self):
        for a in self.acciones:
            self.iface.removePluginMenu(MENU, a)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    @staticmethod
    def _dialogo(alg_id):
        from processing import execAlgorithmDialog
        execAlgorithmDialog(alg_id)

    def abrir_modelo(self):
        self._dialogo(f"{config.PROVIDER_ID}:punto_a_poligono")

    def abrir_configurar(self):
        self._dialogo(f"{config.PROVIDER_ID}:configurar")

    @staticmethod
    def abrir_carpeta():
        carpeta = config.carpeta_trabajo()
        os.makedirs(carpeta, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(carpeta))

    @staticmethod
    def abrir_manual():
        from .manual_pdf import actualizado
        QDesktopServices.openUrl(QUrl.fromLocalFile(actualizado()))
