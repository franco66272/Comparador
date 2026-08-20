"""Extractor automático para The Gamer Shop."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "thegamershop_com_ar",
    "url": "https://www.thegamershop.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://www.thegamershop.com.ar/tienda/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
