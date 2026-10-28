# Manual de uso: plugin "Punto a Polígono" para QGIS

A partir de **un punto dentro de cada chacra**, dibuja el **polígono del lote** con la serie temporal de NDVI de Sentinel-2 en Google Earth Engine. Además calcula las hectáreas, las compara con las declaradas (si las hay) y agrega la **lluvia** y la **temperatura** de la temporada.

---

## 1. Instalación (una vez por PC)

### 1.1 Requisitos de la PC
1. **QGIS 3.28 o posterior** (también QGIS 4). Probado en 3.28 y 3.44.
2. **Python con la librería `earthengine-api`**, aparte del Python de QGIS (paso a paso en 1.2).
3. **Un proyecto de Google Earth Engine** al que tu cuenta de Google tenga acceso (paso a paso en 1.2).
4. **Salida a internet hacia Google** (`*.googleapis.com`): directa o por el proxy de la red.

### 1.2 Paso a paso: Python y Earth Engine
Se hace **una sola vez por PC** y lleva unos 15 minutos. Los comandos se escriben en el **Símbolo del sistema**: tecla Windows, escribir `cmd` y Enter. En cada comando, copiá la línea entera y apretá Enter.

**Paso 1. Instalar Python** (si ya está instalado, saltear)
1. Entrar a **python.org/downloads** y bajar el instalador de Windows (botón *Download Python 3.x*).
2. Abrirlo, tildar **"Add python.exe to PATH"** y tocar **Install Now**. No hace falta ser administrador.
3. Para comprobar, en el Símbolo del sistema:
   - `py --version` tiene que mostrar algo como `Python 3.12.x`.

**Paso 2. Crear el entorno "gee" e instalar earthengine-api**
1. Si la red usa **proxy**, primero avisarle a Python (cambiar por el proxy de tu red; si no hay proxy, saltear):
   - `set HTTPS_PROXY=http://proxy.empresa:8080`
   - `set HTTP_PROXY=http://proxy.empresa:8080`
2. Crear el entorno, que es una carpeta con un Python propio para Earth Engine:
   - `py -m venv %USERPROFILE%\.venvs\gee`
3. Instalar las librerías (tarda 1 o 2 minutos):
   - `%USERPROFILE%\.venvs\gee\Scripts\python -m pip install earthengine-api requests pip-system-certs`
   - `pip-system-certs` hace que Python use los certificados de Windows; hace falta si el proxy inspecciona SSL.
4. Queda instalado en `C:\Users\<tu usuario>\.venvs\gee\Scripts\python.exe`. Esa es la ruta que se pone en *Configurar* (1.4).

**Paso 3. Conseguir el proyecto de Earth Engine**

Earth Engine trabaja dentro de un **proyecto de Google Cloud**. Hay dos caminos:
- **Usar un proyecto que ya existe** (por ejemplo, el de tu equipo): pedirle al dueño que te agregue en **console.cloud.google.com → IAM y administración → IAM → Otorgar acceso**, con tu mail de Google y los roles **"Earth Engine Resource Writer"** y **"Service Usage Consumer"**. Después pedile el **ID del proyecto**.
- **Crear uno propio:**
  1. Entrar a **code.earthengine.google.com/register** con tu cuenta de Google.
  2. Elegir el tipo de uso. El uso no comercial (investigación, educación, gobierno, ONG) es gratis; el comercial requiere una cuenta paga.
  3. Elegir **"Create a new Google Cloud Project"**. Te propone un ID como `ee-tuusuario`; aceptarlo o cambiarlo.
  4. Terminar el registro. Earth Engine queda habilitado en ese proyecto.

**Dónde ver el ID del proyecto:** en **console.cloud.google.com**, en el selector de proyecto de arriba a la izquierda. Usar la columna **ID** (por ejemplo `ee-tuusuario` o `mi-proyecto-123456`), **no el nombre**.

**Paso 4. Autenticarse** (vincular la PC con tu cuenta de Google)
1. En el Símbolo del sistema (si hay proxy, repetir antes los dos `set` del paso 2):
   - `%USERPROFILE%\.venvs\gee\Scripts\earthengine authenticate`
2. Se abre el navegador: elegir la cuenta de Google que tiene acceso al proyecto y aceptar los permisos.
3. Cuando el navegador dice que terminó, cerrar la pestaña. En el Símbolo del sistema aparece *Successfully saved authorization token*.
4. Si el navegador no se abre, copiar el enlace que aparece en el Símbolo del sistema y pegarlo en el navegador.

La autenticación dura mucho tiempo. Si un día Earth Engine dice que las credenciales vencieron, repetir solo el paso 4.

### 1.3 Instalar el plugin
1. En QGIS: **Complementos → Administrar e instalar complementos → Todos**, buscar **"Punto a Polígono"** e instalar.
   - Mientras sea experimental: en *Configuración*, tildar **"Mostrar también los complementos experimentales"**.
   - También se puede instalar el `.zip` de la sección **Releases** del repositorio con *Instalar desde ZIP*.
2. Aparece el menú **Complementos → Punto a polígono** y, en la Caja de herramientas de Procesos, el grupo **Punto a polígono**.

### 1.4 Configurar (una vez por PC)
**Complementos → Punto a polígono → Configurar (una vez por PC)…**

| Parámetro | Qué poner |
|---|---|
| Python con earthengine-api | `C:\Users\<tu usuario>\.venvs\gee\Scripts\python.exe` (paso 2 de 1.2) |
| Proyecto de Google Cloud | el **ID** del proyecto de Earth Engine (paso 3 de 1.2) |
| Proxy | el de la red, ej. `http://proxy.empresa:8080`. Vacío si no hay |
| Carpeta de trabajo | dónde se guardan resultados y rásters |

Al ejecutarlo, **prueba la conexión con Earth Engine**. Si en el registro aparece **"Earth Engine OK"**, está todo listo. Si falla, ver la sección 4.

---

## 2. Uso

1. Tener en el mapa una **capa de puntos**, uno dentro de cada chacra, con un **campo identificador único**. Puede venir de un CSV (*Capa → Añadir capa → Añadir capa de texto delimitado*), de un GPS o dibujada a mano. Cualquier sistema de coordenadas.
2. **Complementos → Punto a polígono → Ejecutar el modelo punto → polígono…**
3. Completar:

| Parámetro | Qué poner | Ejemplo |
|---|---|---|
| **Puntos** | la capa de puntos | |
| **Campo identificador** | el campo que identifica cada punto | `id`, `chacra` |
| **Campo de hectáreas declaradas** (opcional) | si lo hay, para comparar | `ha` |
| **Inicio / Fin de la temporada** | tienen que cubrir el ciclo del cultivo | invierno: 1/5 → 31/12 · verano: 1/10 → 31/5 |
| *Avanzados* | umbral (0,15), tolerancia (20 %), radio (3000 m), huecos (5 ha) | dejar los valores por defecto |

4. **Ejecutar.** Cada punto tarda de 20 a 40 segundos en Earth Engine; la lluvia y la temperatura, de 10 a 30 segundos más en total; los rásters, de 30 a 90 segundos.

### Qué genera

| Capa | Qué es | Cómo se ve |
|---|---|---|
| **`poligonos`** | **El resultado final:** un polígono por punto, con los huecos chicos rellenados, `area_ha`, la comparación con lo declarado (`ha_declaradas`, `dif_pct`, `control`, `motivo`) y la lluvia y temperatura | contorno verde (OK), rojo (REVISAR) o gris (SIN DATO), con etiqueta |
| **`segmentacion`** | El polígono "crudo" que devuelve Earth Engine, antes de rellenar huecos. Sirve para ver qué partes de la chacra se comportaron distinto del punto | punteado celeste |
| Zonas de búsqueda | El círculo donde buscó Earth Engine (solo control) | apagada |
| Grupo **Sentinel-2 (GEE)** | Falso color R:B08 G:B11 B:B02 (prendido), color real, NDVI por período y distancia de cada punto (apagados) | al fondo |
| Grupo **Lluvia y temperatura (GEE)** | Lluvia acumulada (CHIRPS), temperatura de superficie (Landsat) y de piel (ERA5-Land) de la zona | apagados, al fondo |

**Archivos en la carpeta de trabajo:** `punto_a_poligono.gpkg` (se reemplaza en cada corrida: para conservar una, cambiá el nombre de la salida) y `rasters\rasters_<fecha>.gpkg`.

---

## 3. Cómo leer el resultado

### Control (si se eligió el campo de hectáreas)
- **REVISAR**: la diferencia entre las hectáreas estimadas y las declaradas supera la **tolerancia** (20 %). La columna `motivo` lo dice, por ejemplo `ha -43 %`.
- **OK**: dentro de la tolerancia. **SIN DATO**: no hay hectáreas declaradas.

| Situación | Posible causa | Qué hacer |
|---|---|---|
| Estimado **menor** | parte de la chacra se comporta distinto (daño, encharcamiento, resiembra) | mirar en el falso color y en el NDVI qué zona quedó afuera |
| Estimado **mayor** | el polígono se pasó a una chacra vecina con el mismo cultivo y la misma siembra | volver a correr con umbral 0,12 |
| "No se encontró chacra conectada al punto" | el punto cae en un camino, un monte o un borde | mover el punto adentro del cultivo |

### Lluvia y temperatura

| Campo | Qué es | Fuente y resolución |
|---|---|---|
| `precip_acum_mm` | lluvia **acumulada** del período (mm) | CHIRPS v3 diario, ~5,5 km |
| `precip_media_mm_dia` | lluvia **promedio diaria** (mm/día) | CHIRPS v3 |
| `precip_dias`, `precip_hasta` | días con dato y hasta qué fecha (CHIRPS sale con ~3 semanas de atraso) | CHIRPS v3 |
| `lst_media_c`, `lst_max_c`, `lst_min_c` | **temperatura de superficie** (°C) de las escenas sin nubes | Landsat 8/9 C2 L2, ST_B10, **30 m** |
| `lst_escenas` | cantidad de escenas Landsat sin nubes | Landsat 8/9 |
| `era5_piel_media_c`, `era5_piel_max_c` | temperatura de piel (superficie del suelo o del cultivo): media y máxima del período (°C) | ERA5-Land diario, ~11 km |
| `era5_suelo_media_c` | temperatura del suelo de 0 a 7 cm (°C) | ERA5-Land |

- **Landsat** tiene el detalle espacial (30 m) pero solo cuenta las pasadas sin nubes, de día.
- **ERA5-Land** es continua (todos los días) pero con píxel de ~11 km: chacras cercanas dan el mismo valor.
- **CHIRPS** combina satélite y pluviómetros, con píxel de ~5,5 km: no ve una tormenta muy localizada.

### Conceptos
- **Cómo se dibuja la chacra:** para cada píxel de 10 m se arma la **historia de NDVI** de la temporada (un valor por mes). El polígono es el conjunto de píxeles **conectados al punto** que tuvieron **la misma historia** que el punto: la misma siembra y el mismo crecimiento.
- **Umbral:** cuánto se le perdona a un píxel que no sea idéntico al punto. Si el polígono queda chico, subilo de a 0,02; si se pasa a la chacra vecina, bajalo. Por encima de 0,20 suele desbordarse.
- **Zona de búsqueda:** círculo alrededor del punto que le dice a Earth Engine **dónde buscar**. No define la chacra: el borde lo decide la historia de NDVI.
- **Falso color R:B08 G:B11 B:B02:** rojo o naranja = cultivo vigoroso; verde o amarillo = suelo, rastrojo o campo natural; negro = agua.

---

## 4. Si algo falla
| Mensaje | Solución |
|---|---|
| "No encuentro el Python de Earth Engine" | correr *Configurar* y poner la ruta correcta |
| `py` o `python` "no se reconoce como un comando" | Python no está instalado o no se tildó *Add python.exe to PATH*: reinstalar (paso 1 de 1.2) |
| Al hacer `pip install`: error de conexión o de certificado | falta el proxy: hacer los dos `set` del paso 2 de 1.2 en la misma ventana y repetir |
| *Configurar* falla con "Not signed up for Earth Engine" o "project … not registered" | el proyecto no tiene Earth Engine habilitado: registrarlo en code.earthengine.google.com/register (paso 3 de 1.2) |
| *Configurar* falla con "Permission denied" o "Caller does not have required permission" | tu cuenta no tiene acceso a ese proyecto: pedir los roles del paso 3 de 1.2, o revisar que pusiste el **ID** y no el nombre |
| *Configurar* falla con "credentials" o "Please authorize access" | falta autenticarse o venció: repetir el paso 4 de 1.2 |
| "Falló la segmentación en Earth Engine" | ver el registro. Causas habituales: sin internet o proxy mal configurado, `earthengine authenticate` vencido, cuenta sin acceso al proyecto |
| "Las zonas de búsqueda no tienen el campo…" | el campo identificador tiene que existir en los puntos |

## 5. Fuentes de datos
- **NDVI y falso color:** Sentinel-2 L2A armonizado (Copernicus/ESA), con máscara de nubes Cloud Score+.
- **Temperatura de superficie:** Landsat 8/9 Collection 2 Level 2 (USGS/NASA).
- **Lluvia:** CHIRPS v3 diario (Climate Hazards Center, UC Santa Barbara).
- **Temperatura de piel y suelo:** ERA5-Land diario (Copernicus Climate Change Service / ECMWF).
- Todo se procesa en **Google Earth Engine**, con la cuenta y el proyecto de cada usuario.

## 6. Proponer cambios
Los cambios se proponen con un **pull request** en el repositorio de GitHub (`github.com/gingerheart86/point-to-polygon`); los problemas, en *Issues*. Licencia: GPL-2.0 o posterior.
