"""Extractor robusto para XT-PC."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "xt_pc_com_ar",
    "url": "https://www.xt-pc.com.ar",
    "catalog_urls": [
        "https://www.xt-pc.com.ar/catalogo",
        "https://www.xt-pc.com.ar/cat/",
        "https://www.xt-pc.com.ar/pcarmada/",
        "https://www.xt-pc.com.ar/nvidia/",
    ],
    "producto_regex": r"/prod/\d+/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
