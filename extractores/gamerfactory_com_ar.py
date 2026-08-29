"""Extractor robusto para Gamer Factory.

La tienda actual es una SPA: la página /productos requiere JavaScript.
Este extractor deja definida la ruta de catálogo para que el motor robusto
pueda usarla cuando el HTML entregue las fichas o cuando se añada su endpoint.
"""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "gamerfactory_com_ar",
    "url": "https://www.gamerfactory.com.ar",
    "catalog_urls": ["https://www.gamerfactory.com.ar/productos"],
    "producto_regex": r"/producto/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
