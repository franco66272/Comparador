"""Extractor robusto para Katech."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "katech_com_ar",
    "url": "https://katech.com.ar",
    "catalog_urls": [
        "https://katech.com.ar/",
        "https://katech.com.ar/home-nueva/",
    ],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
