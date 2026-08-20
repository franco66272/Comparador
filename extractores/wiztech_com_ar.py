"""Extractor automático para WIZ TECH."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "wiztech_com_ar",
    "url": "https://wiztech.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://wiztech.com.ar/tienda/", "https://wiztech.com.ar/shop/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
