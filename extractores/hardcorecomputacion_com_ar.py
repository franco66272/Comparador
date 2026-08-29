"""Extractor robusto para Hardcore Computación."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "hardcorecomputacion_com_ar",
    "url": "https://hardcorecomputacion.com.ar",
    "catalog_urls": [
        "https://hardcorecomputacion.com.ar/categoria-producto/microprocesadores/",
        "https://hardcorecomputacion.com.ar/categoria-producto/memorias/",
        "https://hardcorecomputacion.com.ar/categoria-producto/almacenamiento/",
        "https://hardcorecomputacion.com.ar/categoria-producto/gabinetes/",
        "https://hardcorecomputacion.com.ar/categoria-producto/fuentes/",
        "https://hardcorecomputacion.com.ar/categoria-producto/motherboards/",
        "https://hardcorecomputacion.com.ar/categoria-producto/monitores/",
        "https://hardcorecomputacion.com.ar/categoria-producto/gaming/",
    ],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
