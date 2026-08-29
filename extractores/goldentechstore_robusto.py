"""Extractor robusto para GoldenTech Store."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "goldentechstore_com_ar",
    "url": "https://goldentechstore.com.ar",
    "catalog_urls": ["https://goldentechstore.com.ar/tienda/"],
    "producto_regex": r"/producto/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
