"""Extractor automático para SCP Hardstore."""
from .auto_generico import extraer_desde_config

CONFIG = {
    "tienda": "scphardstore_com",
    "url": "https://www.scphardstore.com",
    "plataformas": ["woocommerce"],
    "catalog_urls": ["https://www.scphardstore.com/tienda/"],
    "fuentes_prioritarias": [],
}

def extraer():
    return extraer_desde_config(CONFIG)
