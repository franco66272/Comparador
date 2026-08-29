"""Extractor robusto para SCP Hardstore."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "scphardstore_com",
    "url": "https://www.scphardstore.com",
    "catalog_urls": ["https://www.scphardstore.com/tienda/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
