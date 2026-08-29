"""Extractor robusto para Dinobyte."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "dinobyte_ar",
    "url": "https://dinobyte.ar",
    "catalog_urls": ["https://dinobyte.ar/shop/", "https://dinobyte.ar/tienda/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
