"""Algoritmo de Processing de QGIS: "Comparar hectáreas estimadas con declaradas".

Toma los polígonos de chacras (salida del modelo, con el campo area_ha) y les agrega, desde
la capa de puntos, las hectáreas declaradas de cada chacra:
    ha_declaradas  hectáreas declaradas (del campo elegido en los puntos)
    dif_ha         area_ha - ha_declaradas
    dif_pct        dif_ha / ha_declaradas * 100
    control        REVISAR  si |dif_pct| > tolerancia (por defecto 20 %)
                            o si falla alguno de los controles extra
                   OK       si no
                   SIN DATO si no hay hectáreas declaradas (y no falla ningún control extra)
    motivo         por qué se marcó REVISAR, por ejemplo "ha -43 %; FUERA (control_zona)"

Controles extra (opcional): uno o más campos de los puntos que ya tienen un resultado de
control propio del usuario. Si el valor del campo no empieza con "OK", la chacra
queda en REVISAR y el valor se agrega al motivo.

Si no se elige un campo de hectáreas declaradas, ha_declaradas, dif_ha y dif_pct quedan
vacíos. Por eso puede ir siempre en el modelo.

Opcionalmente copia a cada chacra otros campos de su punto (CAMPOS_COPIAR). La unión se
hace por identificador, en código propio, para no depender de "Unir atributos por valor de
campo": en QGIS 3.28 esa herramienta puede correr las columnas cuando hay muchos campos.
"""
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QVariant


def _num(v):
    """Convierte a float; acepta coma decimal ('145,2'). Devuelve None si no se puede."""
    if v is None:
        return None
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def _es_ok(v):
    """Un control extra está bien si su valor empieza con 'OK' (o está vacío)."""
    if v is None or str(v).strip() == "" or str(v) == "NULL":
        return True
    return str(v).strip().upper().startswith("OK")


class CompararHa(QgsProcessingAlgorithm):
    CHACRAS, PUNTOS, CAMPO_ID, CAMPO_HA, TOLERANCIA, CONTROLES, CAMPOS_COPIAR, OUTPUT = (
        "CHACRAS", "PUNTOS", "CAMPO_ID", "CAMPO_HA", "TOLERANCIA", "CONTROLES", "CAMPOS_COPIAR", "OUTPUT")

    def name(self):
        return "comparar_ha"

    def displayName(self):
        return "Comparar hectáreas estimadas con declaradas"

    def group(self):
        return "Piezas del modelo"

    def groupId(self):
        return "piezas"

    def shortHelpString(self):
        return ("Agrega a cada chacra las hectáreas declaradas (tomadas de los puntos), la diferencia en ha "
                "y en %, y las columnas 'control' y 'motivo'. control = REVISAR si la diferencia supera la "
                "tolerancia (por defecto 20 %) o si alguno de los controles extra elegidos (campos de "
                "los puntos con valor OK / otro) no es OK; si no, OK. Sin hectáreas declaradas: SIN DATO.")

    def createInstance(self):
        return CompararHa()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CHACRAS, "Chacras (con area_ha)", [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PUNTOS, "Puntos de las chacras", [QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_ID, "Campo identificador", parentLayerParameterName=self.PUNTOS))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_HA, "Campo de hectáreas declaradas (opcional)",
            parentLayerParameterName=self.PUNTOS, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOLERANCIA, "Tolerancia (%)", QgsProcessingParameterNumber.Type.Double, 20, minValue=0))
        self.addParameter(QgsProcessingParameterField(
            self.CONTROLES, "Controles extra: campos de los puntos que deben ser OK (opcional)",
            parentLayerParameterName=self.PUNTOS, allowMultiple=True, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPOS_COPIAR, "Otros campos de los puntos a copiar (opcional)",
            parentLayerParameterName=self.PUNTOS, allowMultiple=True, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "Chacras con control de ha"))

    def processAlgorithm(self, parameters, context, feedback):
        chacras = self.parameterAsSource(parameters, self.CHACRAS, context)
        puntos = self.parameterAsSource(parameters, self.PUNTOS, context)
        campo_id = self.parameterAsString(parameters, self.CAMPO_ID, context)
        campo_ha = self.parameterAsString(parameters, self.CAMPO_HA, context)
        tol = self.parameterAsDouble(parameters, self.TOLERANCIA, context)
        nombres_pts = puntos.fields().names()
        pedidos = [c for c in self.parameterAsFields(parameters, self.CONTROLES, context) if c] + \
                  list(self.parameterAsFields(parameters, self.CAMPOS_COPIAR, context))
        faltan = sorted({c for c in pedidos if c not in nombres_pts})
        if faltan:  # el CSV puede no traer todas las columnas: se omiten y se avisa
            feedback.pushWarning("Campos que no están en los puntos y se omiten: " + ", ".join(faltan))
        controles = [c for c in self.parameterAsFields(parameters, self.CONTROLES, context) if c in nombres_pts]
        copiar = [c for c in self.parameterAsFields(parameters, self.CAMPOS_COPIAR, context)
                  if c in nombres_pts and c not in (campo_id, "fid")]

        declaradas, extra, ctrl = {}, {}, {}
        for p in puntos.getFeatures():
            k = str(p[campo_id])
            if campo_ha:
                declaradas[k] = _num(p[campo_ha])
            extra[k] = {c: p[c] for c in copiar}
            ctrl[k] = {c: p[c] for c in controles}

        campos = chacras.fields()
        for n, t in (("ha_declaradas", QVariant.Double), ("dif_ha", QVariant.Double),
                     ("dif_pct", QVariant.Double), ("control", QVariant.String), ("motivo", QVariant.String)):
            if campos.indexOf(n) < 0:
                campos.append(QgsField(n, t))
        for c in copiar:
            if campos.indexOf(c) < 0:
                campos.append(QgsField(puntos.fields().field(c)))
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context, campos,
                                          chacras.wkbType(), chacras.sourceCrs())
        n_rev = 0
        for f in chacras.getFeatures():
            k = str(f[campo_id])
            est = _num(f["area_ha"])
            dec = declaradas.get(k)
            motivos = []
            if dec and est is not None:
                dif = round(est - dec, 1)
                pct = round(100 * dif / dec, 1)
                if abs(pct) > tol:
                    motivos.append(f"ha {pct:+.0f} %")
            else:
                dif = pct = None
            for c, v in ctrl.get(k, {}).items():
                if not _es_ok(v):
                    motivos.append(f"{v} ({c})")
            if motivos:
                control = "REVISAR"
                n_rev += 1
            elif dec and est is not None:
                control = "OK"
            else:
                control = "SIN DATO"
            o = QgsFeature(campos)
            o.setGeometry(f.geometry())
            attrs = dict(zip(f.fields().names(), f.attributes()))
            attrs.update(ha_declaradas=dec, dif_ha=dif, dif_pct=pct, control=control,
                         motivo="; ".join(motivos) or None)
            attrs.update(extra.get(k, {}))
            o.setAttributes([attrs.get(n) for n in campos.names()])
            sink.addFeature(o, QgsFeatureSink.Flag.FastInsert)
        feedback.pushInfo(f"{n_rev} chacras en REVISAR (diferencia de ha > {tol:g} %"
                          + (f" o {', '.join(controles)} distinto de OK" if controles else "") + ")")
        return {self.OUTPUT: dest}
