# Cómo funciona el modelo

## La idea 
> **Una chacra es área de campo donde todas las plantas nacieron, crecieron y se secaron al mismo tiempo.** El modelo busca, alrededor de tu punto, todos los píxeles que "vivieron la misma historia" que el punto.

## Una analogía
Imaginá una foto aérea del campo sacada **una vez por mes**, de mayo a octubre: seis fotos. Si mirás un solo punto de la chacra en las seis, ves su historia: en mayo era tierra pelada, en julio apareció el verde, en septiembre estaba verde oscuro y en octubre empezó a amarillear.

Ahora mirá un punto del campo natural de al lado: estuvo verde clarito todo el tiempo, sin grandes cambios. Y la chacra vecina, sembrada tres semanas antes, hizo lo mismo que la tuya pero **adelantada**.

El modelo compara la historia de cada píxel con la de tu punto. Los que tienen **la misma historia y están pegados al punto** forman la chacra.

## ¿Qué es el NDVI?
Es un número entre -1 y 1 que dice **cuánta vegetación verde y sana hay** en un píxel. Se calcula con dos bandas de Sentinel-2:

```
NDVI = (B08 - B04) / (B08 + B04)        B08 = infrarrojo cercano, B04 = rojo
```

- Cerca de **0**: suelo desnudo, rastrojo, agua.
- **0,3 a 0,5**: pasto ralo, cultivo recién nacido.
- **0,7 a 0,9**: cultivo denso y sano.

Las hojas sanas reflejan mucho infrarrojo y absorben el rojo. Por eso, cuanto más verde es la planta, más alto da el NDVI.

## ¿Qué necesitás para correrlo?
| Entrada | Qué es | Ejemplo |
|---|---|---|
| **Puntos de las chacras** | una capa de puntos, uno por chacra | las coordenadas del CSV |
| **Campo identificador** | la columna que identifica cada punto | número de bien o de póliza |
| **Radio de búsqueda** | hasta qué distancia del punto buscar (m) | `3000` (≈ 2.800 ha) |
| **Inicio de la temporada** | primer día de la "película" | `2026-05-01` |
| **Fin de la temporada** | último día | `2026-10-15` |
| **Umbral de similitud** | qué tan parecida tiene que ser la historia | `0.15` |
| **Rellenar huecos menores a** | tamaño de los agujeros a tapar (m²) | `50000` (5 ha) |
| **Campo de hectáreas declaradas** *(opcional)* | la columna de los puntos con la superficie declarada | `ha_declaradas` |
| **Tolerancia (%)** | diferencia aceptable entre estimado y declarado | `20` |
| **Controles extra** *(opcional)* | campos de los puntos que deben valer "OK" (por ejemplo, un control de departamento) | `depto_ok` |
| **Otros campos a copiar** *(opcional)* | columnas de los puntos que querés ver también en las chacras | nombre, cultivo… |

## Los pasos, uno por uno

```
 QGIS (tu computadora)                         Google Earth Engine (la nube)
 ─────────────────────                         ─────────────────────────────
 1. Círculo alrededor de cada punto
    → ZONA DE BÚSQUEDA
          │  (se envían puntos + zonas) ──────► 2a. Busca TODAS las imágenes Sentinel-2
          │                                         de la zona entre Inicio y Fin
          │                                     2b. Borra las nubes
          │                                     2c. Arma 1 NDVI por mes (6 "fotos")
          │                                     2d. Historia del punto vs. historia de
          │                                         cada píxel → DISTANCIA
          │                                     2e. Se queda con lo parecido Y pegado
          │  ◄────────── (vuelve el polígono)       al punto
 3. Tapa huecos chicos
 4. Calcula hectáreas
 5. Compara con las hectáreas declaradas → CHACRAS
```

### Paso 1: dónde buscar (en QGIS)
El modelo dibuja un **círculo** alrededor de cada punto (por defecto, de 3 km de radio). Esa es la **zona de búsqueda**: solo le dice a Earth Engine "buscá por acá". El borde de la chacra lo decide la imagen.

*¿Por qué no se usa el padrón de Catastro?* Se probó, pero el padrón marca **hasta dónde llega una propiedad**, no hasta dónde llega una chacra, y la chacra cruzaba igual al padrón de al lado. Como solo servía para acotar la búsqueda, un círculo hace lo mismo sin necesitar el parcelario.

*¿Cuándo agrandar el radio?* Solo si la chacra es muy grande (más de ~1.000 ha) o si el punto está lejos de su centro. Un radio más grande no cambia el resultado: solo hace más lento el cálculo.

### Paso 2: la segmentación (en Google Earth Engine)
Es el corazón del modelo. QGIS no tiene las imágenes satelitales: las tiene Google Earth Engine, que guarda **todo el archivo de Sentinel-2** (una imagen cada 2 a 5 días de todo el planeta, desde 2017). El modelo le manda los puntos y las zonas, Earth Engine hace las cuentas y devuelve **solo los polígonos**. No se descargan imágenes.

- **2a. Imágenes:** toma todas las imágenes Sentinel-2 de la zona **entre la fecha de Inicio y la de Fin**. Para mayo–octubre de 2026 en Río Negro fueron 87.
- **2b. Nubes:** borra los píxeles nublados con el producto *Cloud Score+*.
- **2c. Las "fotos mensuales":** divide la temporada en **bloques de 30 días** desde la fecha de Inicio y, en cada bloque, calcula el NDVI mediano de cada píxel. La mediana sirve para ignorar algún día malo que haya quedado. Si un bloque quedó todo nublado en un píxel, usa la mediana de toda la temporada.

  Con Inicio = 1 de mayo quedan 6 bloques: 1 may, 31 may, 30 jun, 30 jul, 29 ago y 28 sep. Por eso las capas "NDVI mensual" tienen esas fechas y no "mayo, junio…" exactos.
- **2d. La distancia:** saca la historia del punto (el promedio de un círculo de 20 m) y la compara con la de cada píxel: resta mes a mes, eleva al cuadrado, promedia y saca la raíz. Ese número es la **distancia**: 0 = historia idéntica, 0,3 = historia muy distinta. Es la capa "Distancia" (verde = parecido, rojo = distinto).
- **2e. Lo que se parece y está pegado:** marca los píxeles con distancia **menor al umbral** y se queda solo con la mancha que **toca el punto**. Antes de eso "afina" la mancha: le saca 1 píxel de borde y se lo vuelve a poner, así se cortan los hilitos que la unirían con la chacra de al lado (un camino, un alambrado).

### Pasos 3 y 4: terminación (en QGIS)
Tapa los agujeros menores a 5 ha (manchas de maleza, charcos, daño puntual) y calcula las hectáreas (`area_ha`).

### Paso 5: control de hectáreas (en QGIS, opcional)
Si tus puntos traen una columna con las **hectáreas declaradas** y la elegís en "Campo de hectáreas declaradas", el modelo compara:

```
dif_ha  = estimadas - declaradas
dif_pct = dif_ha / declaradas × 100
control = REVISAR  si |dif_pct| > tolerancia (por defecto 20 %)
                   o si algún "control extra" no es OK
          OK       en los demás casos
          SIN DATO si no hay hectáreas declaradas (y los controles extra están bien)
motivo  = por qué quedó en REVISAR, ej. "ha -43 %" o "NO COINCIDE (depto_ok)"
```

Acepta coma o punto decimal ("145,2" o "145.2"). Si no elegís ningún campo, el paso no hace nada y todas las chacras quedan como SIN DATO.

**Cómo leer un REVISAR:**
- Estimado **menor** que lo declarado: puede ser que la declaración esté inflada, o que el modelo haya dejado afuera parte de la chacra. Por ejemplo, una zona muy dañada se comporta distinto y queda afuera. Mirá la capa Distancia.
- Estimado **mayor**: puede que se haya sembrado más de lo declarado, o que el modelo se haya "desbordado" a una chacra vecina. Probá con un umbral más bajo.

El resultado es la capa **Chacras**.

## ¿Dónde se ponen las fechas?
En los parámetros **"Inicio de la temporada"** y **"Fin de la temporada"** del modelo: la ventana que aparece al hacer doble clic en el modelo, en la Caja de herramientas.

- No hace falta tocar ningún script.
- El largo de cada "foto" (30 días) está fijo en el script 04 (`DIAS_PERIODO`).

### ¿Qué fechas elegir?
Tienen que cubrir **el ciclo del cultivo**, de la siembra a la madurez. Ahí es donde una chacra se diferencia de lo que la rodea.

| Cultivo | Temporada sugerida |
|---|---|
| Invierno (trigo, cebada, colza) | 1 de mayo → 31 de diciembre |
| Verano (soja, maíz, sorgo) | 1 de octubre → 31 de mayo |
| Arroz | 1 de octubre → 31 de marzo |

Estas ventanas incluyen la **cosecha**. Eso ayuda, porque cada chacra se cosecha en una fecha distinta y eso también la diferencia de las vecinas. **Ojo:** no conviene extender el Fin varios meses después de la cosecha, porque la chacra queda como rastrojo, se siembra otro cultivo encima y su historia se mezcla con la de la temporada siguiente. Si la temporada todavía no terminó, usá como Fin la fecha de hoy.

## El umbral, en criollo
Es **cuánto le perdonás** a un píxel que no sea idéntico al punto.

| Umbral | Resultado |
|---|---|
| Muy bajo (0,05) | solo entra lo casi idéntico → chacra **incompleta** |
| **0,15** (recomendado) | buen equilibrio |
| Alto (0,25 o más) | entra cualquier cosa parecida → se **"desborda"** a las chacras vecinas |

Si un polígono te queda chico, subí el umbral de a 0,02. Si se pasa a la chacra vecina, bajalo.

## ¿Qué te devuelve?
- **Chacras:** un polígono por punto, con su identificador, el umbral usado, las hectáreas estimadas (`area_ha`), la cantidad de imágenes usadas, las fechas y, si se dieron, el control de hectáreas (`ha_declaradas`, `dif_ha`, `dif_pct`, `control`, `motivo`).
- **Zonas de búsqueda:** dónde buscó, para revisar.

## Problemas comunes
| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| "No se encontró chacra conectada al punto" | el punto cae en un camino, un monte o el borde | mover el punto adentro de la chacra |
| Polígono muy chico | umbral bajo, o daño fuerte dentro de la chacra | subir el umbral; revisar la capa Distancia |
| Polígono gigante | umbral alto, o la chacra vecina tiene el mismo cultivo y la misma fecha de siembra | bajar el umbral |
| Polígono raro | fechas que no cubren el cultivo | ajustar Inicio y Fin al ciclo |

## Glosario
- **Píxel:** cada cuadradito de la imagen. En Sentinel-2 mide 10 × 10 m (0,01 ha).
- **Banda:** cada "color" que mide el satélite, incluidos los invisibles (infrarrojo).
- **NDVI:** índice de verdor (ver arriba).
- **Mediana:** el valor del medio, si ordenás todos de menor a mayor. Ignora los valores raros.
- **Segmentar:** dividir una imagen en pedazos homogéneos.
- **IoU:** cuánto se superponen dos polígonos. 1 = idénticos, 0 = no se tocan.
