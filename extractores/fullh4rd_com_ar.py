"""Extractor robusto para FullH4rd."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "fullh4rd_com_ar",
    "url": "https://fullh4rd.com.ar",
    "catalog_urls": [
        "https://fullh4rd.com.ar/productos",
        "https://fullh4rd.com.ar/cat",
        "https://fullh4rd.com.ar/amd",
        "https://fullh4rd.com.ar/nvidia",
        "https://fullh4rd.com.ar/pcarmada",
    ],
    "producto_regex": r"/prod/\d+/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
