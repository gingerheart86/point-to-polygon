"""Pasa MANUAL.md a MANUAL.pdf con el Qt de QGIS (no hace falta pandoc ni nada instalado aparte).

Ojo al escribir el manual: Qt numera como ítem aparte cada párrafo o bloque ``` dentro de una lista.
Los comandos dentro de una lista van como sub-viñetas con `código`."""
import os
from datetime import date

from qgis.PyQt.QtCore import QMarginsF, QRectF, QSizeF
from qgis.PyQt.QtGui import (QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument,
                             QTextTable)

from . import config

CSS = """
body { font-family: Arial; font-size: 10pt; color: #222; }
h1 { color: #1f4e79; font-size: 20pt; }
h2 { color: #1f4e79; font-size: 15pt; margin-top: 18px; }
h3 { color: #1f4e79; font-size: 12pt; margin-top: 12px; }
th, td { padding: 4px; }
pre, code { font-family: Consolas; font-size: 9pt; background-color: #f2f2f2; }
blockquote { color: #444; background-color: #eef4fa; }
"""


def _colorear_encabezados(doc):
    """Fondo celeste en la primera fila de cada tabla."""
    pendientes = [doc.rootFrame()]
    while pendientes:
        marco = pendientes.pop()
        pendientes.extend(marco.childFrames())
        if isinstance(marco, QTextTable):
            for c in range(marco.columns()):
                celda = marco.cellAt(0, c)
                fmt = celda.format()
                fmt.setBackground(QColor("#dde7f2"))
                celda.setFormat(fmt)


def generar(md=None, pdf=None):
    """Arma el PDF y devuelve su ruta. Por defecto, MANUAL.md → MANUAL.pdf en la carpeta del plugin."""
    md = md or os.path.join(config.PLUGIN_DIR, "MANUAL.md")
    pdf = pdf or os.path.splitext(md)[0] + ".pdf"
    with open(md, encoding="utf-8") as f:
        texto = f.read()
    # Qt convierte el Markdown a HTML; se vuelve a cargar con la hoja de estilo para que tome los colores
    previo = QTextDocument()
    previo.setMarkdown(texto)
    cuerpo = previo.toHtml()
    pie = (f"<p style='color:#888; font-size:8pt'>Plugin {config.NOMBRE} v{config.version()} · "
           f"manual generado el {date.today():%d/%m/%Y}</p>")

    writer = QPdfWriter(pdf)
    writer.setResolution(300)
    writer.setTitle(f"Manual de uso: plugin {config.NOMBRE}")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(18, 15, 18, 15), QPageLayout.Unit.Millimeter))
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Arial", 10))
    doc.setDefaultStyleSheet(CSS)
    doc.setHtml(cuerpo.replace("</body>", pie + "</body>"))
    _colorear_encabezados(doc)
    # el documento se diagrama en puntos (72 dpi) y se escala a la resolución del PDF
    area = writer.pageLayout().paintRectPixels(writer.resolution())
    escala = writer.resolution() / 72
    doc.setPageSize(QSizeF(area.width() / escala, area.height() / escala))
    ancho, alto = doc.pageSize().width(), doc.pageSize().height()
    pintor = QPainter(writer)
    try:  # el pintor se cierra siempre: un QPainter abierto puede cerrar QGIS
        pintor.scale(escala, escala)
        for i in range(doc.pageCount()):
            if i:
                writer.newPage()
            pintor.save()
            pintor.translate(0, -i * alto)
            doc.drawContents(pintor, QRectF(0, i * alto, ancho, alto))
            pintor.restore()
    finally:
        pintor.end()
    return pdf


def actualizado():
    """Ruta de MANUAL.pdf, regenerándolo si falta o si MANUAL.md es más nuevo."""
    md = os.path.join(config.PLUGIN_DIR, "MANUAL.md")
    pdf = os.path.join(config.PLUGIN_DIR, "MANUAL.pdf")
    if not os.path.exists(pdf) or os.path.getmtime(md) > os.path.getmtime(pdf):
        try:
            generar(md, pdf)
        except OSError:  # carpeta sin permiso de escritura: se abre el .md
            return md if not os.path.exists(pdf) else pdf
    return pdf
