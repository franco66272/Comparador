"""Extractor robusto para ArmyTech (PrestaShop)."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "armytech_com_ar",
    "url": "https://www.armytech.com.ar",
    "catalog_urls": ["https://www.armytech.com.ar/2-productos"],
    "producto_regex": r"/\d+-[^/?#]+\.html(?:$|\?)",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
