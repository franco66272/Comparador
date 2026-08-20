"""Extractor automático para Click Gaming."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "clickgaming_com_ar",
    "url": "https://clickgaming.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://clickgaming.com.ar/", "https://clickgaming.com.ar/categoria-producto/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
