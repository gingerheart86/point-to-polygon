# Bitácora

Registro del desarrollo en orden cronológico. Cada entrada indica qué se hizo, qué se decidió y por qué, y qué quedó pendiente.

---

## 2026-10-16: Arranque

### Objetivo
Dado un punto georreferenciado dentro de una chacra, obtener automáticamente el polígono del lote, para todo Uruguay.

### Decisiones
- **Sistema de coordenadas:** EPSG:32721 (WGS 84 / UTM 21S). Permite medir superficies en metros y hectáreas sin conversiones.
- **Método:** **padrón catastral + Sentinel-2**.
  1. Se busca el padrón rural (DNC) que contiene el punto.
  2. Dentro del padrón se segmenta el lote con Sentinel-2 en GEE.
  - *Por qué:* cada fuente por separado tiene problemas (ver [README](README.md#método)), y combinadas se compensan.
- **Persistencia:** todas las capas se guardan en GeoPackage con rutas absolutas. Nunca en capas temporales en memoria, porque se pierden al cerrar QGIS.
- **Validación:** se usan polígonos de referencia dibujados a mano, con su punto, como "verdad de campo".

### Hecho
1. Se consiguió un set de referencia de **4 chacras** con punto + polígono dibujado a mano:
   - Superficies de 68 a 287 ha.
   - Los 4 puntos caen **dentro** de su polígono.
   - Datos privados, no incluidos en el repo.
2. Script [`scripts/01_importar_kmz_referencia.py`](scripts/01_importar_kmz_referencia.py): importa un KMZ/KML que mezcla puntos y polígonos a un GeoPackage en EPSG:32721. Separa las geometrías en dos capas (`<prefijo>_puntos` y `<prefijo>_poligonos`).

---

## 2026-10-16: Parcelario rural de Catastro

### Hecho
1. Se descargó **"Total País - Rural"** del conjunto *Shapes del parcelario rural y urbano* (DNC) en catalogodatos.gub.uy:
   - Archivo `paisrural_shp.zip`, 146 MB, versión del 2026-09-09.
   - La primera descarga se cortó en 120 MB; se completó retomándola (`Invoke-WebRequest -Resume`).
2. Características del shape:
   - Ya viene en **EPSG:32721**. Tiene **251.919 polígonos**.
   - Campos: `NOMDEPTO`, `CODDEPTO`, `PADRON`, `SECCAT`, `LAMINA`, `CUADRICULA`, `AREAHA`, `AREAMC`, `VALCAT`.
3. Se convirtió a GeoPackage (capa `padrones_rurales`, MultiPolygon, `makeValid`, índice espacial). Script: [`scripts/02_padrones_rurales_a_gpkg.py`](scripts/02_padrones_rurales_a_gpkg.py).
   - Generarlo en disco local y copiarlo después a la carpeta de red: tarda 23 s.
   - El script de entorno `o4w_env.bat` falló desde PowerShell. Alcanza con definir `PATH`, `GDAL_DATA`, `GDAL_DRIVER_PATH` y `PROJ_LIB` apuntando a la instalación de QGIS.
4. En el set de referencia se encontró **1 polígono inválido** (se autointersecta). Se corrigió con `makeValid`; la superficie casi no cambió (68,2 → 68,3 ha).

### Hallazgos (prueba con las 4 chacras de referencia)
- **Un mismo padrón aparece en varios polígonos separados (fracciones).** Ejemplo: un padrón de 956 ha está dividido en dos piezas, de 170 y 795 ha. Hay que trabajar con la **fracción** que contiene el punto, no con el padrón completo.
- **El padrón solo no sirve como polígono de la chacra.** La superposición con la chacra real (IoU) dio entre **0,12 y 0,25**, porque las fracciones son entre 3 y 8 veces más grandes que la chacra.
- **2 de las 4 chacras cruzan el límite del padrón:** tienen el 25 % y el 53 % de su superficie en el padrón vecino. Si la segmentación se recortara estrictamente al padrón del punto, esas chacras quedarían cortadas.

### Decisión: ajuste del método
**El padrón es una división catastral (jurídica), no geográfica ni agronómica.** Un padrón puede contener varias chacras o pedazos de chacras, y una chacra puede repartirse entre varios padrones, porque se siembra por lotes de manejo y no por límites de propiedad.

- El padrón pasa de ser un **recorte** a ser una **zona de búsqueda**. Se usa la fracción que contiene el punto **más las fracciones vecinas**, o un buffer alrededor.
- El borde de la chacra lo define la **segmentación de Sentinel-2** (crecimiento de región desde el punto), aunque cruce el límite del padrón.
- Los límites del padrón se pueden usar como **dato auxiliar** (un borde probable), pero no como corte obligatorio.

---

## 2026-10-16: Departamentos y secciones catastrales

- Se descargó **"Total País - Secciones Catastrales"** (`paisseccat_shp.zip`, 40 MB, DNC). Tiene 204 secciones en EPSG:32721, con campos `CODDEPTO` y `NUMSECCAT`.
- Capa `secciones_catastrales`: se le agregó el nombre del departamento (`nomdepto`), tomado de la relación `CODDEPTO` ↔ `NOMDEPTO` del parcelario rural.
  - Ojo: DNC usa letras propias para los departamentos (A = Canelones, J = Río Negro, K = Soriano, V = Montevideo…).
- Capa `departamentos`: se armó disolviendo las secciones por departamento. **Quedan 18: Montevideo no está en el shape de secciones.**

---

## 2026-10-16: Segmentación con Sentinel-2 y modelo de QGIS

### Algoritmo (scripts 03 y 04)
1. **Zona de búsqueda** ([`03_zona_busqueda.py`](scripts/03_zona_busqueda.py)): fracción de padrón que contiene el punto + fracciones que la tocan. En la prueba dio entre 2.700 y 3.900 ha.
2. **Segmentación** ([`04_segmentar_s2_gee.py`](scripts/04_segmentar_s2_gee.py)):
   - Datos: Sentinel-2 SR armonizado, con nubes enmascaradas por Cloud Score+ (`cs_cdf ≥ 0,6`).
   - Compuestos **mensuales** de NDVI (mediana) en la temporada: 6 bandas de mayo a octubre.
   - Perfil de la **semilla**: media del stack en 20 m alrededor del punto.
   - Para cada píxel se calcula la **distancia** a ese perfil: RMS de la diferencia de NDVI, suavizada con una mediana de 3×3.
   - Se marcan los píxeles con distancia menor al umbral, se aplica una apertura morfológica de 1 píxel (corta "puentes" finos hacia chacras vecinas) y se vectoriza.
   - Se queda el polígono **conectado al punto**.
   - *Por qué el perfil temporal y no una sola imagen:* dos chacras vecinas con el mismo cultivo pueden verse iguales en una fecha, pero casi siempre difieren en la fecha de siembra o en cómo crecieron.

### Resultados contra la referencia (temporada 2026-05-01 a 2026-10-15; 87 imágenes)
| Umbral | IoU por chacra (4) | Comentario |
|---|---|---|
| 0,05 | 0,07–0,40 | demasiado estricto |
| 0,11 | 0,52–0,75 | |
| **0,15** | **0,54 / 0,65 / 0,83 / 0,86** | buen equilibrio, precision ≈ 0,97 |
| 0,20 | — | una chacra se "fuga" (de 94 a 274 ha) |
| 0,25–0,30 | — | se fuga a chacras vecinas: de 2 a 20 veces la superficie real |

- **Precision ≈ 0,97–1,0:** lo detectado casi nunca está fuera de la chacra real. Lo que falta es *recall*: huecos internos y bordes o colas de la chacra.
- Dos chacras vecinas y angostas, del mismo cultivo, **quedaron separadas** correctamente.
- La segmentación **cruza el límite del padrón** sin problema cuando la chacra lo cruza.
- **Línea base (padrón solo): IoU 0,12–0,25 → con segmentación: 0,54–0,86.**

### Rásters intermedios para revisar visualmente (script 04b)
[`04b_exportar_rasters_gee.py`](scripts/04b_exportar_rasters_gee.py) exporta, para cada zona:
- color real del mes de mayor NDVI,
- NDVI mensual,
- distancia al perfil de la semilla.

Con la distancia en el mapa se ve directamente cómo se decide el polígono.
- *Nota de infraestructura:* algunos servidores de archivos bloquean las extensiones de imagen (`.tif`, `.img`). En ese caso se pueden guardar dentro de un **GeoPackage ráster**: una tabla por banda, con `TILE_FORMAT=TIFF` para los valores flotantes.

### Modelo de QGIS (`modelos/punto_a_poligono.model3`)
Entradas: puntos, campo id, padrones, inicio y fin de temporada, umbral, tamaño de huecos a rellenar.
1. Unir por localización: fracción de padrón que **contiene** cada punto.
2. Unir por localización: fracciones que **tocan** la anterior.
3. Disolver por id → **zona de búsqueda**.
   - 3b. Quitar el campo `fid` que viene de los padrones. Si no se quita, al guardar en GeoPackage aparecen `fid` duplicados y la capa queda vacía *sin dar error*, y el paso 4 falla porque no recibe zonas.
4. **Segmentar con Sentinel-2 (GEE)**: algoritmo de Processing propio, [`scripts/qgis/segmentar_s2_gee_alg.py`](scripts/qgis/segmentar_s2_gee_alg.py), que llama al script 04 en un Python aparte con `earthengine-api`.
5. Rellenar huecos menores a 5 ha.
6. Recalcular la superficie (ha).

**Resultado del modelo completo** (umbral 0,15, huecos < 5 ha rellenados): **IoU 0,66 / 0,88 / 0,90 / 0,54**, precision 0,96–0,99. Las 4 chacras se procesan en ~25 s.

La configuración de cada equipo (ruta del Python de GEE, ruta del script 04, proyecto de Google Cloud, proxy) **no se guarda en el modelo**. Se lee de la configuración de QGIS (`punto_a_poligono/*`), así el `.model3` queda portable.

---

## 2026-10-16: Prueba con bandas B08, B11 y B02

**Idea:** sumar al perfil temporal las bandas que se usan en las composiciones para agricultura (NIR B08, SWIR B11, azul B02), además del NDVI. B11 aporta información de humedad y rastrojo.

**Cómo se probó:**
- Script 04 con `--bandas ndvi,B8,B11,B2`: cada banda va como reflectancia 0–1, en compuestos mensuales.
- La distancia es el RMS sobre las 24 variables (4 por 6 meses).
- Se compara con los huecos < 5 ha ya rellenados.

| Chacra | NDVI solo (umbral 0,15) | NDVI + B08 + B11 + B02 (mejor umbral, 0,10–0,12) |
|---|---|---|
| A (145 ha) | 0,66 | 0,64–0,66 |
| B (287 ha) | **0,88** | 0,83–0,84 |
| C (106 ha) | **0,90** | 0,85–0,90 |
| D (68 ha) | 0,54 | 0,53–0,55 |

**Conclusión:** sumar las bandas **no mejora** la segmentación; da igual o un poco peor. Además deja menos margen: con bandas, la fuga a chacras vecinas empieza en 0,15, y con NDVI solo empieza en 0,25.
- Hay una explicación probable: B02 y B11 varían poco entre fechas en comparación con el NDVI, así que agregan ruido a la distancia sin agregar contraste entre chacras.
- **Se mantiene NDVI solo por defecto.** La opción `--bandas` queda disponible en el script 04.

**Para ver la imagen**, las composiciones en falso color sí son útiles ([`04c_exportar_falso_color_gee.py`](scripts/04c_exportar_falso_color_gee.py)):
- **"Agriculture"** de Copernicus: R:B11 G:B08 B:B02. Vegetación verde intenso; suelo y rastrojo marrón o rosado.
- **R:B08 G:B11 B:B02**. Vegetación roja o naranja; suelo verde o celeste.

En estas composiciones se distinguen a simple vista diferencias de estado entre chacras con el mismo cultivo.

**Mosaicos:** los scripts 04b y 04c exportan un ráster por zona de búsqueda. Como zonas vecinas se superponen casi por completo, quedaban 3 recortes casi iguales del mismo terreno. Se unieron en **un mosaico por composición y por mes de NDVI** (`gdal.BuildVRT` + `gdal.Translate`).

---

## 2026-10-16: Control de hectáreas estimadas contra declaradas

- Nuevo algoritmo [`scripts/qgis/comparar_ha_alg.py`](scripts/qgis/comparar_ha_alg.py) ("Comparar hectáreas estimadas con declaradas"), sumado al modelo como **paso 7**.
- Entradas nuevas del modelo:
  - **Campo de hectáreas declaradas** (opcional, columna de los puntos),
  - **Tolerancia (%)** (por defecto 15).
- Columnas que agrega: `ha_declaradas`, `dif_ha`, `dif_pct`, `control` (OK / REVISAR / SIN DATO). Acepta coma decimal.
- **Por qué es opcional y va dentro de un algoritmo propio:** en los modelos de QGIS no hay "si/entonces". Un paso que dependa de un campo opcional fallaría si el campo no se elige. El algoritmo propio resuelve los dos casos.
- **Prueba:**
  - Sin campo declarado → 4 × SIN DATO.
  - Con las superficies de la referencia como "declaradas" → 2 OK (−7,0 % y −6,6 %) y 2 REVISAR (−29 % y −44 %). Las dos marcadas son justamente las chacras donde el modelo deja afuera partes.
- En el mapa, las chacras se etiquetan con "id - ha".

---

## 2026-10-17: Copiar atributos de los puntos a las chacras

- El modelo tiene un parámetro nuevo, **"Otros campos de los puntos a copiar"** (opcional, varios campos). El paso 7 copia esos campos del punto a su chacra, emparejándolos por identificador.
- **Por qué no se usa "Unir atributos por valor de campo" (`native:joinattributestable`):** en QGIS 3.28 copió los valores **corridos de columna** cuando la capa de puntos venía de un GeoPackage con muchos campos. Por ejemplo, el campo nombre recibía el valor del campo anterior. No da ningún error, así que el problema pasa desapercibido. La unión en código propio evita ese riesgo.
- Lección (se repite con el `fid` del paso 3b): en los modelos que escriben en GeoPackage, conviene quitar `fid` de las capas intermedias y **revisar los valores**, no solo la cantidad de objetos.

---

## 2026-10-17: Compatibilidad con QGIS 3.44

- En QGIS 3.44 el paso 4 fallaba con `ModuleNotFoundError: No module named 'ee'`. **Causa:** QGIS 3.44 define la variable de entorno `PYTHONEXECUTABLE`. Cuando se lanza el Python de un *venv* con esa variable presente, arranca como el Python base y no ve los paquetes del venv.
- **Solución:** antes de lanzar el subproceso, el algoritmo borra `PYTHONHOME`, `PYTHONPATH`, `PYTHONEXECUTABLE` y `__PYVENV_LAUNCHER__`.
- Probado en QGIS 3.28.2 y 3.44.15.

---

## 2026-10-17: Se quita el padrón rural del modelo

**Decisión:** la zona de búsqueda pasa a ser un **círculo alrededor de cada punto** (`native:buffer`), con el parámetro *Radio de búsqueda*, por defecto 3.000 m (≈ 2.800 ha). Ya no se usa el parcelario rural de Catastro.

**Por qué:**
- El padrón solo servía para **acotar** dónde busca Earth Engine. El borde siempre lo definió la segmentación, que además cruzaba los límites del padrón.
- Un círculo de tamaño parecido (las zonas por padrón tenían entre 2.700 y 3.900 ha) cumple la misma función.
- Ya no hace falta descargar ni mantener un parcelario de 252.000 polígonos y 290 MB.
- Saca 4 pasos del modelo (unión con la fracción, unión con las vecinas, disolver y quitar `fid`). Ahora tiene 5 pasos: zona → segmentar → huecos → superficie → control de hectáreas.

Los scripts `02_padrones_rurales_a_gpkg.py` y `03_zona_busqueda.py` quedan en el repo como registro del método anterior, pero el modelo ya no los usa.

**Verificación:** con las mismas 4 chacras de referencia, el modelo con círculo de 3 km dio **el mismo resultado** que con padrones. IoU 0,64 / 0,78 / 0,91 / 0,54, y la diferencia de geometría entre las dos corridas fue de 0,1 ha o menos.

**Nota técnica:** al editar desde Python un paso que contiene un modelo anidado (`model:punto_a_poligono` dentro de otro modelo), QGIS 3.44 se cerró con *access violation*. Pasó al tomar el diccionario de `parameterSources()`, quitarle una entrada y volver a asignarlo con `setParameterSources()`. Para cambiar parámetros de un modelo anidado, conviene **recrear el paso desde cero** o editar el `.model3` como texto o XML.

---

## 2026-10-17: Nuevo criterio de control

- **Tolerancia por defecto: 20 %** (antes 15 %).
- **Controles extra** (parámetro nuevo, opcional): campos de los puntos que ya traen un resultado de control (por ejemplo, si el punto cae en el departamento declarado). Si el valor no empieza con "OK", la chacra pasa a **REVISAR**.
- Columna nueva **`motivo`**: dice por qué una chacra quedó en REVISAR, por ejemplo `ha -43 %; NO COINCIDE (depto_ok)`.
- Criterio: REVISAR si |dif_pct| > tolerancia o si falla un control extra; si no, OK; SIN DATO si no hay hectáreas declaradas.
- Prueba con las 4 chacras de referencia: con 20 %, la chacra con −15,9 % pasa de REVISAR a OK. Las de −32 % y −43 % siguen en REVISAR.
- **Nota técnica:** QGIS 3.44 se volvió a cerrar al quitar y volver a agregar un parámetro de un modelo con `removeModelParameter()` y `addModelParameter()` desde Python. A partir de ahora, **los modelos se editan como texto (XML) con QGIS cerrado o sin recargarlos**, y se valida el XML antes de copiarlos.

---

## 2026-10-20: Rásters de Sentinel-2 dentro del flujo

- Script nuevo [`scripts/04d_rasters_zonas_gee.py`](scripts/04d_rasters_zonas_gee.py). Las zonas de búsqueda que se tocan se **agrupan** y se exporta una imagen por grupo:
  - NDVI por período (multibanda);
  - color real;
  - falso color R:B08 G:B11 B:B02;
  - "Agriculture" (R:B11 G:B08 B:B02);
  - la **distancia** de cada punto a su perfil.
  
  Si una descarga es demasiado grande, se reintenta a 20 m y después a 40 m.
- Algoritmo nuevo [`scripts/qgis/rasters_s2_gee_alg.py`](scripts/qgis/rasters_s2_gee_alg.py) ("Rásters Sentinel-2 de las zonas (GEE)"):
  - llama al 04d y pasa los GeoTIFF a un **GeoPackage ráster nuevo por corrida**;
  - los carga con estilo en el grupo "Sentinel-2 (GEE)", **al fondo del panel**. Solo queda prendido el falso color; el NDVI y las distancias quedan apagados.
  - Lo hace con `QgsProcessingContext.LayerDetails` (`groupName`, `layerSortKey`) y un post-procesador que pone el nombre y la visibilidad.
- Esto reemplaza en la práctica a los scripts 04b y 04c, que exportaban una imagen por zona.

---

## 2026-10-22: Plugin de QGIS "Punto a Polígono" v1.0.0

- Todo el método quedó empaquetado como **plugin de QGIS** en [`punto_a_poligono/`](punto_a_poligono/), para publicarlo en el repositorio oficial de complementos (plugins.qgis.org), con licencia **GPL-2.0 o posterior**. Empieza como *experimental*.
- Lo que trae:
  - **Configurar** (una vez por PC): Python con earthengine-api, proyecto de Earth Engine, proxy y carpeta de trabajo. Prueba la conexión.
  - **Modelo completo** "Punto a polígono", que se construye en código (`modelo.py`) cada vez que carga el plugin: zona de búsqueda → segmentación Sentinel-2 en GEE → rellenar huecos → hectáreas → comparación con las declaradas (opcional) → **lluvia y temperatura** → estilos → rásters.
  - Las piezas sueltas: segmentar, comparar hectáreas, lluvia y temperatura, rásters.
- **Lluvia y temperatura** (script nuevo `gee/04e_clima_chacras_gee.py`), sobre el polígono de cada chacra y para la temporada: CHIRPS v3 diario (acumulada y promedio diario), Landsat 8/9 C2 L2 banda ST_B10 a 30 m (media, máxima, mínima y cantidad de escenas sin nubes) y ERA5-Land diario (temperatura de piel y de suelo 0–7 cm).
- La entrada es **cualquier capa de puntos** con un campo identificador, en cualquier sistema de coordenadas. Ya no hace falta un CSV con un formato fijo.
- Prueba con los 4 puntos de referencia (temporada 2026-05-01 → 2026-10-21): los mismos polígonos de antes (99,3 / 236,7 / 100,0 / 37,5 ha). Lluvia de 385 mm, con las 4 chacras en el mismo píxel de CHIRPS. Temperatura de superficie media de 15,6 a 16,7 °C, con 18 a 21 escenas. Tardó 5,4 min.
- Los scripts de `scripts/` y el modelo de `modelos/` quedan como historia del desarrollo: el plugin los reemplaza.

### Pendiente
- [ ] Subir a GitHub y publicar en plugins.qgis.org (cuenta OSGeo).
- [ ] Ícono del plugin (`icon.png`).
- [ ] Scripts 04b y 04c: exportar **una sola vez la unión de las zonas**, en lugar de una imagen por zona.
- [ ] Mejorar el *recall*: rellenar huecos (ya está en el modelo), probar compuestos quincenales, sumar bandas SWIR y bordes (caminos, alambrados).
- [ ] Probar en otras zonas y cultivos (verano: soja, maíz).
- [ ] Datos de ejemplo **públicos** (puntos de prueba sin información privada) para que el repo se pueda probar.
