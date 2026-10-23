# Manual de uso: plugin "Punto a Polígono" para QGIS

A partir de **un punto dentro de cada chacra**, dibuja el **polígono del lote** con la serie temporal de NDVI de Sentinel-2 en Google Earth Engine. Además calcula las hectáreas, las compara con las declaradas (si las hay) y agrega la **lluvia** y la **temperatura** de la temporada.

---

## 1. Instalación (una vez por PC)

### 1.1 Requisitos de la PC
1. **QGIS 3.28 o posterior.** Probado en 3.28 y 3.44.
2. **Python con la librería `earthengine-api`**, en un entorno aparte del de QGIS. Por ejemplo, desde una terminal:
   - `python -m venv %USERPROFILE%\.venvs\gee`
   - `%USERPROFILE%\.venvs\gee\Scripts\pip install earthengine-api requests pip-system-certs`
   - `pip-system-certs` hace falta si la red tiene un proxy que inspecciona SSL: así Python usa los certificados de Windows.
3. **Salida a Google Earth Engine** (`*.googleapis.com`): directa o por el proxy de la red.
4. **Cuenta con acceso a Earth Engine:** una cuenta de Google con permiso en un **proyecto de Google Cloud con Earth Engine habilitado** (se crea gratis para uso no comercial en code.earthengine.google.com). Después, autenticarse **una vez**:
   - `%USERPROFILE%\.venvs\gee\Scripts\earthengine authenticate`

### 1.2 Instalar el plugin
1. En QGIS: **Complementos → Administrar e instalar complementos → Todos**, buscar **"Punto a Polígono"** e instalar.
   - Mientras sea experimental: en *Configuración*, tildar **"Mostrar también los complementos experimentales"**.
   - También se puede instalar el `.zip` de la sección **Releases** del repositorio con *Instalar desde ZIP*.
2. Aparece el menú **Complementos → Punto a polígono** y, en la Caja de herramientas de Procesos, el grupo **Punto a polígono**.

### 1.3 Configurar (una vez por PC)
**Complementos → Punto a polígono → Configurar (una vez por PC)…**

| Parámetro | Qué poner |
|---|---|
| Python con earthengine-api | `C:\Users\<usuario>\.venvs\gee\Scripts\python.exe` |
| Proyecto de Google Cloud | el proyecto de Earth Engine |
| Proxy | el de la red, ej. `http://proxy.empresa:8080`. Vacío si no hay |
| Carpeta de trabajo | dónde se guardan resultados y rásters |

Al ejecutarlo, **prueba la conexión con Earth Engine** y te avisa si algo falla.

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
| "Falló la segmentación en Earth Engine" | ver el registro. Causas habituales: sin internet o proxy mal configurado, `earthengine authenticate` vencido, cuenta sin acceso al proyecto |
| "Las zonas de búsqueda no tienen el campo…" | el campo identificador tiene que existir en los puntos |

## 5. Fuentes de datos
- **NDVI y falso color:** Sentinel-2 L2A armonizado (Copernicus/ESA), con máscara de nubes Cloud Score+.
- **Temperatura de superficie:** Landsat 8/9 Collection 2 Level 2 (USGS/NASA).
- **Lluvia:** CHIRPS v3 diario (Climate Hazards Center, UC Santa Barbara).
- **Temperatura de piel y suelo:** ERA5-Land diario (Copernicus Climate Change Service / ECMWF).
- Todo se procesa en **Google Earth Engine**, con la cuenta y el proyecto de cada usuario.

## 6. Proponer cambios
Los cambios se proponen con un **pull request** en el repositorio de GitHub (`github.com/gingerheart86/punto-a-poligono`); los problemas, en *Issues*. Licencia: GPL-2.0 o posterior.
