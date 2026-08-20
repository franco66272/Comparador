"""Extractor de GoldenTech Store (WooCommerce)."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://goldentechstore.com.ar"
CATALOGO_URL = f"{BASE_URL}/tienda/"
MAX_PAGINAS = 50
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


def _precio_ar(valor):
    if valor is None:
        return None
    texto = str(valor).replace("$", "").replace("ARS", "").strip()
    texto = re.sub(r"[^0-9,.]", "", texto)
    if not texto:
        return None
    try:
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif texto.count(".") > 1:
            texto = texto.replace(".", "")
        return int(round(float(texto)))
    except (TypeError, ValueError):
        return None


def _imagen_producto(node, base_url):
    img = node.select_one("img")
    if not img:
        return None
    for atributo in (
        "data-large_image",
        "data-src",
        "data-lazy-src",
        "data-original",
        "src",
    ):
        valor = img.get(atributo)
        if valor and not str(valor).startswith("data:"):
            return urljoin(base_url, str(valor).strip())
    srcset = img.get("srcset")
    if srcset:
        return urljoin(base_url, srcset.split(",")[-1].strip().split(" ")[0])
    return None


def _producto_desde_card(card, session):
    enlace = card.select_one(
        "a.woocommerce-LoopProduct-link[href], "
        "a.woocommerce-loop-product__link[href], "
        "h2 a[href], h3 a[href]"
    )
    if not enlace:
        enlace = card.select_one("a[href]")
    if not enlace:
        return None

    url = urljoin(BASE_URL, enlace.get("href", "").strip())
    if "/producto/" not in url:
        return None

    titulo = card.select_one(
        "h2.woocommerce-loop-product__title, "
        "h3.woocommerce-loop-product__title, "
        ".woocommerce-loop-product__title"
    )
    nombre = titulo.get_text(" ", strip=True) if titulo else enlace.get_text(" ", strip=True)
    if not nombre:
        return None

    precio = None
    precio_node = card.select_one("ins .woocommerce-Price-amount, .price .woocommerce-Price-amount")
    if precio_node:
        precio = _precio_ar(precio_node.get_text(" ", strip=True))
    if precio is None:
        precio_node = card.select_one(".price")
        if precio_node:
            valores = re.findall(r"[\d.]+(?:,\d+)?", precio_node.get_text(" ", strip=True))
            if valores:
                precio = _precio_ar(valores[-1])

    if precio is None or precio <= 0:
        return None

    precio_anterior = None
    del_node = card.select_one("del .woocommerce-Price-amount, .price del")
    if del_node:
        precio_anterior = _precio_ar(del_node.get_text(" ", strip=True))
        if precio_anterior and precio_anterior <= precio:
            precio_anterior = None

    texto = card.get_text(" ", strip=True).lower()
    agotado = any(x in texto for x in ("agotado", "sin stock", "no disponible"))

    sku = None
    sku_node = card.select_one(".sku")
    if sku_node:
        sku = sku_node.get_text(" ", strip=True)
    if not sku:
        match = re.search(r"(?:sku\s*:\s*)([a-z0-9_-]+)", card.get_text(" ", strip=True), re.I)
        if match:
            sku = match.group(1)

    imagen = _imagen_producto(card, BASE_URL)

    # WooCommerce suele tener JSON-LD en la página del producto. Lo usamos como
    # respaldo para precio/imagen/SKU cuando la tarjeta no entrega alguno.
    if not imagen or not sku:
        try:
            respuesta = session.get(url, headers=HEADERS, timeout=20)
            if respuesta.status_code == 200:
                soup = BeautifulSoup(respuesta.text, "html.parser")
                for script in soup.select('script[type="application/ld+json"]'):
                    try:
                        datos = json.loads(script.string or script.get_text())
                    except Exception:
                        continue
                    elementos = datos if isinstance(datos, list) else [datos]
                    for dato in elementos:
                        if not isinstance(dato, dict):
                            continue
                        tipo = dato.get("@type")
                        tipos = tipo if isinstance(tipo, list) else [tipo]
                        if "Product" not in tipos:
                            continue
                        if not sku and dato.get("sku"):
                            sku = str(dato["sku"])
                        if not imagen and dato.get("image"):
                            img = dato["image"]
                            imagen = urljoin(BASE_URL, img[0] if isinstance(img, list) else str(img))
                        if not precio:
                            ofertas = dato.get("offers")
                            ofertas = ofertas if isinstance(ofertas, list) else [ofertas]
                            for oferta in ofertas:
                                if isinstance(oferta, dict) and oferta.get("price"):
                                    precio = _precio_ar(oferta["price"])
                                    if precio:
                                        break
                    if imagen and sku and precio:
                        break
        except requests.RequestException:
            pass

    identificador = sku or url

    return {
        "tienda": "GoldenTech Store",
        "nombre": nombre.strip(),
        "precio": int(precio),
        "precio_anterior": precio_anterior,
        "stock": 0 if agotado else 1,
        "imagen": imagen,
        "url": url,
        "id_producto": identificador,
    }


def extraer():
    session = requests.Session()
    session.headers.update(HEADERS)
    productos = []
    ids = set()
    warnings = []

    for pagina in range(1, MAX_PAGINAS + 1):
        url = CATALOGO_URL if pagina == 1 else f"{CATALOGO_URL}page/{pagina}/"
        try:
            respuesta = session.get(url, timeout=30)
            if respuesta.status_code == 404:
                break
            respuesta.raise_for_status()
        except requests.RequestException as exc:
            warnings.append(f"Página {pagina}: {exc}")
            break

        soup = BeautifulSoup(respuesta.text, "html.parser")
        cards = soup.select("li.product")
        if not cards:
            cards = soup.select(".products .product")
        if not cards:
            warnings.append(f"Página {pagina} sin tarjetas de productos")
            break

        nuevos = 0
        for card in cards:
            producto = _producto_desde_card(card, session)
            if not producto:
                continue
            clave = producto["id_producto"]
            if clave in ids:
                continue
            ids.add(clave)
            productos.append(producto)
            nuevos += 1

        print(f"[goldentech] página {pagina}: {nuevos} nuevos, {len(productos)} acumulados")

        siguiente = soup.select_one(
            "a.next, a.next.page-numbers, a.page-numbers.next"
        )
        if not siguiente:
            break

    return {
        "ok": bool(productos),
        "tienda": "GoldenTech Store",
        "productos": productos,
        "con_imagen": sum(1 for p in productos if p.get("imagen")),
        "warnings": warnings,
    }


if __name__ == "__main__":
    resultado = extraer()
    print(f"GoldenTech: {len(resultado['productos'])} productos")
    for warning in resultado["warnings"]:
        print(f"WARNING: {warning}")
