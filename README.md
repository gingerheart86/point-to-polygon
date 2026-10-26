# Punto a Polígono: delimitar chacras a partir de un punto

Plugin de QGIS + Google Earth Engine que, a partir de **un punto georreferenciado dentro de una chacra**, genera automáticamente el **polígono del lote** con la serie temporal de NDVI de Sentinel-2. Además calcula hectáreas, las compara con las declaradas y agrega **lluvia** (CHIRPS v3) y **temperatura** (Landsat 8/9, ERA5-Land) de la temporada.

Sirve en cualquier caso en que se conozca solo la ubicación aproximada de un cultivo y haga falta su contorno. Desarrollado y probado en Uruguay.

- 📦 **Instalar:** en QGIS, *Complementos → Administrar e instalar complementos*, buscar **"Punto a Polígono"** (por ahora es experimental: tildar *Mostrar también los complementos experimentales*). O bajar el `.zip` de [Releases](../../releases) e *Instalar desde ZIP*.
- 📖 **Manual:** [`punto_a_poligono/MANUAL.md`](punto_a_poligono/MANUAL.md) ([PDF](punto_a_poligono/MANUAL.pdf)).
- 🧭 **¿Primera vez?** [Cómo funciona, explicado para principiantes](docs/como_funciona.md).
- 🐞 **Problemas y sugerencias:** [Issues](../../issues). **Cambios:** por pull request.

## Método

```
Puntos (uno dentro de cada chacra)
        │
        ▼
Círculo alrededor del punto (radio ajustable, 3 km)      ← zona de búsqueda
        │
        ▼
Segmentación Sentinel-2 en GEE desde el punto            ← borde del lote sembrado
        │
        ▼
Polígono de la chacra + hectáreas + lluvia y temperatura (GeoPackage)
```

- **La zona de búsqueda solo limita dónde mira Earth Engine.** El borde de la chacra lo define la serie temporal de NDVI: se juntan los píxeles conectados al punto que tuvieron la misma historia de NDVI. Ver [BITACORA.md](BITACORA.md).
- **Validación:** se comparó el polígono automático con polígonos dibujados a mano (IoU de 0,54 a 0,91 en la primera prueba).

## Estructura

```
point-to-polygon/
├── punto_a_poligono/    ← el plugin (esta carpeta es la que va dentro del .zip)
│   ├── metadata.txt      versión y datos del plugin
│   ├── plugin.py, provider.py, modelo.py, config.py
│   ├── algoritmos/       configurar, segmentar_s2_gee, comparar_ha, clima_gee, rasters_s2_gee
│   ├── gee/              scripts de Earth Engine (corren en el Python con earthengine-api)
│   ├── estilos/          estilos QML
│   └── MANUAL.md, MANUAL.pdf, LICENSE
├── empaquetar.ps1        arma dist/punto_a_poligono-<versión>.zip (y regenera MANUAL.pdf)
├── generar_manual.py     lo usa empaquetar.ps1
├── BITACORA.md           registro del desarrollo, fecha por fecha
├── docs/                 documentación adicional
├── scripts/, modelos/    versiones anteriores al plugin (historia del desarrollo)
└── LICENSE
```

## Requisitos

- QGIS 3.28 o posterior.
- Python con `earthengine-api` y un proyecto de Google Cloud con Earth Engine habilitado (ver el manual).

## Fuentes de datos

Sentinel-2 L2A armonizado + Cloud Score+ (Copernicus/ESA), Landsat 8/9 Collection 2 Level 2 (USGS/NASA), CHIRPS v3 diario (Climate Hazards Center, UCSB), ERA5-Land diario (Copernicus/ECMWF), procesados en Google Earth Engine.

## Licencia

Copyright (C) 2026 Carolina Menchaca. Este programa es software libre: se puede redistribuir y modificar bajo los términos de la **GNU General Public License, versión 2 o (a tu elección) cualquier versión posterior**, publicada por la Free Software Foundation. Ver [LICENSE](LICENSE).
