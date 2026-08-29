"""Extractor robusto para The Gamer Shop."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "thegamershop_com_ar",
    "url": "https://www.thegamershop.com.ar",
    "catalog_urls": ["https://www.thegamershop.com.ar/tienda/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
