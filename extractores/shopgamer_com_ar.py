"""Extractor robusto para ShopGamer."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "shopgamer_com_ar",
    "url": "https://www.shopgamer.com.ar",
    "catalog_urls": ["https://www.shopgamer.com.ar/productos/"],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
