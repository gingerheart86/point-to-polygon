def classFactory(iface):  # noqa: N802 (nombre requerido por QGIS)
    from .plugin import PluginPuntoAPoligono
    return PluginPuntoAPoligono(iface)
