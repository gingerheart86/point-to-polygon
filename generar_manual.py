"""Genera punto_a_poligono/MANUAL.pdf a partir de MANUAL.md, fuera de QGIS.

Lo llama empaquetar.ps1 con el Python de QGIS, por ejemplo:
    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" generar_manual.py
"""
import os
import sys

from qgis.core import QgsApplication

app = QgsApplication([], True)  # hace falta la parte gráfica de Qt para las fuentes
app.initQgis()
raiz = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, raiz)
from punto_a_poligono.manual_pdf import generar  # noqa: E402

print(generar(os.path.join(raiz, "punto_a_poligono", "MANUAL.md")))
app.exitQgis()

