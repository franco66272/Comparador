"""Extractor automático para Max Tecno."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "maxtecno_com_ar",
    "url": "https://www.maxtecno.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://maxtecno.com.ar/hardware/", "https://maxtecno.com.ar/tienda/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
