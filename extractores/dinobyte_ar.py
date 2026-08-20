"""Extractor automático para Dinobyte."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "dinobyte_ar",
    "url": "https://dinobyte.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://dinobyte.ar/shop/", "https://dinobyte.ar/tienda/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
