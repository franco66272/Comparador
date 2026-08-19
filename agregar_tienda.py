import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


RAIZ = Path(__file__).parent
EXTRACTORES = RAIZ / "extractores"
CONFIG = RAIZ / "config"
REGISTRO = CONFIG / "tiendas_auto.json"

TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    )
}


def normalizar_url(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    return f"{parsed.scheme}://{parsed.netloc}"


def nombre_tienda(url):
    host = urlparse(url).netloc.lower()
    host = host.split(":")[0]
    host = host.removeprefix("www.")

    nombre = re.sub(r"[^a-zA-Z0-9]+", "_", host).strip("_")

    if not nombre:
        nombre = "tienda"

    return nombre.lower()


PENDIENTES = CONFIG / "tiendas_pendientes.json"


def registrar_pendiente(url, motivo):
    try:
        datos = json.loads(PENDIENTES.read_text(encoding="utf-8")) if PENDIENTES.exists() else {}
    except Exception:
        datos = {}
    lista = list(datos.get("tiendas", []))
    if url not in lista:
        lista.append(url)
    PENDIENTES.write_text(
        json.dumps(
            {"tiendas": lista, "motivo_ultimo": motivo},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def descargar(session, url):
    try:
        r = session.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        return r

    except requests.RequestException as exc:
        print(f"[ERROR] {exc}")
        return None


def detectar(html, base_url):
    low = html.lower()

    plataformas = []

    patrones = {
        "shopify": [
            "cdn.shopify.com",
            "shopify.theme",
            "shopify.routes",
            "/cdn/shop/",
        ],
        "vtex": [
            "vtex",
            "vtexid",
            "vtexassets",
        ],
        "tiendanube": [
            "tiendanube",
            "mitiendanube",
            "nuvemshop",
        ],
        "woocommerce": [
            "woocommerce",
            "wp-content/plugins/woocommerce",
        ],
        "nextjs": [
            "__next_data__",
            "_next/static",
        ],
        "magento": [
            "magento",
            "mage/",
        ],
        "prestashop": [
            "prestashop",
            "prestashop.js",
        ],
    }

    for plataforma, firmas in patrones.items():
        if any(firma in low for firma in firmas):
            plataformas.append(plataforma)

    if not plataformas:
        plataformas.append("no_reconocida")

    return plataformas


def extraer_jsonld(html):
    soup = BeautifulSoup(html, "html.parser")

    resultados = []

    for script in soup.select(
        'script[type="application/ld+json"]'
    ):
        texto = script.string or script.get_text()

        try:
            data = json.loads(texto)
        except Exception:
            continue

        if isinstance(data, list):
            resultados.extend(data)

        elif isinstance(data, dict):
            resultados.append(data)

    productos = []

    def recorrer(obj):
        if isinstance(obj, dict):
            tipo = obj.get("@type")

            if tipo == "Product" or (
                isinstance(tipo, list)
                and "Product" in tipo
            ):
                productos.append(obj)

            for valor in obj.values():
                recorrer(valor)

        elif isinstance(obj, list):
            for valor in obj:
                recorrer(valor)

    for item in resultados:
        recorrer(item)

    return productos



CATALOGO_MAX_URLS = 50
SITEMAP_MAX_URLS = 100

TECNOLOGIA = (
    "pc", "computadora", "computacion", "hardware", "componentes",
    "mother", "motherboard", "procesador", "processor", "cpu",
    "gpu", "vga", "placa", "video", "geforce", "radeon", "rtx", "gtx",
    "memoria", "ram", "ddr", "ssd", "nvme", "hdd", "disco", "storage",
    "fuente", "psu", "gabinete", "case", "cooler", "watercooler",
    "refrigeracion", "monitor", "teclado", "keyboard", "mouse",
    "auricular", "headset", "webcam", "joystick", "gamepad",
    "notebook", "laptop", "router", "switch", "wifi", "wi-fi",
    "ethernet", "red", "periferico", "microfono", "ups",
)

EXCLUIR_CATALOGO = (
    "cocina", "living", "comedor", "mueble", "muebles", "placard",
    "cama", "colchon", "colchón", "despensero", "tocador", "biblioteca",
    "pileta", "piscina", "jardin", "jardín", "hogar", "bazar", "limpieza",
    "electrodomestico", "electrodoméstico", "freidora", "pava",
    "lavarropas", "heladera", "vestidor", "sofa", "sofá", "sillon", "sillón",
    "juguete", "juguetes", "mascota", "alimento",
    "contacto", "nosotros", "quienes-somos", "privacidad", "terminos",
    "login", "register", "carrito", "checkout", "wishlist",
)


def puntuar_url_catalogo(url, texto=""):
    datos = f"{url} {texto}".lower()

    if any(x in datos for x in EXCLUIR_CATALOGO):
        return -100

    score = 0

    if any(x in datos for x in TECNOLOGIA):
        score += 5

    if any(
        x in datos
        for x in (
            "/categoria", "/categorias", "/category", "/collection",
            "/tienda/", "/shop/", "/hardware/", "/componentes",
            "/computacion", "/perifericos", "/placas", "/procesadores",
            "/memorias", "/almacenamiento",
        )
    ):
        score += 4

    if "/producto" in datos or "/product" in datos:
        score += 2

    return score


def seleccionar_catalogo(urls, limite=CATALOGO_MAX_URLS):
    vistos = set()
    categorias = []
    productos = []
    otros = []

    for url, texto in urls:
        if not url:
            continue
        url = url.split("#", 1)[0]
        if url in vistos:
            continue
        vistos.add(url)
        score = puntuar_url_catalogo(url, texto)
        if score <= 0:
            continue
        path = urlparse(url).path.lower()
        entrada = (score, url)
        if any(x in path for x in ("/categor", "/category", "/collection", "/tienda/", "/shop/")):
            categorias.append(entrada)
        elif any(x in path for x in ("/producto/", "/productos/", "/product/", "/products/")):
            productos.append(entrada)
        else:
            otros.append(entrada)

    for grupo in (categorias, productos, otros):
        grupo.sort(key=lambda x: (-x[0], x[1]))

    # Las categorías son la fuente primaria: una sola URL puede devolver cientos
    # de productos. Los productos individuales quedan como fallback.
    resultado = []
    # Pocas fuentes de alta señal; nunca convertir un sitemap generalista
    # en una lista masiva de URLs históricas.
    for grupo, cantidad in ((categorias, 30), (productos, 15), (otros, 5)):
        for _, url in grupo[:cantidad]:
            if url not in resultado:
                resultado.append(url)
            if len(resultado) >= limite:
                return resultado
    return resultado


def descubrir_urls(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower()
    encontrados = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()

        if not href:
            continue

        url = urljoin(base_url, href)
        parsed = urlparse(url)

        if parsed.netloc.lower() != base_host:
            continue

        texto = a.get_text(" ", strip=True)

        if puntuar_url_catalogo(url, texto) > 0:
            encontrados.append((url, texto))

    return seleccionar_catalogo(encontrados, limite=CATALOGO_MAX_URLS)


def descubrir_sitemap(session, base_url):
    encontrados = []

    for path in (
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/product-sitemap.xml",
    ):
        url = urljoin(base_url, path)
        r = descargar(session, url)

        if not r or r.status_code != 200:
            continue

        locs = re.findall(
            r"<loc>\s*(.*?)\s*</loc>",
            r.text,
            re.I | re.S,
        )

        for loc in locs:
            loc = unescape(loc.strip())

            if puntuar_url_catalogo(loc) > 0:
                encontrados.append((loc, ""))

            if len(encontrados) >= SITEMAP_MAX_URLS:
                break

        if encontrados:
            break

    return seleccionar_catalogo(
        encontrados,
        limite=SITEMAP_MAX_URLS,
    )


def descubrir_endpoints(html, base_url):
    encontrados = set()

    patrones = [
        r'https?://[^"\']+',
        r'["\']([^"\']*(?:api|graphql|products|catalog)[^"\']*)["\']',
    ]

    for patron in patrones:
        for match in re.findall(patron, html, re.I):
            if isinstance(match, tuple):
                match = match[0]

            if not match:
                continue

            if match.startswith("/"):
                match = urljoin(base_url, match)

            if match.startswith(("http://", "https://")):
                encontrados.add(match)

    return sorted(encontrados)



def analizar_catalogo_magento(session, base_url, html):
    """
    Analiza una instalación Magento sin asumir que su REST API
    pública está habilitada.
    """

    soup = BeautifulSoup(html, "html.parser")

    resultados = {
        "cards": 0,
        "productos": [],
        "imagenes": 0,
        "precios": 0,
        "urls": 0,
        "ids": 0,
        "paginas": [],
    }

    # Buscar estructuras típicas de Magento.
    selectores = [
        ".product-item",
        ".item.product.product-item",
        ".product-item-info",
        ".product-item-details",
        "[data-product-id]",
        "[data-productid]",
        "[data-product-id]",
    ]

    cards = []

    for selector in selectores:
        encontrados = soup.select(selector)

        if len(encontrados) > len(cards):
            cards = encontrados

    resultados["cards"] = len(cards)

    for card in cards:

        nombre = None
        precio = None
        imagen = None
        url = None
        product_id = None

        # Nombre
        for selector in (
            ".product-item-link",
            ".product.name a",
            ".product-item-name a",
            "[data-product-name]",
        ):
            nodo = card.select_one(selector)

            if nodo:
                nombre = (
                    nodo.get("data-product-name")
                    or nodo.get_text(" ", strip=True)
                )

                if nombre:
                    break

        # URL
        nodo = card.select_one(
            "a.product-item-link, "
            ".product.name a, "
            ".product-item-name a"
        )

        if nodo and nodo.get("href"):
            url = urljoin(
                base_url,
                nodo["href"],
            )

        # Imagen
        imagen_node = card.select_one(
            "img.product-image-photo, "
            ".product-image-container img, "
            "img"
        )

        if imagen_node:

            imagen = (
                imagen_node.get("data-src")
                or imagen_node.get("data-lazy-src")
                or imagen_node.get("src")
            )

            if imagen:
                imagen = urljoin(
                    base_url,
                    imagen,
                )

        # Precio
        precio_node = card.select_one(
            ".price, "
            ".price-wrapper, "
            "[data-price-amount]"
        )

        if precio_node:

            precio = (
                precio_node.get("data-price-amount")
                or precio_node.get_text(
                    " ",
                    strip=True,
                )
            )

        # ID
        product_id = (
            card.get("data-product-id")
            or card.get("data-productid")
        )

        if not product_id and url:
            match = re.search(
                r"[?&](?:id|product_id)=(\d+)",
                url,
                re.I,
            )

            if match:
                product_id = match.group(1)

        if nombre:
            resultados["productos"].append(
                {
                    "nombre": nombre,
                    "precio": precio,
                    "imagen": imagen,
                    "url": url,
                    "id": product_id,
                }
            )

            if precio:
                resultados["precios"] += 1

            if imagen:
                resultados["imagenes"] += 1

            if url:
                resultados["urls"] += 1

            if product_id:
                resultados["ids"] += 1

    # Detectar paginación.
    for a in soup.find_all("a", href=True):

        texto = a.get_text(
            " ",
            strip=True,
        ).lower()

        href = a["href"].lower()

        if (
            texto in {
                "next",
                "siguiente",
                "next page",
                "página siguiente",
            }
            or "p=" in href
            or "page=" in href
            or "product_list_limit" in href
        ):
            resultados["paginas"].append(
                urljoin(
                    base_url,
                    a["href"],
                )
            )

    resultados["paginas"] = list(
        dict.fromkeys(
            resultados["paginas"]
        )
    )

    return resultados



def analizar_bloques_genericos(html, base_url):
    """
    Busca automáticamente estructuras repetidas de productos.

    No depende de nombres concretos de plataforma.
    Busca bloques que combinen:
        - enlace
        - texto
        - precio
        - imagen
    """

    soup = BeautifulSoup(html, "html.parser")

    candidatos = []

    # Elementos que suelen representar una tarjeta/producto.
    elementos = soup.find_all(
        [
            "article",
            "li",
            "div",
        ]
    )

    for elemento in elementos:

        texto = elemento.get_text(
            " ",
            strip=True,
        )

        if len(texto) < 15 or len(texto) > 2500:
            continue

        # Precio argentino.
        tiene_precio = bool(
            re.search(
                r"\$\s*[\d.]+(?:,\d+)?",
                texto,
            )
        )

        if not tiene_precio:
            continue

        enlaces = elemento.find_all(
            "a",
            href=True,
        )

        imagenes = elemento.find_all(
            "img"
        )

        if not enlaces or not imagenes:
            continue

        # Evitar tomar contenedores gigantes.
        if len(elemento.find_all(["article", "li", "div"])) > 80:
            continue

        candidatos.append(elemento)

    # Eliminar candidatos contenidos dentro de otros candidatos.
    finales = []

    for candidato in candidatos:

        contenido = False

        for otro in candidatos:

            if candidato is otro:
                continue

            if otro in candidato.parents:
                contenido = True
                break

        if not contenido:
            finales.append(candidato)

    productos = []

    for card in finales:

        texto = card.get_text(
            " ",
            strip=True,
        )

        precio_match = re.search(
            r"\$\s*[\d.]+(?:,\d+)?",
            texto,
        )

        precio = (
            precio_match.group(0)
            if precio_match
            else None
        )

        enlace = card.find(
            "a",
            href=True,
        )

        imagen = card.find("img")

        if not enlace:
            continue

        href = urljoin(
            base_url,
            enlace.get("href"),
        )

        nombre = None

        # Priorizar atributos habituales.
        for atributo in (
            "title",
            "aria-label",
            "data-name",
            "data-product-name",
        ):
            valor = enlace.get(atributo)

            if valor and len(valor.strip()) > 3:
                nombre = valor.strip()
                break

        # Buscar texto en encabezados.
        if not nombre:
            heading = card.find(
                ["h1", "h2", "h3", "h4", "h5"]
            )

            if heading:
                nombre = heading.get_text(
                    " ",
                    strip=True,
                )

        # Último recurso: texto del enlace.
        if not nombre:
            texto_enlace = enlace.get_text(
                " ",
                strip=True,
            )

            if len(texto_enlace) > 3:
                nombre = texto_enlace

        if not nombre:
            continue

        imagen_url = None

        if imagen:

            imagen_url = (
                imagen.get("data-src")
                or imagen.get("data-lazy-src")
                or imagen.get("data-original")
                or imagen.get("src")
            )

            if imagen_url:
                imagen_url = urljoin(
                    base_url,
                    imagen_url,
                )

        candidatos_id = [
            card.get("data-product-id"),
            card.get("data-productid"),
            card.get("data-id"),
            enlace.get("data-product-id"),
            enlace.get("data-productid"),
        ]

        product_id = next(
            (
                x for x in candidatos_id
                if x
            ),
            None,
        )

        productos.append(
            {
                "nombre": nombre,
                "precio": precio,
                "imagen": imagen_url,
                "url": href,
                "id": product_id,
            }
        )

    return productos


def cargar_registro():
    CONFIG.mkdir(exist_ok=True)

    if not REGISTRO.exists():
        return {}

    try:
        return json.loads(
            REGISTRO.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def guardar_registro(registro):
    CONFIG.mkdir(exist_ok=True)

    REGISTRO.write_text(
        json.dumps(
            registro,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def compactar_registro(registro):
    """Reduce el registro histórico a fuentes útiles y portables."""
    limpio = {}
    for nombre, datos in registro.items():
        if not isinstance(datos, dict):
            continue
        item = dict(datos)
        item["catalog_urls"] = list(dict.fromkeys(
            [u for u in (item.get("catalog_urls") or []) if isinstance(u, str)]
        ))[:50]
        item["fuentes_prioritarias"] = list(dict.fromkeys(
            [u for u in (item.get("fuentes_prioritarias") or []) if isinstance(u, str)]
        ))[:30]
        item["endpoints"] = list(dict.fromkeys(
            [u for u in (item.get("endpoints") or []) if isinstance(u, str)]
        ))[:20]
        # La estructura detectada sirve como memoria, pero no debe almacenar
        # miles de URLs ni bloques HTML.
        item.pop("productos", None)
        item.pop("genericos", None)
        limpio[nombre] = item
    return limpio


def generar_extractor_base(nombre, url, info):
    archivo = EXTRACTORES / f'{nombre}.py'

    genericos = info.get('genericos') or []

    estructura = {
        'productos_iniciales': len(genericos),
        'con_imagen': sum(1 for x in genericos if x.get('imagen')),
        'con_precio': sum(1 for x in genericos if x.get('precio')),
        'con_url': sum(1 for x in genericos if x.get('url')),
    }

    config = {
        'tienda': nombre,
        'url': url,
        'plataformas': info.get('plataformas', []),
        'jsonld_productos': info.get('jsonld_productos', 0),
        'endpoints': info.get('endpoints', []),
        'catalog_urls': info.get('catalog_urls', []),
        'fuentes_prioritarias': info.get('fuentes_prioritarias', []),
        'estructura_detectada': estructura,
    }

    extractor = []
    extractor.append(chr(34) * 3 + 'Extractor generado automáticamente.' + chr(34) * 3)
    extractor.append('')
    extractor.append('from .auto_generico import extraer_desde_config')
    extractor.append('')
    extractor.append('CONFIG = ' + repr(config))
    extractor.append('')
    extractor.append('def extraer():')
    extractor.append('    return extraer_desde_config(CONFIG)')
    extractor.append('')

    archivo.write_text(
        chr(10).join(extractor),
        encoding='utf-8',
    )

    return archivo



def main():
    if len(sys.argv) < 2:
        print(
            "Uso: python agregar_tienda.py "
            "https://nueva-tienda.com"
        )
        raise SystemExit(1)

    url = normalizar_url(sys.argv[1])
    nombre = nombre_tienda(url)

    session = requests.Session()

    print(f"[AUTO] Analizando {url}")
    print()

    response = descargar(session, url)

    if not response:
        registrar_pendiente(url, "sin_respuesta")
        raise SystemExit(1)

    print(f"[AUTO] HTTP: {response.status_code}")
    print(f"[AUTO] HTML: {len(response.text)} bytes")

    if response.status_code != 200:
        registrar_pendiente(url, f"HTTP_{response.status_code}")
        print(
            f"[AUTO] La portada respondió "
            f"{response.status_code}. "
            f"No se genera extractor."
        )
        raise SystemExit(2)

    html = response.text

    plataformas = detectar(html, url)
    jsonld = extraer_jsonld(html)

    catalog_urls = descubrir_urls(
        html,
        url,
    )

    endpoints = descubrir_endpoints(
        html,
        url,
    )

    sitemap = descubrir_sitemap(
        session,
        url,
    )

    catalog_urls = seleccionar_catalogo(
        [(u, "") for u in catalog_urls]
        + [(u, "") for u in sitemap],
        limite=CATALOGO_MAX_URLS,
    )

    print()
    print("[AUTO] Plataformas:")

    for plataforma in plataformas:
        print(f"    - {plataforma}")

    print(
        f"[AUTO] JSON-LD Product: "
        f"{len(jsonld)}"
    )

    print(
        f"[AUTO] URLs catálogo/producto: "
        f"{len(catalog_urls)}"
    )

    print(
        f"[AUTO] Endpoints candidatos: "
        f"{len(endpoints)}"
    )

    info = {
        "plataformas": plataformas,
        "jsonld_productos": len(jsonld),
        "catalog_urls": catalog_urls,
        "endpoints": endpoints,
        "fuentes_prioritarias": catalog_urls[:50],
    }

    # Analizador Magento.
    if "magento" in plataformas:

        print()
        print(
            "[AUTO/MAGENTO] "
            "Analizando catálogo HTML..."
        )

        magento = analizar_catalogo_magento(
            session,
            url,
            html,
        )

        info["magento"] = magento

        print(
            f"[AUTO/MAGENTO] Tarjetas: "
            f"{magento['cards']}"
        )

        if not magento["productos"]:

            print(
                "[AUTO] Magento estándar "
                "no detectado. "
                "Ejecutando perfilado "
                "HTML genérico..."
            )

            genericos = analizar_bloques_genericos(
                html,
                url,
            )

            info["genericos"] = genericos

            print(
                f"[AUTO/GENERIC] "
                f"Bloques producto: "
                f"{len(genericos)}"
            )

            print(
                f"[AUTO/GENERIC] "
                f"Con imagen: "
                f"{sum(1 for x in genericos if x.get('imagen'))}"
            )

            print(
                f"[AUTO/GENERIC] "
                f"Con precio: "
                f"{sum(1 for x in genericos if x.get('precio'))}"
            )

            print(
                f"[AUTO/GENERIC] "
                f"Con URL: "
                f"{sum(1 for x in genericos if x.get('url'))}"
            )

        print(
            f"[AUTO/MAGENTO] "
            f"Productos detectados: "
            f"{len(magento['productos'])}"
        )

        print(
            f"[AUTO/MAGENTO] "
            f"Con precio: "
            f"{magento['precios']}"
        )

        print(
            f"[AUTO/MAGENTO] "
            f"Con imagen: "
            f"{magento['imagenes']}"
        )

        print(
            f"[AUTO/MAGENTO] "
            f"Con URL: "
            f"{magento['urls']}"
        )

        print(
            f"[AUTO/MAGENTO] "
            f"Con ID: "
            f"{magento['ids']}"
        )

        print(
            f"[AUTO/MAGENTO] "
            f"Paginación: "
            f"{len(magento['paginas'])}"
        )

    # Registrar automáticamente.
    registro = cargar_registro()

    genericos = info.get(
        "genericos",
        [],
    )

    registro[nombre] = {
        "url": url,
        "estado": "activo",
        "extractor": (
            f"extractores.{nombre}"
        ),
        "plataformas": plataformas,
        "catalog_urls": catalog_urls,
        "endpoints": endpoints,
        "jsonld_productos": len(jsonld),
        "estructura_detectada": {
            "productos_iniciales": len(
                genericos
            ),
            "con_imagen": sum(
                1
                for x in genericos
                if x.get("imagen")
            ),
            "con_precio": sum(
                1
                for x in genericos
                if x.get("precio")
            ),
            "con_url": sum(
                1
                for x in genericos
                if x.get("url")
            ),
        },
    }

    registro = compactar_registro(registro)
    guardar_registro(registro)

    archivo = generar_extractor_base(
        nombre,
        url,
        info,
    )

    print()
    print(
        f"[AUTO] Extractor generado: "
        f"{archivo}"
    )

    print(
        f"[AUTO] Registrada como: "
        f"{nombre}"
    )

    print()
    print(
        "[AUTO] Siguiente etapa: "
        "ejecutar automáticamente "
        "el extractor generado."
    )


if __name__ == "__main__":
    main()
