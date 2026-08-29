"""Extractor robusto para CompufanStore."""
from .catalogo_robusto import extraer_desde_config_robusto

CONFIG = {
    "tienda": "compufanstore_com_ar",
    "url": "https://www.compufanstore.com.ar",
    "catalog_urls": [
        "https://www.compufanstore.com.ar/ARTICULOS/Accesorios/CAT_ID=57/SCAT_ID=3886/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Monitores/CAT_ID=57/SCAT_ID=3883/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Procesadores-AMD/CAT_ID=64/SCAT_ID=3879/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Procesadores-Intel/CAT_ID=64/SCAT_ID=3878/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Placas-de-Video-AMD/CAT_ID=64/SCAT_ID=3877/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Placas-de-Video-Nvidia/CAT_ID=64/SCAT_ID=3909/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Memorias-Ram/CAT_ID=64/SCAT_ID=3873/m=0/BUS=/compufanstore.aspx",
        "https://www.compufanstore.com.ar/ARTICULOS/Discos-SSD/CAT_ID=64/SCAT_ID=3880/m=0/BUS=/compufanstore.aspx",
    ],
    "producto_regex": r"/DETALLE/[^?#]+",
}

def extraer():
    return extraer_desde_config_robusto(CONFIG)
