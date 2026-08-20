"""Motor universal de catálogos de TecnoRadar.

Principio central: primero se descubre el catálogo completo y después se
extraen los productos. Nunca se usa una lista de palabras para decidir qué
URLs existen, porque eso provocaba catálogos de 0/10/20 productos cuando la
tienda tenía cientos o miles.

Fuentes soportadas:
- WooCommerce Store API pública
- Shopify products.json
- Magento REST público
- sitemap.xml / sitemap_index.xml / product-sitemap.xml
- categorías y paginación HTML
- JSON-LD Product y tarjetas HTML

El resultado incluye métricas de cobertura para que el validador pueda
rechazar una extracción parcial.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

from .utils import parse_precio_ar, session_con_reintentos

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

# Una tienda grande puede tener miles de fichas. El límite anterior de 120
# requests era la principal causa de catálogos incompletos.
MAX_SEGUNDOS = 280
MAX_REQUESTS = 5000
MAX_PAGINAS = 1000
MAX_PRODUCTOS = 20000
MAX_SITEMAP_URLS = 30000
DETAIL_WORKERS = 12
HTTP_TIMEOUT = 10

PRODUCT_PATH_RE = re.compile(
    r"/(?:producto|product|productos|products|p)/[^/?#]+",
    re.I,
)
PAGE_RE = re.compile(
    r"(?:^|[?&/])(?:page|p|pagina|pagenum|pageNumber|page_num)[=/]\d+",
    re.I,
)

SOURCE_EXCLUDE = (
    "contacto", "nosotros", "quienes-somos", "privacidad", "terminos",
    "politicas", "login", "register", "carrito", "checkout", "wishlist",
    "blog", "faq", "preguntas-frecuentes", "sobre-nosotros", "mi-cuenta",
    "account", "wp-json", "/feed", "tag/", "autor/", "author/",
)

PRODUCT_MARKERS = (
    "producto", "productos", "product", "products", "item", "sku",
    "hardware", "componentes", "computacion", "perifericos", "notebook",
    "laptop", "monitor", "placa", "procesador", "memoria", "ram", "ssd",
    "disco", "fuente", "gabinete", "cooler", "teclado", "mouse", "auricular",
    "headset", "webcam", "microfono", "router", "wifi", "cable", "adaptador",
    "consola", "playstation", "xbox", "nintendo", "joystick", "silla", "gaming",
    "toner", "impresora", "tablet", "celular", "smartwatch", "audio",
)

IMAGE_PLACEHOLDERS = (
    "placeholder", "no-image", "no_image", "default-image", "copito.png",
    "data:image", "spacer.gif", "transparent.gif",
)


class Presupuesto:
    def __init__(self):
        self.inicio = time.monotonic()
        self.requests = 0
        self.paginas = 0
        self.productos = 0

    def vencido(self):
        return (
            time.monotonic() - self.inicio >= MAX_SEGUNDOS
            or self.requests >= MAX_REQUESTS
            or self.paginas >= MAX_PAGINAS
            or self.productos >= MAX_PRODUCTOS
        )

    def puede_request(self):
        if self.vencido():
            return False
        self.requests += 1
        return True


def _normalizar_url(url):
    if not url:
        return None
    try:
        p = urlparse(str(url).strip())
        return urlunparse((
            p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/",
            "", p.query, "",
        ))
    except Exception:
        return str(url).strip()


def _url(base, valor):
    if not valor:
        return None
    valor = str(valor).strip()
    if valor.startswith("//"):
        return "https:" + valor
    return urljoin(base, valor)


def _es_misma_tienda(url, base):
    try:
        return urlparse(url).netloc.lower().lstrip("www.") == urlparse(base).netloc.lower().lstrip("www.")
    except Exception:
        return False


def _es_fuente_excluida(url):
    valor = str(url or "").lower()
    return any(x in valor for x in SOURCE_EXCLUDE)


def _es_producto_url(url):
    return bool(PRODUCT_PATH_RE.search(urlparse(url).path))


def _precio(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        n = int(round(float(valor)))
        return n if 100 <= n <= 100_000_000 else None
    n = parse_precio_ar(str(valor))
    return n if n and 100 <= n <= 100_000_000 else None


def _imagen_valida(url):
    valor = str(url or "").strip().lower()
    return bool(valor) and not any(x in valor for x in IMAGE_PLACEHOLDERS)


def _imagen(img, base):
    if not img:
        return None
    if isinstance(img, str):
        candidato = _url(base, img)
        return candidato if _imagen_valida(candidato) else None
    for atributo in (
        "data-zoom-image", "data-large-image", "data-full", "data-original",
        "data-image", "data-lazy-src", "data-src", "src",
    ):
        valor = img.get(atributo)
        if valor:
            candidato = _url(base, valor)
            if _imagen_valida(candidato):
                return candidato
    for atributo in ("data-srcset", "srcset"):
        if img.get(atributo):
            for item in str(img[atributo]).split(","):
                candidato = _url(base, item.strip().split()[0])
                if _imagen_valida(candidato):
                    return candidato
    return None


def _producto_relevante(producto):
    """No descarta por nombre.

    El comparador debe conocer el catálogo real de la tienda. La clasificación
    de categorías se hace después, en la aplicación. Sólo rechazamos registros
    que claramente no son una ficha de producto.
    """
    nombre = str(producto.get("nombre") or "").strip()
    url = str(producto.get("url") or "")
    return bool(nombre and producto.get("precio") and url)


def _producto_jsonld(data, base_url, tienda):
    if not isinstance(data, dict):
        return None
    tipo = data.get("@type")
    tipos = tipo if isinstance(tipo, list) else [tipo]
    if not any(str(x).lower() == "product" for x in tipos):
        return None

    nombre = str(data.get("name") or "").strip()
    if not nombre:
        return None

    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}

    precio = _precio(
        offers.get("price") or offers.get("lowPrice") or
        data.get("price") or data.get("salePrice")
    )
    if not precio:
        return None

    disponibilidad = str(offers.get("availability") or "").lower()
    stock = 0 if any(x in disponibilidad for x in ("outofstock", "soldout", "unavailable")) else 1
    url = _url(base_url, data.get("url")) or base_url
    imagen = data.get("image") or data.get("thumbnailUrl")
    if isinstance(imagen, list):
        imagen = imagen[0] if imagen else None
    sku = data.get("sku") or data.get("mpn") or data.get("productID") or url

    return {
        "tienda": tienda,
        "nombre": nombre,
        "precio": precio,
        "stock": stock,
        "imagen": _imagen(imagen, base_url),
        "url": url,
        "id_producto": str(sku),
    }


def _extraer_jsonld(html, base_url, tienda):
    soup = BeautifulSoup(html, "html.parser")
    encontrados = []
    vistos = set()
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        pila = data if isinstance(data, list) else [data]
        while pila:
            obj = pila.pop()
            if isinstance(obj, dict):
                p = _producto_jsonld(obj, base_url, tienda)
                if p and _producto_relevante(p):
                    clave = p["id_producto"]
                    if clave not in vistos:
                        vistos.add(clave)
                        encontrados.append(p)
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        pila.append(value)
            elif isinstance(obj, list):
                pila.extend(obj)
    return encontrados


def _precio_card(card):
    for nodo in card.select(
        "[data-price-amount], [data-price], [itemprop=price], [itemprop=lowPrice], "
        ".price, .precio, .product-price, .price-box, .special-price, .sale-price, "
        ".woocommerce-Price-amount, .amount, .current-price"
    ):
        valor = (
            nodo.get("data-price-amount") or nodo.get("data-price") or
            nodo.get("content") or nodo.get_text(" ", strip=True)
        )
        precio = _precio(valor)
        if precio:
            return precio

    texto = card.get_text(" ", strip=True)
    for patron in (r"\$\s*[\d.]+(?:,\d+)?", r"(?:ARS|ar\$)\s*[\d.]+(?:,\d+)?"):
        m = re.search(patron, texto, re.I)
        if m:
            precio = _precio(m.group(0))
            if precio:
                return precio
    return None


def _nombre_card(card):
    for selector in (
        "[data-product-name]", "[data-name]", ".product-item-link",
        ".product-item-name", ".product-name", ".product-title", ".woocommerce-loop-product__title",
        ".product-name a", ".name", ".title", "[itemprop=name]", "h1", "h2", "h3", "h4", "h5",
    ):
        nodo = card.select_one(selector)
        if not nodo:
            continue
        valor = (
            nodo.get("data-product-name") or nodo.get("data-name") or
            nodo.get("title") or nodo.get_text(" ", strip=True)
        )
        if valor and len(valor.strip()) >= 3:
            return valor.strip()
    return None


def _extraer_card(card, base_url, tienda):
    enlace = card.select_one("a[href]")
    if not enlace:
        return None
    href = _normalizar_url(_url(base_url, enlace.get("href")))
    if not href or not _es_misma_tienda(href, base_url) or not _es_producto_url(href):
        return None
    nombre = _nombre_card(card) or enlace.get("title") or enlace.get_text(" ", strip=True)
    precio = _precio_card(card)
    if not nombre or not precio:
        return None
    imagen = _imagen(card.select_one("img"), base_url)
    product_id = (
        card.get("data-product-id") or card.get("data-productid") or
        card.get("data-id") or enlace.get("data-product-id") or href
    )
    return {
        "tienda": tienda,
        "nombre": nombre.strip(),
        "precio": precio,
        "stock": 1,
        "imagen": imagen,
        "url": href,
        "id_producto": str(product_id),
    }


def _detectar_cards(soup):
    selectores = (
        ".product-item", ".product-card", ".product-card-item", ".item.product",
        "article.product", ".product", "li.product", ".type-product",
        "[data-product-id]", "[data-productid]", "[itemtype*='Product']",
    )
    mejor = []
    for selector in selectores:
        try:
            cards = soup.select(selector)
        except Exception:
            continue
        validos = [c for c in cards if c.select_one("a[href]") and _precio_card(c)]
        if len(validos) > len(mejor):
            mejor = validos
    return mejor


def _extraer_html(html, base_url, tienda):
    soup = BeautifulSoup(html, "html.parser")
    productos = []
    vistos = set()
    for card in _detectar_cards(soup):
        p = _extraer_card(card, base_url, tienda)
        if not p:
            continue
        clave = p["url"]
        if clave not in vistos:
            vistos.add(clave)
            productos.append(p)

    # Fallback: buscar directamente enlaces a fichas y subir hasta encontrar
    # un contenedor que contenga un precio.
    if not productos:
        for a in soup.select("a[href]"):
            href = _normalizar_url(_url(base_url, a.get("href")))
            if not href or not _es_misma_tienda(href, base_url) or not _es_producto_url(href):
                continue
            nodo = a
            for _ in range(6):
                nodo = nodo.parent if nodo else None
                if not nodo:
                    break
                if _precio_card(nodo):
                    p = _extraer_card(nodo, base_url, tienda)
                    if p and p["url"] == href and href not in vistos:
                        vistos.add(href)
                        productos.append(p)
                    break
    return productos


def _extraer_detalle(url, tienda, session=None):
    try:
        if session:
            r = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        else:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    productos = _extraer_jsonld(r.text, r.url, tienda)
    if productos:
        p = productos[0]
        p["url"] = _normalizar_url(p.get("url") or r.url)
        return p

    soup = BeautifulSoup(r.text, "html.parser")
    nombre = None
    for selector in ("h1", "[itemprop=name]", ".product_title", ".product-name", ".product-title"):
        nodo = soup.select_one(selector)
        if nodo and nodo.get_text(" ", strip=True):
            nombre = nodo.get_text(" ", strip=True)
            break
    precio = None
    for selector in (
        '[itemprop=price]', 'meta[property="product:price:amount"]',
        '.price', '.precio', '.product-price', '.price-box', '.special-price',
        '.sale-price', '.woocommerce-Price-amount', '.amount', '.current-price',
    ):
        for nodo in soup.select(selector)[:10]:
            valor = nodo.get("content") or nodo.get("data-price") or nodo.get_text(" ", strip=True)
            precio = _precio(valor)
            if precio:
                break
        if precio:
            break
    if not nombre or not precio:
        return None

    imagen = _imagen(soup.select_one('meta[property="og:image"]'), r.url)
    if not imagen:
        meta = soup.select_one('meta[property="og:image"]')
        imagen = _imagen(meta.get("content") if meta else None, r.url)
    sku_node = soup.select_one("[itemprop=sku], .sku")
    sku = sku_node.get("content") if sku_node and sku_node.get("content") else (sku_node.get_text(" ", strip=True) if sku_node else r.url)
    stock = 0 if re.search(r"sin stock|agotado|out of stock|no disponible", soup.get_text(" ", strip=True), re.I) else 1
    return {
        "tienda": tienda,
        "nombre": nombre,
        "precio": precio,
        "stock": stock,
        "imagen": imagen,
        "url": _normalizar_url(r.url),
        "id_producto": str(sku or r.url),
    }


def _siguiente_pagina(soup, actual):
    candidatos = []
    for nodo in soup.select('a[rel="next"], link[rel="next"]'):
        if nodo.get("href"):
            candidatos.append(nodo.get("href"))
    palabras = {"next", "siguiente", "siguiente página", "next page", "›", "»", ">"}
    for nodo in soup.select("a[href]"):
        texto = nodo.get_text(" ", strip=True).lower()
        aria = (nodo.get("aria-label") or "").lower()
        title = (nodo.get("title") or "").lower()
        if texto in palabras or aria in palabras or title in palabras:
            candidatos.append(nodo.get("href"))
    for candidato in candidatos:
        siguiente = _normalizar_url(_url(actual, candidato))
        if siguiente and siguiente != _normalizar_url(actual):
            return siguiente

    # WooCommerce suele usar /page/2/ y Magento/otros usan ?page=2.
    for nodo in soup.select("a[href]"):
        siguiente = _normalizar_url(_url(actual, nodo.get("href")))
        if not siguiente or not _es_misma_tienda(siguiente, actual):
            continue
        if PAGE_RE.search(siguiente):
            return siguiente
    return None


def _parse_json_products(data, base_url, tienda):
    if isinstance(data, dict):
        pools = []
        for key in ("products", "items", "results", "data", "productsData", "hits"):
            value = data.get(key)
            if isinstance(value, list):
                pools.extend(value)
            elif isinstance(value, dict):
                pools.append(value)
        if not pools and isinstance(data.get("items"), dict):
            pools = [data["items"]]
    elif isinstance(data, list):
        pools = data
    else:
        return []

    productos = []
    for item in pools:
        if not isinstance(item, dict):
            continue
        nombre = item.get("name") or item.get("title") or item.get("productName")
        if not nombre:
            continue
        offers = item.get("offers")
        if not isinstance(offers, dict):
            offers = item
        precio = _precio(
            offers.get("price") or offers.get("lowPrice") or item.get("price") or
            item.get("salePrice") or item.get("bestPrice")
        )
        if not precio:
            continue
        url = _url(base_url, item.get("url") or item.get("link") or item.get("productUrl"))
        if not url and item.get("handle"):
            origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
            url = _url(origin, "/products/" + str(item["handle"]))
        if not url:
            continue
        stock = 0 if item.get("available") is False or item.get("inStock") is False else 1
        producto = {
            "tienda": tienda,
            "nombre": str(nombre).strip(),
            "precio": precio,
            "stock": stock,
            "imagen": _imagen(item.get("image") or item.get("imageUrl") or item.get("thumbnail"), base_url),
            "url": _normalizar_url(url),
            "id_producto": str(item.get("id") or item.get("productId") or item.get("sku") or item.get("handle") or url),
        }
        if _producto_relevante(producto):
            productos.append(producto)
    return productos


def _descubrir_sitemaps(session, base_url, presupuesto):
    """Devuelve URLs de fichas de producto descubiertas en sitemaps.

    Se recorren índices recursivamente y no se filtran por palabras de hardware.
    """
    raiz = urlparse(base_url)
    candidatos = [
        "/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml",
        "/product-sitemap.xml", "/products-sitemap.xml", "/sitemap_products.xml",
        "/wp-sitemap-posts-product-1.xml",
    ]
    cola = []
    vistos_sitemap = set()
    productos = set()

    for path in candidatos:
        u = _normalizar_url(_url(base_url, path))
        if u:
            cola.append(u)

    while cola and not presupuesto.vencido() and len(productos) < MAX_SITEMAP_URLS:
        sitemap = cola.pop(0)
        if sitemap in vistos_sitemap:
            continue
        vistos_sitemap.add(sitemap)
        if not presupuesto.puede_request():
            break
        try:
            r = session.get(sitemap, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code != 200 or not r.text:
            continue

        locs = [unescape(x.strip()) for x in re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.I | re.S)]
        for loc in locs:
            u = _normalizar_url(loc)
            if not u or not _es_misma_tienda(u, base_url):
                continue
            if _es_fuente_excluida(u):
                continue
            path = urlparse(u).path.lower()
            if _es_producto_url(u) or ("product" in path and not path.endswith(".xml")):
                productos.add(u)
            elif u.lower().endswith(".xml") and len(vistos_sitemap) < 300:
                cola.append(u)
            if len(productos) >= MAX_SITEMAP_URLS:
                break
    return sorted(productos)


def _descubrir_links_catalogo(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    candidatos = []
    vistos = set()
    for a in soup.select("a[href]"):
        href = _normalizar_url(_url(base_url, a.get("href")))
        if not href or href in vistos or not _es_misma_tienda(href, base_url):
            continue
        vistos.add(href)
        if _es_fuente_excluida(href) or _es_producto_url(href):
            continue
        texto = f"{href} {a.get_text(' ', strip=True)}".lower()
        if any(m in texto for m in PRODUCT_MARKERS) or PAGE_RE.search(href):
            candidatos.append(href)
    return candidatos[:200]


def _api_woocommerce(session, base_url, tienda, presupuesto):
    """WooCommerce Store API pública. Devuelve productos y si la API respondió."""
    productos = []
    page = 1
    funciono = False
    while page <= 1000 and not presupuesto.vencido():
        if not presupuesto.puede_request():
            break
        url = _url(base_url, f"/wp-json/wc/store/v1/products?per_page=100&page={page}")
        try:
            r = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except Exception:
            break
        if not isinstance(data, list):
            break
        funciono = True
        encontrados = _parse_json_products(data, base_url, tienda)
        productos.extend(encontrados)
        if not data:
            break
        total_pages = r.headers.get("X-WP-TotalPages")
        if total_pages:
            try:
                if page >= int(total_pages):
                    break
            except ValueError:
                pass
        if len(data) < 100:
            break
        page += 1
    return productos, funciono


def _api_shopify(session, base_url, tienda, presupuesto):
    productos = []
    page = 1
    funciono = False
    while page <= 1000 and not presupuesto.vencido():
        if not presupuesto.puede_request():
            break
        u = _url(base_url, f"/products.json?limit=250&page={page}")
        try:
            r = session.get(u, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except Exception:
            break
        items = data.get("products") if isinstance(data, dict) else data
        if not isinstance(items, list):
            break
        funciono = True
        productos.extend(_parse_json_products(items, base_url, tienda))
        if len(items) < 250:
            break
        page += 1
    return productos, funciono


def _api_magento(session, base_url, tienda, presupuesto):
    productos = []
    page = 1
    funciono = False
    while page <= 1000 and not presupuesto.vencido():
        if not presupuesto.puede_request():
            break
        u = _url(base_url, f"/rest/V1/products?searchCriteria[currentPage]={page}&searchCriteria[pageSize]=100")
        try:
            r = session.get(u, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except Exception:
            break
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            break
        funciono = True
        for item in data["items"]:
            nombre = item.get("name")
            price = _precio(item.get("price"))
            if not nombre or not price:
                continue
            sku = item.get("sku") or ""
            # Magento REST no siempre devuelve la URL pública. Se conserva el
            # SKU como identidad y luego se completa desde sitemap/HTML.
            productos.append({
                "tienda": tienda, "nombre": str(nombre).strip(), "precio": price,
                "stock": 1, "imagen": None, "url": _url(base_url, "/catalog/product/view/" + str(sku)),
                "id_producto": str(sku),
            })
        total = data.get("total_count")
        if total is not None:
            try:
                if page * 100 >= int(total):
                    break
            except (TypeError, ValueError):
                pass
        if len(data["items"]) < 100:
            break
        page += 1
    return productos, funciono


def _extraer_fuente_html(session, primera_url, tienda, presupuesto):
    productos = []
    vistos = set()
    visitadas = set()
    url = primera_url
    while url and not presupuesto.vencido() and len(productos) < MAX_PRODUCTOS:
        url = _normalizar_url(url)
        if not url or url in visitadas:
            break
        visitadas.add(url)
        presupuesto.paginas += 1
        if not presupuesto.puede_request():
            break
        try:
            r = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        encontrados = _extraer_jsonld(r.text, r.url, tienda)
        if not encontrados:
            encontrados = _extraer_html(r.text, r.url, tienda)
        for p in encontrados:
            clave = _normalizar_url(p.get("url")) or p.get("id_producto")
            if clave and clave not in vistos:
                vistos.add(clave)
                productos.append(p)
        siguiente = _siguiente_pagina(BeautifulSoup(r.text, "html.parser"), r.url)
        if not siguiente:
            break
        url = siguiente
    return productos, len(visitadas)


def _extraer_detalles_en_paralelo(urls, tienda, presupuesto):
    resultados = []
    if not urls or presupuesto.vencido():
        return resultados

    # No se comparte una requests.Session entre hilos para evitar problemas con
    # adaptadores. Cada worker usa requests con los mismos headers.
    def uno(url):
        if presupuesto.vencido():
            return None
        if not presupuesto.puede_request():
            return None
        return _extraer_detalle(url, tienda)

    workers = min(DETAIL_WORKERS, max(1, len(urls)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(uno, u): u for u in urls}
        for futuro in as_completed(futuros):
            try:
                p = futuro.result()
            except Exception:
                p = None
            if p:
                resultados.append(p)
    return resultados


def extraer_desde_config(config):
    tienda = config["tienda"]
    base_url = _normalizar_url(config["url"])
    presupuesto = Presupuesto()
    session = session_con_reintentos(intentos=1)
    warnings = []
    productos = []
    vistos = set()
    fuentes = []
    paginas_catalogo = 0

    def agregar(lista):
        nuevos = 0
        for p in lista or []:
            if not p or not _producto_relevante(p):
                continue
            p["tienda"] = tienda
            p["url"] = _normalizar_url(p.get("url"))
            clave = p.get("url") or p.get("id_producto")
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            productos.append(p)
            nuevos += 1
            if len(productos) >= MAX_PRODUCTOS:
                break
        presupuesto.productos = len(productos)
        return nuevos

    if not base_url or not presupuesto.puede_request():
        return {"ok": False, "tienda": tienda, "productos": [], "warnings": ["No se pudo iniciar"], "salud": "FAILED", "completitud": "baja"}

    try:
        portada = session.get(base_url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        return {"ok": False, "tienda": tienda, "productos": [], "warnings": [f"Portada inaccesible: {exc}"], "salud": "FAILED", "completitud": "baja"}

    if portada.status_code in (401, 403, 429):
        return {"ok": False, "tienda": tienda, "productos": [], "warnings": [f"Acceso bloqueado HTTP {portada.status_code}"], "salud": "BLOCKED", "completitud": "baja"}
    if portada.status_code != 200:
        return {"ok": False, "tienda": tienda, "productos": [], "warnings": [f"Portada HTTP {portada.status_code}"], "salud": "FAILED", "completitud": "baja"}

    # 1) APIs públicas. Si una API funciona, es la fuente de mayor confianza.
    plataformas = {str(x).lower() for x in config.get("plataformas", [])}
    api_productos = []
    api_ok = False
    if "shopify" in plataformas:
        api_productos, api_ok = _api_shopify(session, base_url, tienda, presupuesto)
        if api_ok:
            fuentes.append({"tipo": "shopify", "productos": len(api_productos)})
    elif "tiendanube" in plataformas:
        # Tiendanube no expone una API pública de catálogo sin token. Se continúa
        # con sitemap/HTML, que sí es público.
        pass
    if "magento" in plataformas and not api_ok:
        api_productos, api_ok = _api_magento(session, base_url, tienda, presupuesto)
        if api_ok:
            fuentes.append({"tipo": "magento", "productos": len(api_productos)})
    if not api_ok:
        api_productos, api_ok = _api_woocommerce(session, base_url, tienda, presupuesto)
        if api_ok:
            fuentes.append({"tipo": "woocommerce_store_api", "productos": len(api_productos)})

    agregar(api_productos)

    # 2) Sitemap completo: se usa para conocer cuántas fichas existen, sin
    # aplicar filtros de relevancia.
    sitemap_urls = _descubrir_sitemaps(session, base_url, presupuesto)
    sitemap_urls = [u for u in sitemap_urls if _es_producto_url(u)]
    sitemap_urls = list(dict.fromkeys(sitemap_urls))
    expected_urls = len(sitemap_urls)

    if sitemap_urls:
        fuentes.append({"tipo": "sitemap", "urls": expected_urls})

    # 3) Si la API no cubrió todo o el sitemap tiene URLs no presentes en la API,
    # completar mediante las fichas del sitemap. Esto arregla tiendas mixtas y
    # APIs incompletas.
    urls_faltantes = [u for u in sitemap_urls if u not in vistos]
    if urls_faltantes and not presupuesto.vencido():
        detalle = _extraer_detalles_en_paralelo(urls_faltantes, tienda, presupuesto)
        agregar(detalle)

    # 4) Fallback HTML: categorías/tienda y paginación real.
    # Se ejecuta aunque haya sitemap si la cobertura detectada todavía es baja.
    html_urls = list(config.get("catalog_urls", []))
    html_urls.extend(_descubrir_links_catalogo(portada.text, base_url))
    html_urls = list(dict.fromkeys(_normalizar_url(u) for u in html_urls if u))
    html_urls = [u for u in html_urls if _es_misma_tienda(u, base_url) and not _es_fuente_excluida(u) and not _es_producto_url(u)]

    # Priorizar URLs de catálogo reales.
    html_urls.sort(key=lambda u: (0 if any(x in u.lower() for x in ("/tienda", "/productos", "/categoria", "/categorias", "/shop", "/category")) else 1, u))
    for catalog_url in html_urls[:80]:
        if presupuesto.vencido():
            break
        antes = len(productos)
        extraidos, paginas = _extraer_fuente_html(session, catalog_url, tienda, presupuesto)
        paginas_catalogo += paginas
        agregar(extraidos)
        if len(productos) > antes:
            fuentes.append({"tipo": "html", "url": catalog_url, "productos": len(productos) - antes, "paginas": paginas})

    # Si no hubo sitemap, la cantidad de URLs de producto encontrada en HTML es
    # la mejor señal disponible. Se cuenta junto con las fichas extraídas.
    discovered_from_products = set(sitemap_urls)
    discovered_from_products.update(
        p.get("url") for p in productos if p.get("url") and _es_producto_url(p.get("url"))
    )
    if expected_urls == 0:
        expected_urls = len(discovered_from_products)

    extracted_urls = set(p.get("url") for p in productos if p.get("url"))
    if expected_urls:
        cobertura = min(1.0, len(extracted_urls & discovered_from_products) / expected_urls)
    else:
        cobertura = 1.0 if productos else 0.0

    if presupuesto.vencido():
        salud = "PARTIAL" if productos else "TIMEOUT"
        completitud = "media" if productos else "baja"
        warnings.append(
            f"Presupuesto agotado: {presupuesto.requests} requests, {presupuesto.paginas} páginas"
        )
    elif productos and expected_urls and cobertura < 0.98:
        salud = "PARTIAL"
        completitud = "media"
        warnings.append(f"Cobertura de fichas {cobertura:.1%} ({len(extracted_urls & discovered_from_products)}/{expected_urls})")
    elif productos:
        salud = "HEALTHY"
        completitud = "alta"
    else:
        salud = "NO_SOURCE"
        completitud = "baja"
        warnings.append("No se encontró ningún producto con precio utilizable")

    # Si sitemap + extracción coinciden, tenemos una señal fuerte de catálogo
    # completo. Si sólo encontramos una página, jamás la marcamos como completa.
    if expected_urls and len(extracted_urls & discovered_from_products) == 0:
        salud = "NO_SOURCE"
        completitud = "baja"

    return {
        "ok": bool(productos),
        "tienda": tienda,
        "productos": productos[:MAX_PRODUCTOS],
        "con_imagen": sum(1 for p in productos if p.get("imagen")),
        "warnings": warnings,
        "salud": salud,
        "completitud": completitud,
        "parcial": salud != "HEALTHY",
        "requests": presupuesto.requests,
        "paginas": presupuesto.paginas + paginas_catalogo,
        "fuentes": fuentes,
        "expected_product_urls": expected_urls,
        "discovered_product_urls": len(discovered_from_products),
        "extracted_product_urls": len(extracted_urls & discovered_from_products),
        "coverage": round(cobertura, 4),
    }


def extraer():
    raise RuntimeError("Los extractores automáticos deben definir CONFIG y llamar a extraer_desde_config(CONFIG)")
