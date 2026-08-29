"""Extractor robusto para Click Gaming."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "clickgaming_com_ar",
    "url": "https://clickgaming.com.ar",
    "catalog_urls": ["https://clickgaming.com.ar/", "https://clickgaming.com.ar/categoria-producto/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
