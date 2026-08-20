"""Extractor automático para Silver Hard."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "silverhard_com",
    "url": "https://silverhard.com",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://silverhard.com/tienda/", "https://silverhard.com/categoria-producto/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
