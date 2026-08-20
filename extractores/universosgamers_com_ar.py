"""Extractor automático para Universos Gamers."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "universosgamers_com_ar",
    "url": "https://universosgamers.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://universosgamers.com.ar/tienda/", "https://universosgamers.com.ar/shop/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
