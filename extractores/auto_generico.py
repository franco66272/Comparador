"""
Motor universal de adquisición de catálogos.

La prioridad es descubrir fuentes de productos, no recorrer URLs indiscriminadamente.
El motor:
- prueba fuentes estructuradas primero;
- puntúa categorías y productos antes de recorrerlos;
- limita candidatos, requests, páginas y productos;
- combina varias fuentes cuando aportan cobertura;
- detecta contenido irrelevante;
- devuelve métricas y nivel de completitud para el validador.
"""
import json
import re
import time
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .utils import parse_precio_ar, session_con_reintentos

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

MAX_SEGUNDOS = 150
MAX_REQUESTS = 120
MAX_CANDIDATAS = 80
MAX_FUENTES = 8
MAX_PAGINAS = 80
MAX_PRODUCTOS = 10000
HTTP_TIMEOUT = 9
MAX_SIN_RESULTADOS = 3
MAX_LINKS_FALLBACK = 20
PROBE_LIMIT = 18

PRODUCTO_INCLUIR = (
    "pc", "computadora", "computacion", "hardware", "componente", "componentes",
    "mother", "motherboard", "placa madre",
    "procesador", "processor", "cpu", "cpus", "ryzen", "threadripper",
    "core i3", "core i5", "core i7", "core i9",
    "gpu", "gpus", "vga", "placa de video", "placa-de-video",
    "geforce", "radeon", "rtx", "gtx", "rx ",
    "memoria", "ram", "ddr", "ssd", "nvme", "hdd", "disco", "almacenamiento",
    "fuente", "psu", "gabinete", "case", "cooler", "watercooler",
    "water-cooling", "water-cooler", "refrigeracion",
    "monitor", "teclado", "keyboard", "mouse", "auricular", "auriculares",
    "headset", "webcam", "joystick", "gamepad", "notebook", "laptop",
    "router", "switch", "wifi", "wi-fi", "ethernet", "red", "periferico",
    "perifericos", "microfono", "micrófono", "ups", "capturadora",
)

EXCLUIR = (
    "cocina", "living", "comedor", "mueble", "muebles", "placard",
    "cama", "colchon", "colchón", "despensero", "tocador", "biblioteca",
    "pileta", "piscina", "jardin", "jardín", "hogar", "bazar", "limpieza",
    "electrodomestico", "electrodoméstico", "freidora", "pava electrica",
    "pava-electrica", "lavarropas", "heladera", "vestidor", "sofa", "sofá",
    "sillon", "sillón", "ropa", "calzado", "juguete", "juguetes", "mascota",
    "alimento", "mattress", "colchones", "muebles-de-jardin",
)

SOURCE_EXCLUDE = EXCLUIR + (
    "contacto", "nosotros", "quienes-somos", "privacidad", "terminos",
    "politicas", "login", "register", "carrito", "checkout", "wishlist",
    "blog", "faq", "preguntas-frecuentes", "sobre-nosotros",
)

CATEGORY_MARKERS = (
    "/categoria", "/categorias", "/category", "/categories", "/collection",
    "/collections", "/tienda/", "/shop/", "/hardware", "/componentes",
    "/computacion", "/perifericos", "/placas", "/procesadores", "/memorias",
    "/almacenamiento", "/storage", "/monitores", "/gabinetes", "/refrigeracion",
    "/notebooks", "/notebook", "/accesorios", "/productos/", "/products/",
)

PRODUCT_PATH_RE = re.compile(r"/(?:producto|product|productos|products)/[^/]+", re.I)
PAGE_RE = re.compile(r"(?:^|[?&])(?:page|p|pagina|pageNumber|page_num)=\d+", re.I)


class Presupuesto:
    def __init__(self):
        self.inicio = time.monotonic()
        self.requests = 0
        self.paginas = 0
        self.fuentes = 0
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
            p.scheme.lower(),
            p.netloc.lower(),
            p.path.rstrip("/") or "/",
            "",
            p.query,
            "",
        ))
    except Exception:
        return str(url)


def _url(base, valor):
    if not valor:
        return None
    valor = str(valor).strip()
    if valor.startswith("//"):
        return "https:" + valor
    return urljoin(base, valor)


def _coincide(valor, termino):
    valor = str(valor or "").lower()
    termino = termino.lower()
    if len(termino) <= 3:
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(termino) + r"(?![a-z0-9])", valor))
    return termino in valor


def _score_relevancia(texto):
    valor = str(texto or "").lower()
    negativos = sum(1 for x in EXCLUIR if _coincide(valor, x))
    positivos = sum(1 for x in PRODUCTO_INCLUIR if _coincide(valor, x))
    score = positivos * 2 - negativos * 7

    # Modelos y nomenclaturas muy comunes en hardware.
    if re.search(r"\b(?:rtx|gtx|rx|radeon|geforce)\s*\d{3,4}\b", valor):
        score += 5
    if re.search(r"\bryzen\s*[3579]\b|\bcore\s+i[3579]\b", valor):
        score += 5
    if re.search(r"\b(?:ddr[345]|nvme|m\.?2|sata|hdmi|displayport)\b", valor):
        score += 2
    return score


def _texto_relevante(texto, umbral=2):
    return _score_relevancia(texto) >= umbral


def _producto_relevante(producto):
    nombre = str(producto.get("nombre", ""))
    url = str(producto.get("url", ""))
    score_nombre = _score_relevancia(nombre)
    if score_nombre < 1 and not _texto_relevante(url, 4):
        return False
    if any(_coincide(nombre, x) for x in EXCLUIR):
        return False
    return True


def _precio(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        n = int(round(float(valor)))
        return n if 100 <= n <= 100_000_000 else None
    n = parse_precio_ar(str(valor))
    return n if n and 100 <= n <= 100_000_000 else None


IMAGE_PLACEHOLDERS = (
    "a12.svg", "a13.svg", "a14.svg", "fuego.png",
    "placeholder", "no-image", "no_image", "default-image", "copito.png",
)

def _imagen_valida(url):
    valor = str(url or "").strip().lower()
    if not valor or valor.startswith("data:"):
        return False
    return not any(x in valor for x in IMAGE_PLACEHOLDERS)

def _imagen(img, base):
    if not img:
        return None
    if isinstance(img, str):
        valor = _url(base, img)
        return valor if _imagen_valida(valor) else None
    for atributo in (
        "data-zoom-image", "data-large-image", "data-full",
        "data-original", "data-image", "data-lazy-src",
        "data-src", "src",
    ):
        valor = img.get(atributo)
        if valor:
            candidata = _url(base, valor)
            if _imagen_valida(candidata):
                return candidata
    if img.get("data-srcset"):
        for item in str(img["data-srcset"]).split(","):
            valor = item.strip().split(" ")[0]
            candidata = _url(base, valor)
            if _imagen_valida(candidata):
                return candidata
    if img.get("srcset"):
        for item in str(img["srcset"]).split(","):
            valor = item.strip().split(" ")[0]
            candidata = _url(base, valor)
            if _imagen_valida(candidata):
                return candidata
    return None

def _imagen_desde_html(nodo, base):
    if not nodo:
        return None
    # Algunos motores de e-commerce dejan la imagen real en noscript o
    # atributos HTML mientras src apunta al placeholder.
    texto = str(nodo)
    urls = re.findall(r'https?://[^\"\'\s>]+', texto, re.I)
    for valor in urls:
        candidata = _url(base, valor)
        if _imagen_valida(candidata) and re.search(r'\.(?:jpe?g|png|webp|gif)(?:[?#]|$)', candidata, re.I):
            return candidata
    return None


def _producto_jsonld(data, base_url, tienda):
    if not isinstance(data, dict):
        return None
    tipo = data.get("@type")
    tipos = tipo if isinstance(tipo, list) else [tipo]
    if "Product" not in tipos:
        return None

    nombre = str(data.get("name") or "").strip()
    if not nombre:
        return None

    oferta = data.get("offers")
    if isinstance(oferta, list):
        oferta = oferta[0] if oferta else {}
    if not isinstance(oferta, dict):
        oferta = {}

    precio = _precio(oferta.get("price") or oferta.get("lowPrice") or data.get("price"))
    if not precio:
        return None

    disponibilidad = str(oferta.get("availability") or "").lower()
    stock = 1 if "instock" in disponibilidad else 0
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
    productos, vistos = [], set()
    for script in soup.select('script[type="application/ld+json"]'):
        texto = script.string or script.get_text()
        try:
            data = json.loads(texto)
        except Exception:
            continue
        objetos = []
        if isinstance(data, list):
            objetos = data
        elif isinstance(data, dict):
            objetos = [data]
            if isinstance(data.get("@graph"), list):
                objetos.extend(data["@graph"])

        pila = list(objetos)
        while pila:
            obj = pila.pop()
            if isinstance(obj, dict):
                producto = _producto_jsonld(obj, base_url, tienda)
                if producto and _producto_relevante(producto):
                    clave = producto["id_producto"]
                    if clave not in vistos:
                        vistos.add(clave)
                        productos.append(producto)
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        pila.append(value)
            elif isinstance(obj, list):
                pila.extend(obj)
    return productos


def _precio_card(card, nombre=None):
    # Primero usar campos explícitos de precio. Nunca inferir el precio desde
    # el nombre del producto: algunos vendedores incluyen ofertas antiguas,
    # cuotas o importes promocionales dentro del título.
    for nodo in card.select(
        "[data-price-amount], [data-price], [itemprop=price], "
        ".price, .precio, .product-price, .price-box, .special-price, .sale-price"
    ):
        valor = (
            nodo.get("data-price-amount")
            or nodo.get("data-price")
            or nodo.get("content")
            or nodo.get_text(" ", strip=True)
        )
        precio = _precio(valor)
        if precio:
            return precio, "structured"

    texto = card.get_text(" ", strip=True)
    if nombre:
        # Evitar que una cifra escrita dentro del título sea tomada como
        # precio real. Conservamos el resto del texto del card.
        texto_sin_nombre = texto.replace(str(nombre), " ")
    else:
        texto_sin_nombre = texto

    for patron in (r"\$\s*[\d.]+(?:,\d+)?", r"(?:ARS|ar\$)\s*[\d.]+(?:,\d+)?"):
        m = re.search(patron, texto_sin_nombre, re.I)
        if m:
            precio = _precio(m.group(0))
            if precio:
                return precio, "text"
    return None, None


def _precio_detalle(url):
    try:
        r = requests.get(
            url, timeout=8, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}
        )
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # 1) JSON-LD: fuente estructurada de mayor prioridad.
    for producto in _extraer_jsonld(r.text, url, ""):
        if producto.get("precio"):
            return int(producto["precio"])

    # 2) Metadatos específicos de producto.
    for nodo in soup.select('meta[property="product:price:amount"], meta[itemprop="price"]'):
        precio = _precio(nodo.get("content"))
        if precio:
            return precio

    # 3) Texto explícitamente asociado al precio principal del producto.
    texto = soup.get_text(" ", strip=True)
    patrones_prioritarios = (
        r"Precio\s+(?:especial|oferta|actual|promocional)\s*[:：]?\s*\$\s*([\d.]+(?:,\d+)?)",
        r"Precio\s*[:：]?\s*\$\s*([\d.]+(?:,\d+)?)",
    )
    for patron in patrones_prioritarios:
        m = re.search(patron, texto, re.I)
        if m:
            precio = _precio(m.group(1))
            if precio:
                return precio

    # 4) Selectores de precio dentro del bloque principal antes de
    # considerar listas de productos relacionados.
    for contenedor in soup.select("main, #content, .product-detail, .product-detail-page, .product, .producto")[:6]:
        for nodo in contenedor.select("[itemprop=price], .price, .precio, .product-price, .special-price, .current-price, .sale-price")[:15]:
            valor = nodo.get("content") or nodo.get("data-price") or nodo.get_text(" ", strip=True)
            precio = _precio(valor)
            if precio:
                return precio
    return None


def _nombre_card(card):
    for selector in (
        "[data-product-name]", "[data-name]", ".product-item-link",
        ".product-item-name", ".product-name", ".product-title",
        ".product-name a", ".name", ".title",
        "[itemprop=name]", "h1", "h2", "h3", "h4", "h5",
    ):
        nodo = card.select_one(selector)
        if not nodo:
            continue
        valor = (
            nodo.get("data-product-name") or nodo.get("data-name")
            or nodo.get("title") or nodo.get_text(" ", strip=True)
        )
        if valor and len(valor.strip()) >= 4:
            return valor.strip()
    return None


def _extraer_card(card, base_url, tienda):
    nombre = _nombre_card(card)
    if not nombre:
        return None
    enlace = card.select_one("a[href]")
    if not enlace:
        return None
    href = _url(base_url, enlace.get("href"))
    if not href:
        return None
    precio, fuente_precio = _precio_card(card, nombre)
    patron_nombre = re.search(r"\$\s*([\d.]+(?:,\d+)?)", str(nombre or ""))

    # Si el card no contiene un precio estructurado y el nombre sí contiene
    # un importe, verificar la ficha individual. No interpretar nunca ese
    # importe del título como precio del producto.
    if not precio:
        if patron_nombre:
            verificado = _precio_detalle(href)
            if not verificado:
                return None
            precio = verificado
            fuente_precio = "detail_page"
        else:
            return None

    # Caso especialmente peligroso: el único importe visible en la tarjeta
    # coincide con un monto escrito dentro del nombre (por ejemplo,
    # "OFERTA $ 240"). En ese escenario jamás confiar en el título: verificar
    # la página individual del producto.
    if patron_nombre and fuente_precio in ("text", "structured"):
        monto_nombre = _precio(patron_nombre.group(1))
        if monto_nombre and int(precio) == int(monto_nombre):
            verificado = _precio_detalle(href)
            if verificado:
                precio = verificado
                fuente_precio = "detail_page"
            else:
                return None
    imagen_nodo = card.select_one("img")
    imagen = _imagen(imagen_nodo, base_url)
    if not imagen:
        imagen = _imagen_desde_html(card, base_url)

    product_id = (
        card.get("data-product-id") or card.get("data-productid")
        or card.get("data-id") or enlace.get("data-product-id")
        or href
    )
    producto = {
        "tienda": tienda,
        "nombre": nombre,
        "precio": precio,
        "stock": 1,
        "imagen": imagen,
        "url": href,
        "id_producto": str(product_id),
    }
    return producto if _producto_relevante(producto) else None


def _detectar_cards(soup):
    selectores = (
        ".product-item", ".product-card", ".product-card-item",
        ".item.product", "article.product", "[data-product-id]",
        "[data-productid]", "[itemtype*='Product']",
    )
    mejor = []
    for selector in selectores:
        try:
            encontrados = soup.select(selector)
        except Exception:
            continue
        validos = []
        for card in encontrados:
            if not card.select_one("a[href]"):
                continue
            if not (_precio_card(card) or card.select_one("[itemprop=price]")):
                continue
            nombre = _nombre_card(card)
            if not nombre or not _producto_relevante({"nombre": nombre, "url": ""}):
                continue
            validos.append(card)
        if len(validos) > len(mejor):
            mejor = validos
    if mejor:
        return mejor

    candidatos = []
    for elemento in soup.find_all(["article", "li", "div"]):
        if len(elemento.find_all(["article", "li", "div"])) > 45:
            continue
        texto = elemento.get_text(" ", strip=True)
        if len(texto) < 15 or len(texto) > 1500:
            continue
        if not _texto_relevante(texto):
            continue
        if not elemento.select_one("a[href]") or not _precio_card(elemento):
            continue
        candidatos.append(elemento)

    finales = []
    for candidato in candidatos:
        if any(otro is not candidato and otro in candidato.descendants for otro in candidatos):
            continue
        finales.append(candidato)
    return finales


def _extraer_html(html, base_url, tienda):
    soup = BeautifulSoup(html, "html.parser")
    productos = []
    vistos = set()
    for card in _detectar_cards(soup):
        producto = _extraer_card(card, base_url, tienda)
        if not producto:
            continue
        clave = producto["id_producto"]
        if clave in vistos:
            continue
        vistos.add(clave)
        productos.append(producto)

    if not productos:
        # Fallback acotado para layouts no estándar.
        for a in soup.select("a[href]")[:250]:
            href = _url(base_url, a.get("href"))
            if not href or not PRODUCT_PATH_RE.search(urlparse(href).path):
                continue
            nombre = a.get_text(" ", strip=True) or a.get("title") or ""
            nodo = a
            mejor = None
            for _ in range(5):
                nodo = nodo.parent
                if nodo is None:
                    break
                if _precio_card(nodo) and len(nodo.get_text(" ", strip=True)) < 2200:
                    mejor = nodo
                    break
            if mejor is None:
                continue
            producto = _extraer_card(mejor, base_url, tienda)
            if producto and producto["url"] == href:
                if href not in vistos:
                    vistos.add(href)
                    productos.append(producto)
    return productos


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

    # Sólo acepta paginación explícita, jamás un enlace arbitrario.
    for nodo in soup.select("a[href]"):
        siguiente = _normalizar_url(_url(actual, nodo.get("href")))
        if not siguiente:
            continue
        p = urlparse(siguiente)
        if p.netloc.lower() != urlparse(actual).netloc.lower():
            continue
        if PAGE_RE.search(p.query):
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
        if not pools:
            pools = [data]
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

        oferta = item.get("offers")
        if not isinstance(oferta, dict):
            oferta = item

        precio = (
            oferta.get("price")
            or oferta.get("lowPrice")
            or item.get("price")
            or item.get("salePrice")
            or item.get("bestPrice")
        )
        precio = _precio(precio)
        if not precio:
            continue

        url = _url(
            base_url,
            item.get("url") or item.get("link") or item.get("productUrl")
        )
        if not url and item.get("handle"):
            parsed = urlparse(base_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            url = _url(origin, "/products/" + str(item.get("handle")))
        if not url and item.get("id") and "/rest/" in urlparse(base_url).path:
            parsed = urlparse(base_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            url = _url(origin, "/catalog/product/view/?id=" + str(item.get("id")))

        producto = {
            "tienda": tienda,
            "nombre": str(nombre).strip(),
            "precio": precio,
            "stock": 1 if item.get("available", item.get("inStock", True)) else 0,
            "imagen": _imagen(
                item.get("image") or item.get("imageUrl") or item.get("thumbnail"),
                base_url,
            ),
            "url": url,
            "id_producto": str(
                item.get("id") or item.get("productId")
                or item.get("sku") or item.get("handle") or url
            ),
        }

        if producto["url"] and _producto_relevante(producto):
            productos.append(producto)

    return productos


def _descubrir_sitemap(session, base_url, presupuesto):
    candidatos = []
    for path in (
        "/product-sitemap.xml", "/products-sitemap.xml", "/sitemap_products.xml",
        "/sitemap.xml", "/sitemap_index.xml",
    ):
        if not presupuesto.puede_request():
            break
        try:
            r = session.get(_url(base_url, path), headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        locs = [unescape(x.strip()) for x in re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.I | re.S)]
        for loc in locs[:500]:
            if urlparse(loc).netloc.lower() != urlparse(base_url).netloc.lower():
                continue
            score = _score_relevancia(loc)
            if score < 2:
                continue
            path_l = urlparse(loc).path.lower()
            if any(x in path_l for x in SOURCE_EXCLUDE):
                continue
            candidates.append(("sitemap", loc, score + (3 if PRODUCT_PATH_RE.search(path_l) else 0)))
        if candidates:
            break

    candidates.sort(key=lambda x: (-x[2], x[1]))
    return candidates[:40]


def _descubrir_endpoints(html, base_url):
    encontrados = set()
    patrones = (
        r'["\']([^"\']*(?:/api/|/graphql|/products(?:\.json)?|/catalog[^"\']*)["\'])',
        r'https?://[^"\']+',
    )
    for patron in patrones:
        for match in re.findall(patron, html, re.I):
            valor = match[0] if isinstance(match, tuple) else match
            if not valor:
                continue
            if not valor.startswith(("http://", "https://", "/")):
                continue
            if valor.startswith("/"):
                valor = _url(base_url, valor)
            if not valor:
                continue
            p = urlparse(valor)
            if p.netloc.lower() != urlparse(base_url).netloc.lower():
                continue
            if any(x in valor.lower() for x in SOURCE_EXCLUDE):
                continue
            if any(x in valor.lower() for x in ("/api/", "/graphql", "products.json", "/catalog")):
                encontrados.add(_normalizar_url(valor))
    return list(encontrados)[:25]


def _descubrir_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.lower()
    candidatos = []
    vistos = set()

    for a in soup.select("a[href]"):
        href = _normalizar_url(_url(base_url, a.get("href")))
        if not href or href in vistos:
            continue
        p = urlparse(href)
        if p.netloc.lower() != host:
            continue
        vistos.add(href)

        texto = a.get_text(" ", strip=True)
        datos = f"{href} {texto}"
        path = p.path.lower()
        if any(x in datos.lower() for x in SOURCE_EXCLUDE):
            continue
        if len(path.split("/")) > 6:
            continue

        score = _score_relevancia(datos)
        if any(x in datos.lower() for x in CATEGORY_MARKERS):
            score += 3
        if PRODUCT_PATH_RE.search(path):
            score += 2
        if score >= 3:
            candidatos.append(("html", href, score))
    candidatos.sort(key=lambda x: (-x[2], x[1]))
    return candidatos[:50]


def _crear_candidatos(config, html, base_url, session, presupuesto):
    candidatos = []
    seen = set()

    def add(kind, url, score, reason=""):
        url = _normalizar_url(url)
        if not url or url in seen:
            return
        if urlparse(url).netloc.lower() != urlparse(base_url).netloc.lower():
            return
        if any(x in url.lower() for x in SOURCE_EXCLUDE):
            return
        seen.add(url)
        candidatos.append({"kind": kind, "url": url, "score": score, "reason": reason})

    # Fuentes estructuradas conocidas.
    plataformas = {str(x).lower() for x in config.get("plataformas", [])}
    if "shopify" in plataformas:
        add("shopify", _url(base_url, "/products.json?limit=250"), 100, "plataforma")
    if "magento" in plataformas:
        add("magento", _url(base_url, "/rest/V1/products?searchCriteria[pageSize]=100"), 100, "plataforma")
        add("magento", _url(base_url, "/rest/default/V1/products?searchCriteria[pageSize]=100"), 98, "plataforma")

    for u in config.get("fuentes_prioritarias", [])[:30]:
        add("config", u, 20, "configuracion previa")
    for u in config.get("catalog_urls", [])[:40]:
        add("config", u, 12, "catalogo historico")

    # JSON-LD de portada: si ya hay productos, la propia portada es una fuente válida.
    if _extraer_jsonld(html, base_url, config["tienda"]):
        add("jsonld", base_url, 90, "JSON-LD Product")

    for u in _descubrir_endpoints(html, base_url):
        add("endpoint", u, 70, "endpoint detectado")

    for kind, u, score in _descubrir_links(html, base_url):
        add(kind, u, score, "enlace relevante")

    for kind, u, score in _descubrir_sitemap(session, base_url, presupuesto):
        add(kind, u, score, "sitemap filtrado")

    # La portada siempre queda al final como fallback.
    add("html", base_url, 5, "fallback")

    candidatos.sort(key=lambda x: (-x["score"], x["url"]))
    return candidatos[:MAX_CANDIDATAS]


def _probar_fuente(session, fuente, tienda, presupuesto):
    if not presupuesto.puede_request():
        return None, 0

    url = fuente["url"]
    try:
        response = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        return None, 0

    if response.status_code != 200:
        return None, 0

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "json" in content_type or url.lower().endswith((".json", ".json?")):
        try:
            data = response.json()
        except Exception:
            return None, 0
        productos = _parse_json_products(data, url, tienda)
        return productos, len(productos)

    productos = _extraer_jsonld(response.text, url, tienda)
    if not productos:
        productos = _extraer_html(response.text, url, tienda)
    return productos, len(productos)


def _extraer_fuente_html(session, primera_url, tienda, presupuesto):
    productos, vistos, visitadas = [], set(), set()
    url = primera_url
    sin_resultados = 0

    while url and not presupuesto.vencido() and len(productos) < MAX_PRODUCTOS:
        normalizada = _normalizar_url(url)
        if normalizada in visitadas:
            break
        visitadas.add(normalizada)
        presupuesto.paginas += 1

        if not presupuesto.puede_request():
            break

        try:
            response = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if response.status_code != 200:
            break

        encontrados = _extraer_jsonld(response.text, url, tienda)
        if not encontrados:
            encontrados = _extraer_html(response.text, url, tienda)

        nuevos = 0
        for producto in encontrados:
            if not _producto_relevante(producto):
                continue
            clave = producto.get("id_producto") or producto.get("url")
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            productos.append(producto)
            nuevos += 1

        sin_resultados = sin_resultados + 1 if nuevos == 0 else 0
        if sin_resultados >= MAX_SIN_RESULTADOS:
            break

        siguiente = _siguiente_pagina(BeautifulSoup(response.text, "html.parser"), url)
        if not siguiente:
            break
        url = siguiente

    return productos


def _extraer_fuente_json(session, url, tienda, presupuesto, kind):
    productos = []
    paginas = 0
    actual = url

    while actual and not presupuesto.vencido() and paginas < 30:
        if not presupuesto.puede_request():
            break
        try:
            response = session.get(actual, headers=HEADERS, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            break
        if response.status_code != 200:
            break
        try:
            data = response.json()
        except Exception:
            break

        encontrados = _parse_json_products(data, actual, tienda)
        productos.extend(encontrados)
        paginas += 1
        presupuesto.paginas += 1

        # Shopify: page=; Magento: currentPage.
        if kind == "shopify":
            if len(encontrados) < 50:
                break
            sep = "&" if "?" in url else "?"
            actual = f"{url}{sep}page={paginas + 1}"
        elif kind == "magento":
            if len(encontrados) < 100:
                break
            base = url.split("?", 1)[0]
            actual = (
                f"{base}?searchCriteria[currentPage]={paginas + 1}"
                f"&searchCriteria[pageSize]=100"
            )
        else:
            break

    return productos


def extraer_desde_config(config):
    tienda = config["tienda"]
    base_url = _normalizar_url(config["url"])
    presupuesto = Presupuesto()
    session = session_con_reintentos(intentos=1)
    productos = []
    vistos = set()
    warnings = []
    fuentes_exitosas = []
    fuentes_consideradas = []
    complete_signal = False

    def agregar(lista):
        nuevos = 0
        for producto in lista or []:
            if not producto or not _producto_relevante(producto):
                continue
            producto["tienda"] = tienda
            clave = producto.get("id_producto") or producto.get("url")
            if not clave:
                continue
            if clave in vistos:
                continue
            vistos.add(clave)
            productos.append(producto)
            nuevos += 1
            if len(productos) >= MAX_PRODUCTOS:
                break
        presupuesto.productos = len(productos)
        return nuevos

    # Obtener portada una sola vez. Esto también permite detectar caída/bloqueo.
    if not presupuesto.puede_request():
        return {
            "ok": False, "tienda": tienda, "productos": [],
            "warnings": ["Presupuesto agotado antes de comenzar"],
            "salud": "TIMEOUT", "completitud": "baja",
        }

    try:
        response = session.get(base_url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        return {
            "ok": False, "tienda": tienda, "productos": [],
            "warnings": [f"No se pudo acceder a la portada: {exc}"],
            "salud": "FAILED", "completitud": "baja",
        }

    if response.status_code in (401, 403, 429):
        return {
            "ok": False, "tienda": tienda, "productos": [],
            "warnings": [f"Acceso bloqueado o limitado: HTTP {response.status_code}"],
            "salud": "BLOCKED", "completitud": "baja",
        }
    if response.status_code >= 500:
        return {
            "ok": False, "tienda": tienda, "productos": [],
            "warnings": [f"La tienda respondió HTTP {response.status_code}"],
            "salud": "FAILED", "completitud": "baja",
        }
    if response.status_code != 200:
        return {
            "ok": False, "tienda": tienda, "productos": [],
            "warnings": [f"La tienda respondió HTTP {response.status_code}"],
            "salud": "DISCOVERY_FAILED", "completitud": "baja",
        }

    html = response.text
    inicial = _extraer_jsonld(html, base_url, tienda)
    agregar(inicial)
    if inicial:
        complete_signal = True
        fuentes_exitosas.append({"url": base_url, "tipo": "jsonld", "productos": len(inicial)})

    candidatos = _crear_candidatos(config, html, base_url, session, presupuesto)
    print(f"[AUTO] Fuentes candidatas: {len(candidatos)}")

    # Primero se prueban fuentes para medir densidad. Sólo se recorren las que
    # realmente devuelven productos relevantes.
    usados = 0
    sin_aporte = 0
    probados = 0

    for fuente in candidatos:
        if presupuesto.vencido() or usados >= MAX_FUENTES:
            break
        if probados >= PROBE_LIMIT:
            break
        probados += 1
        fuentes_consideradas.append({
            "url": fuente["url"],
            "tipo": fuente["kind"],
            "score": fuente["score"],
        })

        try:
            if fuente["kind"] in ("shopify", "magento"):
                if fuente["kind"] == "shopify":
                    encontrados = _extraer_fuente_json(
                        session, fuente["url"].split("?")[0] + "?limit=250",
                        tienda, presupuesto, "shopify"
                    )
                else:
                    encontrados = _extraer_fuente_json(
                        session, fuente["url"], tienda, presupuesto, "magento"
                    )
            else:
                probe, densidad = _probar_fuente(session, fuente, tienda, presupuesto)
                if not probe:
                    continue
                # Una página producto es válida sólo como rescate; para categorías
                # y sitemaps se continúa con paginación.
                if fuente["kind"] in ("html", "jsonld") and (
                    PRODUCT_PATH_RE.search(urlparse(fuente["url"]).path)
                ):
                    encontrados = probe
                else:
                    encontrados = _extraer_fuente_html(
                        session, fuente["url"], tienda, presupuesto
                    )
                    if not encontrados:
                        encontrados = probe
            nuevos = agregar(encontrados)

            if nuevos:
                usados += 1
                fuentes_exitosas.append({
                    "url": fuente["url"],
                    "tipo": fuente["kind"],
                    "productos": nuevos,
                })
                sin_aporte = 0
            else:
                sin_aporte += 1
        except Exception as exc:
            warnings.append(f"{fuente['url']}: {exc}")

        # Dos fuentes consecutivas sin aporte tras haber conseguido catálogo
        # indican baja rentabilidad y evitan recorrer la tienda completa.
        if productos and sin_aporte >= 2:
            break

    if not productos:
        warnings.append("No se encontró un catálogo relevante utilizable.")

    if presupuesto.vencido():
        warnings.append(
            f"Circuit breaker: {MAX_SEGUNDOS}s/{MAX_REQUESTS} requests/"
            f"{MAX_PAGINAS} páginas/{MAX_PRODUCTOS} productos"
        )

    # Señal de completitud: una fuente estructurada agotó la paginación o se
    # detectó una portada con JSON-LD; de lo contrario la extracción se considera
    # como mínimo parcial y el validador conserva el catálogo anterior al fusionar.
    if presupuesto.vencido():
        salud = "PARTIAL" if productos else "TIMEOUT"
        completitud = "media" if productos else "baja"
    elif productos and (complete_signal or any(x["tipo"] in ("shopify", "magento") for x in fuentes_exitosas)):
        salud = "HEALTHY"
        completitud = "alta"
    elif productos:
        salud = "PARTIAL"
        completitud = "media"
    else:
        salud = "NO_SOURCE"

    return {
        "ok": bool(productos),
        "tienda": tienda,
        "productos": productos[:MAX_PRODUCTOS],
        "con_imagen": sum(1 for x in productos if x.get("imagen")),
        "warnings": warnings,
        "parcial": salud != "HEALTHY",
        "salud": salud,
        "completitud": completitud,
        "requests": presupuesto.requests,
        "paginas": presupuesto.paginas,
        "fuentes": presupuesto.fuentes,
        "fuentes_consideradas": fuentes_consideradas,
        "fuentes_exitosas": fuentes_exitosas,
    }
