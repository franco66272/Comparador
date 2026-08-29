"""Extractor robusto para Portal Store."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "portalstore_com_ar",
    "url": "https://portalstore.com.ar",
    "catalog_urls": [
        "https://portalstore.com.ar/",
        "https://portalstore.com.ar/productos",
        "https://portalstore.com.ar/productos/hardware",
        "https://portalstore.com.ar/productos/perifericos",
        "https://portalstore.com.ar/productos/consolas",
        "https://portalstore.com.ar/productos/monitores",
        "https://portalstore.com.ar/productos/notebooks",
    ],
    "producto_regex": r"/producto/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
