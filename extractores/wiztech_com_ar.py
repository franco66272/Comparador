"""Extractor robusto para WIZ TECH."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "wiztech_com_ar",
    "url": "https://wiztech.com.ar",
    "catalog_urls": ["https://wiztech.com.ar/catalogo"],
    "producto_regex": r"/catalogo/producto/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
