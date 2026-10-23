"""Arma el modelo "Punto a polígono (modelo completo)" con los algoritmos del plugin.

El modelo NO se guarda como .model3 ni se edita en el Modelador: se construye en código cada vez
que QGIS carga el plugin. Así, el modelo instalado siempre coincide con la versión del plugin.
Para cambiarlo se edita este archivo y se propone el cambio por pull request en el repositorio.

Pasos:
  1. Zona de búsqueda: círculo alrededor de cada punto
  2. Punto a polígono: segmentar con Sentinel-2 (Google Earth Engine)    → salida Segmentación
  3. Rellenar huecos chicos
  4. Calcular hectáreas
  5. Comparar con las hectáreas declaradas (opcional): OK / REVISAR / SIN DATO + motivo
  6. Lluvia (CHIRPS v3) y temperatura (Landsat 8/9 30 m, ERA5-Land) de cada polígono (GEE)
  7. Polígonos finales                                                     → salida Polígonos
  8. Aplicar estilos
  9. Rásters Sentinel-2 y de clima de las zonas (GEE) + zonas de búsqueda (apagadas)
"""
from qgis.core import (
    QgsProcessing,
    QgsProcessingModelAlgorithm,
    QgsProcessingModelChildAlgorithm,
    QgsProcessingModelChildParameterSource as Src,
    QgsProcessingModelOutput,
    QgsProcessingModelParameter,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)
from qgis.PyQt.QtCore import QPointF

from . import config

D = QgsProcessingParameterNumber.Double


def _parametros():
    avanzado = QgsProcessingParameterDefinition.FlagAdvanced
    ps = [
        QgsProcessingParameterFeatureSource("puntos", "Puntos (uno dentro de cada chacra)",
                                            [QgsProcessing.TypeVectorPoint]),
        QgsProcessingParameterField("campo_id", "Campo identificador de cada punto (valores únicos)",
                                    parentLayerParameterName="puntos"),
        QgsProcessingParameterField("campo_ha", "Campo de hectáreas declaradas (opcional)",
                                    parentLayerParameterName="puntos", optional=True),
        QgsProcessingParameterString("inicio", "Inicio de la temporada (AAAA-MM-DD)", "2026-05-01"),
        QgsProcessingParameterString("fin", "Fin de la temporada (AAAA-MM-DD)", "2026-12-31"),
        QgsProcessingParameterNumber("umbral", "Umbral de similitud (RMS de NDVI)", D, 0.15, minValue=0.01, maxValue=1),
        QgsProcessingParameterNumber("tolerancia", "Tolerancia de diferencia de ha (%)", D, 20, minValue=0),
        QgsProcessingParameterNumber("radio_m", "Radio de búsqueda alrededor del punto (m)", D, 3000, minValue=500),
        QgsProcessingParameterNumber("huecos_m2", "Rellenar huecos menores a (m2)", D, 50000, minValue=0),
    ]
    for p in ps[5:]:  # umbral en adelante: opciones avanzadas (plegadas en la ventana)
        p.setFlags(p.flags() | avanzado)
    return ps


AYUDA = {
    "ALG_DESC": (
        "A partir de UN PUNTO dentro de cada chacra, dibuja el polígono del lote con la serie temporal de NDVI de "
        "Sentinel-2 (Google Earth Engine): toma la historia de NDVI del punto y junta los píxeles conectados que "
        "tuvieron la misma historia. Después calcula las hectáreas, las compara con las declaradas (si se elige un "
        "campo), y agrega la LLUVIA (CHIRPS v3: acumulada y promedio diario) y la TEMPERATURA (Landsat 8/9 a 30 m y "
        "ERA5-Land) del período.\n\nAntes de usarlo por primera vez en una PC: correr 'Configurar Punto a polígono'.\n\n"
        "SALIDAS (en la carpeta de trabajo; cada corrida REEMPLAZA las capas anteriores):\n"
        "• Segmentación GEE (polígono crudo) • Polígonos (area_ha, ha_declaradas, dif_pct, control, motivo, lluvia y "
        "temperatura) • Grupos 'Sentinel-2 (GEE)' y 'Lluvia y temperatura (GEE)' • Zonas de búsqueda (apagadas)."),
    "SHORT_DESCRIPTION": "Puntos → polígonos de chacras con Sentinel-2 (GEE), hectáreas, lluvia y temperatura.",
    "ALG_CREATOR": "Carolina Menchaca",
    "puntos": "Capa de puntos, uno dentro de cada chacra. Cualquier sistema de coordenadas.",
    "campo_id": "Identificador de cada punto: se copia a su polígono. Tiene que ser único.",
    "campo_ha": "Si se elige, compara las hectáreas estimadas con las declaradas (OK / REVISAR / SIN DATO).",
    "inicio": "Inicio de la temporada del cultivo. También es el inicio del período de lluvia y temperatura.",
    "fin": "Fin de la temporada del cultivo. Si sigue en curso, poné una fecha futura: se usa lo disponible.",
    "umbral": "Qué tan parecida tiene que ser la historia de NDVI de un píxel a la del punto. 0,15 recomendado.",
    "tolerancia": "REVISAR si la diferencia de ha supera este %.",
    "radio_m": "Radio del círculo de búsqueda (m). Solo subirlo para chacras de más de ~1.000 ha.",
    "huecos_m2": "Rellena los agujeros menores a este tamaño (50000 m² = 5 ha).",
}


def armar():
    trabajo = config.carpeta_trabajo().replace("\\", "/")
    gpkg = trabajo + "/punto_a_poligono.gpkg"
    prov = config.PROVIDER_ID + ":"
    m = QgsProcessingModelAlgorithm("punto_a_poligono", "")
    params = _parametros()
    for i, p in enumerate(params):
        c = QgsProcessingModelParameter(p.name())
        c.setPosition(QPointF(120, 80 + i * 80))
        m.addModelParameter(p, c)
    m.setParameterOrder([p.name() for p in params])
    P, C = Src.fromModelParameter, Src.fromChildOutput

    def paso(cid, alg, desc, y, fuentes, fijos=None, x=520):
        c = QgsProcessingModelChildAlgorithm(alg)
        c.setChildId(cid)
        c.setDescription(desc)
        c.setPosition(QPointF(x, y))
        for k, v in fuentes.items():
            c.addParameterSources(k, [v])
        for k, v in (fijos or {}).items():
            c.addParameterSources(k, [Src.fromStaticValue(v)])
        return c

    pasos = [
        paso("zona", "native:buffer", "1. Zona de búsqueda (círculo alrededor del punto)", 100,
             {"INPUT": P("puntos"), "DISTANCE": P("radio_m")},
             {"SEGMENTS": 16, "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2, "DISSOLVE": False}),
        paso("segmentar", prov + "segmentar_s2_gee", "2. Punto a polígono: segmentar con Sentinel-2 (GEE)", 210,
             {"PUNTOS": P("puntos"), "ZONAS": C("zona", "OUTPUT"), "CAMPO_ID": P("campo_id"), "INICIO": P("inicio"),
              "FIN": P("fin"), "UMBRAL": P("umbral")}),
        paso("huecos", "native:deleteholes", "3. Rellenar huecos chicos", 320,
             {"INPUT": C("segmentar", "OUTPUT"), "MIN_AREA": P("huecos_m2")}),
        paso("area", "native:fieldcalculator", "4. Calcular hectáreas", 430, {"INPUT": C("huecos", "OUTPUT")},
             {"FIELD_NAME": "area_ha", "FIELD_TYPE": 0, "FIELD_LENGTH": 10, "FIELD_PRECISION": 1,
              "FORMULA": "round($area / 10000, 1)"}),
        paso("control", prov + "comparar_ha", "5. Comparar con las hectáreas declaradas", 540,
             {"CHACRAS": C("area", "OUTPUT"), "PUNTOS": P("puntos"), "CAMPO_ID": P("campo_id"),
              "CAMPO_HA": P("campo_ha"), "TOLERANCIA": P("tolerancia")}),
        paso("clima", prov + "clima_gee", "6. Lluvia y temperatura de cada polígono (GEE)", 650,
             {"CHACRAS": C("control", "OUTPUT"), "CAMPO_ID": P("campo_id"), "INICIO": P("inicio"), "FIN": P("fin")}),
        paso("salida", "native:deletecolumn", "7. Polígonos", 760,
             {"INPUT": C("clima", "OUTPUT")}, {"COLUMN": ["fid"]}),
        paso("rasters", prov + "rasters_s2_gee", "9. Rásters Sentinel-2 y clima (GEE) + zonas de búsqueda", 870,
             {"PUNTOS": P("puntos"), "ZONAS": C("zona", "OUTPUT"), "CAMPO_ID": P("campo_id"), "INICIO": P("inicio"),
              "FIN": P("fin")},
             {"CARPETA": trabajo + "/rasters", "APAGAR": gpkg + "|zonas_busqueda"}),
    ]
    for cid, fuente, archivo, y in (("estilo_segmentacion", C("segmentar", "OUTPUT"), "segmentacion", 210),
                                    ("estilo_poligonos", C("salida", "OUTPUT"), "chacras", 760)):
        pasos.append(paso(cid, "native:setlayerstyle", f"8. Estilo: {archivo}", y, {"INPUT": fuente},
                          {"STYLE": config.estilo(archivo)}, x=1150))

    salidas = {
        "Segmentación GEE (polígono crudo)": ("segmentar", "segmentacion"),
        "Polígonos (hectáreas, control, lluvia y temperatura)": ("salida", "poligonos"),
    }
    por_id = {c.childId(): c for c in pasos}
    for nombre, (cid, tabla) in salidas.items():
        c = por_id[cid]
        o = QgsProcessingModelOutput(nombre, nombre)
        o.setChildId(cid)
        o.setChildOutputName("OUTPUT")
        o.setPosition(QPointF(880, c.position().y() + 40))
        o.setDefaultValue(QgsProcessingOutputLayerDefinition(f"ogr:dbname='{gpkg}' table=\"{tabla}\" (geom)"))
        outs = c.modelOutputs()
        outs[nombre] = o
        c.setModelOutputs(outs)
    for c in pasos:
        m.addChildAlgorithm(c)
    ayuda = dict(AYUDA)
    ayuda["ALG_VERSION"] = config.version()
    m.setHelpContent(ayuda)
    return m


class ModeloPuntoAPoligono(QgsProcessingModelAlgorithm):
    """El modelo, con nombre visible propio, que se reconstruye en cada instancia."""

    def __init__(self):
        super().__init__()
        self.loadVariant(armar().toVariant())

    def name(self):
        return "punto_a_poligono"

    def displayName(self):
        return f"Punto a polígono – modelo completo (v{config.version()})"

    def group(self):
        return ""

    def groupId(self):
        return ""

    def createInstance(self):
        return ModeloPuntoAPoligono()
