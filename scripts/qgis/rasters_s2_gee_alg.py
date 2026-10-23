"""Algoritmo de Processing de QGIS: "Rásters Sentinel-2 de las zonas (GEE)".

Descarga de Google Earth Engine los rásters con los que se decide el polígono de cada chacra
(script 04d_rasters_zonas_gee.py), los guarda en un GeoPackage ráster y los carga en el
proyecto, en el grupo "Sentinel-2 (GEE)":
  - Color real y falso color para agricultura R:B08 G:B11 B:B02
  - NDVI de cada período (apagados; se prenden de a uno)
  - Distancia de cada chacra al perfil de su punto (verde = se comporta igual; apagadas)
El grupo queda al fondo del panel de capas, debajo de los polígonos. Solo el falso color
R:B08 G:B11 B:B02 queda prendido.

Las zonas que se tocan se exportan juntas (una imagen por grupo), para no repetir terreno.
Los rásters se guardan en un GeoPackage (y no en .tif) porque algunos servidores de archivos
bloquean las extensiones de imagen. Cada corrida crea un GeoPackage nuevo, con fecha y hora
en el nombre, dentro de la carpeta elegida.

Usa la misma configuración de QGIS que "Segmentar chacras con Sentinel-2 (GEE)":
punto_a_poligono/python_gee, script_04 (04d se busca en la misma carpeta), proyecto_gee y proxy.
La carpeta de salida por defecto se toma de punto_a_poligono/carpeta_rasters.
"""
import datetime
import glob
import json
import os
import shutil
import subprocess
import tempfile

from osgeo import gdal
from qgis.core import (
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingOutputFile,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSettings,
    QgsSingleBandPseudoColorRenderer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
GRUPO = "Sentinel-2 (GEE)"
_POST = []  # mantiene vivos los post-procesadores hasta que QGIS los usa


def _conf(clave, defecto=""):
    return QgsSettings().value(f"punto_a_poligono/{clave}", defecto) or defecto


class _Post(QgsProcessingLayerPostProcessorInterface):
    """Al cargar cada ráster: le pone nombre, lo prende o apaga, y deja el grupo "Sentinel-2 (GEE)"
    al fondo del panel de capas (debajo de los polígonos), con "Departamentos" justo encima."""

    def __init__(self, nombre, visible, al_fondo=True):
        super().__init__()
        self.nombre, self.visible, self.al_fondo = nombre, visible, al_fondo

    def postProcessLayer(self, layer, context, feedback):
        layer.setName(self.nombre)
        raiz = QgsProject.instance().layerTreeRoot()
        nodo = raiz.findLayer(layer.id())
        if nodo:
            nodo.setItemVisibilityChecked(self.visible)
        if not self.al_fondo:
            return
        for nombre in ("Departamentos", GRUPO):  # mover al fondo, en este orden
            n = raiz.findGroup(nombre) if nombre == GRUPO else next(
                (x for x in raiz.children() if x.name() == nombre and x.nodeType() == 1), None)
            if n is not None and n.parent() is raiz and raiz.children()[-1] is not n:
                clon = n.clone()
                raiz.addChildNode(clon)
                raiz.removeChildNode(n)


def _estilo_ndvi(capa):
    sh = QgsColorRampShader(0, 0.9)
    sh.setColorRampType(QgsColorRampShader.Interpolated)
    sh.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c)) for v, c in
                             [(0, "#a50026"), (0.3, "#fdae61"), (0.5, "#ffffbf"), (0.7, "#a6d96a"), (0.9, "#006837")]])
    s = QgsRasterShader()
    s.setRasterShaderFunction(sh)
    capa.setRenderer(QgsSingleBandPseudoColorRenderer(capa.dataProvider(), 1, s))


def _estilo_distancia(capa):
    sh = QgsColorRampShader()
    sh.setColorRampType(QgsColorRampShader.Discrete)
    sh.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), t) for v, c, t in
                             [(0.11, "#1a9641", "< 0.11"), (0.15, "#a6d96a", "0.11-0.15"),
                              (0.20, "#ffffbf", "0.15-0.20"), (0.25, "#fdae61", "0.20-0.25"),
                              (9, "#d7191c", "> 0.25")]])
    s = QgsRasterShader()
    s.setRasterShaderFunction(sh)
    r = QgsSingleBandPseudoColorRenderer(capa.dataProvider(), 1, s)
    r.setOpacity(0.75)
    capa.setRenderer(r)


class RastersS2GEE(QgsProcessingAlgorithm):
    PUNTOS, CAMPO_ID, ZONAS, INICIO, FIN, CARPETA, PROYECTO, PROXY, APAGAR, OUTPUT = (
        "PUNTOS", "CAMPO_ID", "ZONAS", "INICIO", "FIN", "CARPETA", "PROYECTO", "PROXY", "APAGAR", "OUTPUT")

    def name(self):
        return "rasters_s2_gee"

    def displayName(self):
        return "Rásters Sentinel-2 de las zonas (GEE)"

    def group(self):
        return "Punto a polígono"

    def groupId(self):
        return "punto_a_poligono"

    def shortHelpString(self):
        return ("Descarga de Earth Engine el color real, los falsos colores, el NDVI de cada período y la "
                "distancia de cada chacra al perfil de su punto, para las zonas de búsqueda. Los guarda en un "
                "GeoPackage nuevo dentro de la carpeta elegida y los carga en el grupo 'Sentinel-2 (GEE)'.")

    def createInstance(self):
        return RastersS2GEE()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PUNTOS, "Puntos de las chacras", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.CAMPO_ID, "Campo identificador", parentLayerParameterName=self.PUNTOS))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ZONAS, "Zonas de búsqueda (con el mismo campo identificador)", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterString(self.INICIO, "Inicio de la temporada (AAAA-MM-DD)", "2026-05-01"))
        self.addParameter(QgsProcessingParameterString(self.FIN, "Fin de la temporada (AAAA-MM-DD)", "2026-10-15"))
        self.addParameter(QgsProcessingParameterFile(
            self.CARPETA, "Carpeta donde guardar el GeoPackage de rásters",
            behavior=QgsProcessingParameterFile.Folder, defaultValue=_conf("carpeta_rasters", tempfile.gettempdir())))
        self.addParameter(QgsProcessingParameterString(
            self.PROYECTO, "Proyecto de Google Cloud (Earth Engine)", _conf("proyecto_gee"), optional=True))
        self.addParameter(QgsProcessingParameterString(self.PROXY, "Proxy HTTP(S) (opcional)", _conf("proxy"), optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.APAGAR, "Guardar y cargar las zonas (apagadas) en: ruta.gpkg|tabla (opcional)",
            optional=True))
        self.addOutput(QgsProcessingOutputFile(self.OUTPUT, "GeoPackage de rásters"))

    def _geojson(self, feats, ruta):
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)

    def processAlgorithm(self, parameters, context, feedback):
        puntos = self.parameterAsSource(parameters, self.PUNTOS, context)
        zonas = self.parameterAsSource(parameters, self.ZONAS, context)
        campo = self.parameterAsString(parameters, self.CAMPO_ID, context)
        inicio = self.parameterAsString(parameters, self.INICIO, context)
        fin = self.parameterAsString(parameters, self.FIN, context)
        carpeta = self.parameterAsFile(parameters, self.CARPETA, context)
        proyecto = self.parameterAsString(parameters, self.PROYECTO, context) or _conf("proyecto_gee")
        proxy = self.parameterAsString(parameters, self.PROXY, context) or _conf("proxy")
        guardar_zonas = (self.parameterAsString(parameters, self.APAGAR, context) or "").strip()
        python = _conf("python_gee", "python")
        script = os.path.join(os.path.dirname(_conf("script_04")), "04d_rasters_zonas_gee.py")
        if not os.path.exists(script):
            raise QgsProcessingException(f"No encuentro el script 04d: {script}")

        tmp = tempfile.mkdtemp(prefix="rasters_s2_")
        entrada, salida = os.path.join(tmp, "entrada"), os.path.join(tmp, "tif")
        os.makedirs(entrada)
        trp = QgsCoordinateTransform(puntos.sourceCrs(), WGS84, QgsProject.instance())
        trz = QgsCoordinateTransform(zonas.sourceCrs(), WGS84, QgsProject.instance())

        def feat(g, tr, props):
            g = QgsGeometry(g)
            g.transform(tr)
            return {"type": "Feature", "properties": props, "geometry": json.loads(g.asJson(7))}

        self._geojson([feat(f.geometry(), trp, {"id": str(f[campo])}) for f in puntos.getFeatures()],
                      os.path.join(entrada, "puntos.geojson"))
        geoms = [(str(f[campo]), f.geometry()) for f in zonas.getFeatures()]
        self._geojson([feat(g, trz, {"id": k}) for k, g in geoms], os.path.join(entrada, "zonas.geojson"))
        union = QgsGeometry.unaryUnion([g for _, g in geoms])
        partes = union.asGeometryCollection() if union.isMultipart() else [union]
        self._geojson([feat(p, trz, {"grupo": i + 1}) for i, p in enumerate(partes)],
                      os.path.join(entrada, "grupos.geojson"))
        feedback.pushInfo(f"{len(geoms)} zonas en {len(partes)} grupo(s). Descargando de Earth Engine...")

        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        for v in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__"):
            env.pop(v, None)
        if proxy:
            env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
        cmd = [python, "-I", "-u", script, entrada, salida, inicio, fin] + ([proyecto] if proyecto else [])
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for linea in proc.stdout:
            feedback.pushInfo(linea.rstrip())
            if feedback.isCanceled():
                proc.kill()
                return {}
        if proc.wait() != 0:
            raise QgsProcessingException("Falló la descarga de rásters de Earth Engine (ver el registro)")

        # GeoTIFF → GeoPackage ráster (una tabla por banda/imagen), primero en local y después se copia
        fechas = open(os.path.join(salida, "fechas.txt")).read().split()
        local = os.path.join(tmp, "rasters.gpkg")
        capas = []  # (tabla, nombre en el mapa, tipo)

        def agregar(src, tabla, banda=None, flotante=False):
            opciones = [f"RASTER_TABLE={tabla}", "APPEND_SUBDATASET=YES"] + (["TILE_FORMAT=TIFF"] if flotante else [])
            gdal.Translate(local, src, format="GPKG", creationOptions=opciones,
                           bandList=[banda] if banda else None, noData=None if flotante else 0)

        for ruta in sorted(glob.glob(os.path.join(salida, "g*_ndvi.tif"))):
            g = os.path.basename(ruta).split("_")[0]
            for b, f in enumerate(fechas, start=1):
                t = f"{g}_ndvi_{f.replace('-', '')}"
                agregar(ruta, t, b, True)
                capas.append((t, f"NDVI {f} ({g})", "ndvi"))
        for tipo, nombre in (("rgb", "Color real"), ("nir_swir", "Falso color R:B08 G:B11 B:B02")):
            for ruta in sorted(glob.glob(os.path.join(salida, f"g*_{tipo}.tif"))):
                g = os.path.basename(ruta).split("_")[0]
                agregar(ruta, f"{g}_{tipo}")
                capas.append((f"{g}_{tipo}", f"{nombre} ({g})", tipo))
        for ruta in sorted(glob.glob(os.path.join(salida, "dist_*.tif"))):
            t = os.path.basename(ruta)[:-4]
            agregar(ruta, t, None, True)
            capas.append((t, f"Distancia {t[5:]}", "dist"))

        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, f"rasters_{datetime.datetime.now():%Y%m%d_%H%M%S}.gpkg")
        shutil.copy(local, destino)
        feedback.pushInfo(f"Rásters guardados en {destino}")

        # carga en el proyecto, dentro del grupo "Sentinel-2 (GEE)". Orden de arriba a abajo:
        # distancias (apagadas), falso color B08-B11-B02 (prendido), Agriculture, color real, NDVI (apagados)
        orden = {"dist": 0, "nir_swir": 1, "rgb": 3, "ndvi": 4}
        prendidas = {"nir_swir"}
        for i, (t, nombre, tipo) in enumerate(sorted(capas, key=lambda c: (orden[c[2]], c[0]))):
            capa = QgsRasterLayer(f"GPKG:{destino}:{t}", nombre, "gdal")
            if not capa.isValid():
                feedback.reportError(f"No se pudo abrir {t}")
                continue
            if tipo == "ndvi":
                _estilo_ndvi(capa)
            elif tipo == "dist":
                _estilo_distancia(capa)
            context.temporaryLayerStore().addMapLayer(capa)
            det = QgsProcessingContext.LayerDetails(nombre, context.project(), self.OUTPUT)
            det.groupName = GRUPO
            det.layerSortKey = 1000 - i  # clave más alta = más arriba en el grupo
            post = _Post(nombre, tipo in prendidas)
            _POST.append(post)
            det.setPostProcessor(post)
            context.addLayerToLoadOnCompletion(capa.id(), det)
        # zonas de búsqueda: se guardan y se cargan APAGADAS (son de control). Si la tabla tiene un
        # estilo por defecto guardado en el GeoPackage, QGIS lo aplica al abrirla.
        if guardar_zonas and "|" in guardar_zonas:
            gpkg, tabla = (x.strip() for x in guardar_zonas.split("|", 1))
            zl = self.parameterAsVectorLayer(parameters, self.ZONAS, context)
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName, opts.layerName = "GPKG", tabla
            opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
            err = QgsVectorFileWriter.writeAsVectorFormatV3(zl, gpkg, context.transformContext(), opts)
            if err[0] != QgsVectorFileWriter.NoError:
                feedback.reportError(f"No se pudieron guardar las zonas: {err[1]}")
            else:
                capa = QgsVectorLayer(f"{gpkg}|layername={tabla}", "Zonas de búsqueda", "ogr")
                context.temporaryLayerStore().addMapLayer(capa)
                det = QgsProcessingContext.LayerDetails("Zonas de búsqueda", context.project(), "ZONAS")
                post = _Post("Zonas de búsqueda", False, al_fondo=False)
                _POST.append(post)
                det.setPostProcessor(post)
                context.addLayerToLoadOnCompletion(capa.id(), det)
        shutil.rmtree(tmp, ignore_errors=True)
        return {self.OUTPUT: destino}
