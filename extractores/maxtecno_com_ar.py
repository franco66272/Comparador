"""Extractor robusto para Max Tecno."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "maxtecno_com_ar",
    "url": "https://www.maxtecno.com.ar",
    "catalog_urls": [
        "https://maxtecno.com.ar/hardware/",
        "https://maxtecno.com.ar/tienda/",
        "https://maxtecno.com.ar/categoria/computadoras/",
        "https://maxtecno.com.ar/categoria/componentes-pc/",
        "https://maxtecno.com.ar/categoria/auriculares/",
        "https://maxtecno.com.ar/categoria/notebooks/",
    ],
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
