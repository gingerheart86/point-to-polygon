"""Configuración del plugin: rutas internas y ajustes de cada usuario.

Los ajustes de cada usuario se guardan en la configuración de QGIS, bajo punto_a_poligono/*, y
se cargan con el algoritmo "Configurar Punto a polígono":
    python_gee        ruta al Python que tiene earthengine-api
    proyecto_gee      proyecto de Google Cloud con Earth Engine habilitado
    proxy             proxy HTTP(S), si la red lo necesita (vacío = sin proxy)
    carpeta_trabajo   dónde se guardan resultados y rásters
"""
import configparser
import os

from qgis.core import QgsSettings

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
GEE_DIR = os.path.join(PLUGIN_DIR, "gee")
SCRIPT_04 = os.path.join(GEE_DIR, "04_segmentar_s2_gee.py")
SCRIPT_04D = os.path.join(GEE_DIR, "04d_rasters_zonas_gee.py")
ESTILOS = os.path.join(PLUGIN_DIR, "estilos")
PROVIDER_ID = "punto_a_poligono"
NOMBRE = "Punto a polígono"


def valor(clave, defecto=""):
    return QgsSettings().value(f"punto_a_poligono/{clave}", defecto) or defecto


def guardar(clave, v):
    QgsSettings().setValue(f"punto_a_poligono/{clave}", v)


def python_gee():
    return valor("python_gee", os.path.expandvars(r"%USERPROFILE%\.venvs\gee\Scripts\python.exe"))


def carpeta_trabajo():
    return valor("carpeta_trabajo", os.path.join(os.path.expanduser("~"), "Documents", "Punto_a_poligono"))


def estilo(nombre):
    return os.path.join(ESTILOS, nombre + ".qml")


def version():
    cp = configparser.ConfigParser()
    cp.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
    return cp.get("general", "version", fallback="?")


def entorno_gee():
    """Variables de entorno limpias para lanzar el Python de Earth Engine desde QGIS."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # que no herede el Python de QGIS. PYTHONEXECUTABLE (QGIS 3.44) hace que un venv use el Python base.
    for v in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__"):
        env.pop(v, None)
    proxy = valor("proxy")
    if proxy:
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
    return env
