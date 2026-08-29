"""Extractor robusto para GamingCity."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "gamingcity_com_ar",
    "url": "https://www.gamingcity.com.ar",
    "catalog_urls": [
        "https://www.gamingcity.com.ar/",
        "https://www.gamingcity.com.ar/fuentes-componentes--prod--10",
        "https://www.gamingcity.com.ar/memorias-ram-componentes--prod--100",
        "https://www.gamingcity.com.ar/placas-de-video-componentes--prod--104",
        "https://www.gamingcity.com.ar/refrigeracion-componentes--prod--129",
        "https://www.gamingcity.com.ar/pc-joysticks-perifericos--prod--137",
        "https://www.gamingcity.com.ar/ps5-joysticks-perifericos--prod--141",
    ],
    "producto_regex": r"/[^/?#]+--det--\d+[^/?#]*",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
