"""Extractor robusto para Silver Hard."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "silverhard_com",
    "url": "https://silverhard.com",
    "catalog_urls": ["https://silverhard.com/tienda/", "https://silverhard.com/categoria-producto/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
