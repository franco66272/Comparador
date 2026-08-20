"""Extractor automático para Empeño Gamer."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "empeniogamer_com_ar",
    "url": "https://empeniogamer.com.ar",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://empeniogamer.com.ar/tienda/", "https://empeniogamer.com.ar/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
