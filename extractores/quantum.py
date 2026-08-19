"""
Extractor de Quantum Hardstore (Tiendanube).

REGLA DEFINITIVA (aprendida de la corrida que generó cientos de 429):
    NUNCA visitar productos individuales. Solo se recorren las páginas de
    catálogo (/productos/, /productos/page/N/) y se extrae todo desde las
    tarjetas HTML de esas páginas. Esto es lo que en su momento dio
    2107 productos / 2051 con imagen / 101.3s.

Nota importante: no tengo forma de verificar en vivo el HTML actual de
Quantum desde este entorno (sin acceso de red al sitio), así que los
selectores de abajo son una cascada de candidatos típicos de temas
Tiendanube. Si al correr esto el resultado da 0 productos o un número
muy bajo, correr `diagnostico.py https://quantumhardstore.com/productos/`
y pasarme el HTML de una tarjeta para ajustar el selector en un solo paso
(no hace falta volver a probar a ciegas).
"""
import re
import time

import requests
from bs4 import BeautifulSoup

from .utils import parse_precio_ar, session_con_reintentos

BASE_URL = "https://quantumhardstore.com"
CATALOG_URL = f"{BASE_URL}/productos/"
DELAY_ENTRE_PAGINAS = 1.0  # segundos entre requests, para no repetir el 429
MAX_PAGINAS = 60  # margen sobre las ~45 páginas conocidas

# Se prueban en orden; se usa el primer selector que devuelva resultados.
SELECTORES_TARJETA = [
    "li.js-item-product",
    "div.js-item-product",
    "li.product-item",
    "div.product-item",
    "article.product-item",
]


def _extraer_tarjetas(soup):
    for selector in SELECTORES_TARJETA:
        tarjetas = soup.select(selector)
        if tarjetas:
            return tarjetas, selector
    return [], None


def _parsear_tarjeta(tarjeta):
    link = tarjeta.select_one("a[href*='/productos/']") or tarjeta.select_one("a")
    if not link or not link.get("href"):
        return None
    url = link["href"]
    if url.startswith("/"):
        url = BASE_URL + url

    nombre_el = (
        tarjeta.select_one(".product-name")
        or tarjeta.select_one(".js-item-name")
        or tarjeta.select_one("h3")
        or tarjeta.select_one("h2")
        or link
    )
    nombre = nombre_el.get_text(strip=True) if nombre_el else None

    precio_el = (
        tarjeta.select_one(".price ins")
        or tarjeta.select_one(".price .money")
        or tarjeta.select_one(".product-price")
        or tarjeta.select_one("[class*='price']")
    )
    precio_texto = precio_el.get_text(strip=True) if precio_el else None
    precio = parse_precio_ar(precio_texto) if precio_texto else None

    img_el = tarjeta.select_one("img")
    imagen = None
    if img_el:
        imagen = img_el.get("data-src") or img_el.get("src")
        if not imagen and img_el.get("data-srcset"):
            imagen = img_el["data-srcset"].split(" ")[0]
        if imagen and imagen.startswith("//"):
            imagen = "https:" + imagen

    id_producto = tarjeta.get("data-product-id")
    if not id_producto:
        m = re.search(r"-(\d+)(?:\.html)?/?$", url)
        id_producto = m.group(1) if m else url

    if not nombre or not precio:
        return None

    return {
        "tienda": "Quantum Hardstore",
        "nombre": nombre,
        "precio": precio,
        "precio_anterior": None,
        "stock": 1,
        "imagen": imagen,
        "url": url,
        "id_producto": id_producto,
    }


def extraer():
    """
    Devuelve:
        {
            "ok": bool,
            "tienda": "Quantum Hardstore",
            "productos": [...],
            "con_imagen": int,
            "paginas_recorridas": int,
            "selector_usado": str | None,
            "warnings": [...],
        }
    """
    session = session_con_reintentos()
    productos = []
    urls_vistas = set()
    selector_usado = None
    warnings = []
    pagina = 1

    while pagina <= MAX_PAGINAS:
        url_pagina = CATALOG_URL if pagina == 1 else f"{BASE_URL}/productos/page/{pagina}/"
        try:
            resp = session.get(url_pagina, timeout=20)
        except requests.RequestException as e:
            warnings.append(f"Error de red en página {pagina}: {e}")
            break

        if resp.status_code == 429:
            warnings.append(f"HTTP 429 en página {pagina} — se corta acá, no se insiste")
            break
        if resp.status_code != 200:
            # Fin normal de la paginación (la página N+1 más allá de la última suele dar 404)
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tarjetas, selector = _extraer_tarjetas(soup)
        if not tarjetas:
            break

        selector_usado = selector_usado or selector
        nuevos = 0
        for tarjeta in tarjetas:
            p = _parsear_tarjeta(tarjeta)
            if p and p["url"] not in urls_vistas:
                urls_vistas.add(p["url"])
                productos.append(p)
                nuevos += 1

        if nuevos == 0:
            break  # página repetida: ya se dio toda la vuelta al catálogo

        pagina += 1
        time.sleep(DELAY_ENTRE_PAGINAS)

    if not productos:
        warnings.append(
            "0 productos extraídos. Los selectores conocidos "
            f"({SELECTORES_TARJETA}) no matchearon nada — probablemente Quantum "
            "cambió de tema. Correr diagnostico.py sobre "
            f"{CATALOG_URL} y pasar el HTML de una tarjeta de producto."
        )

    con_imagen = sum(1 for p in productos if p.get("imagen"))
    if productos and con_imagen < len(productos) * 0.8:
        warnings.append(f"Solo {con_imagen}/{len(productos)} productos con imagen")

    return {
        "ok": len(productos) > 0,
        "tienda": "Quantum Hardstore",
        "productos": productos,
        "con_imagen": con_imagen,
        "paginas_recorridas": pagina - 1,
        "selector_usado": selector_usado,
        "warnings": warnings,
    }


if __name__ == "__main__":
    resultado = extraer()
    print(f"OK: {resultado['ok']}")
    print(f"Productos: {len(resultado['productos'])}")
    print(f"Con imagen: {resultado['con_imagen']}")
    print(f"Páginas recorridas: {resultado['paginas_recorridas']}")
    print(f"Selector usado: {resultado['selector_usado']}")
    for w in resultado["warnings"]:
        print(f"WARNING: {w}")
