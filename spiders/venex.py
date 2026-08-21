import scrapy
import re
from urllib.parse import urljoin, urlparse


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    start_urls = [
        "https://www.venex.com.ar/",
        "https://www.venex.com.ar/sitemap.xml",
        "https://www.venex.com.ar/sitemap_index.xml",
        "https://www.venex.com.ar/robots.txt",
    ]
    custom_settings = {
        "DEPTH_LIMIT": 8,
        "CLOSESPIDER_PAGECOUNT": 5000,
        "CONCURRENT_REQUESTS": 32,
        "DOWNLOAD_TIMEOUT": 20,
    }

    CATEGORY_MARKERS = (
        "notebook", "microprocesador", "procesador", "placa", "video", "memoria",
        "ram", "almacenamiento", "disco", "ssd", "monitor", "periferico",
        "gabinete", "fuente", "motherboard", "mother", "componente", "pc",
        "computadora", "conectividad", "audio", "impresora", "telefon", "tablet",
        "gaming", "accesorio", "hogar", "oficina", "teclado", "mouse", "auricular",
        "joystick", "silla", "router", "webcam", "cable", "cooler",
    )

    BLOCKED_PATHS = (
        "/entrar", "/login", "/registr", "/contact", "/corporativo", "/envio",
        "/politica", "/terminos", "/carrito", "/checkout", "/landing", "/create_account",
    )

    def _misma_tienda(self, url):
        try:
            return urlparse(url).netloc.lower().lstrip("www.") == "venex.com.ar"
        except Exception:
            return False

    def _es_producto(self, href):
        if not href:
            return False
        path = urlparse(href).path.lower()
        # Las fichas históricas de Venex usan .html; también aceptamos rutas
        # explícitas de producto para no depender de una única convención.
        return path.endswith(".html") or any(
            x in path for x in ("/producto/", "/product/", "/productos/")
        )

    def _es_bloqueada(self, href):
        path = urlparse(href).path.lower()
        return any(x in path for x in self.BLOCKED_PATHS)

    def _es_lista(self, href, texto=""):
        if not href or not self._misma_tienda(href) or self._es_producto(href):
            return False
        if self._es_bloqueada(href):
            return False
        parsed = urlparse(href)
        path = parsed.path.lower()
        query = parsed.query.lower()
        valor = f"{path} {query} {texto or ''}".lower()
        if any(m in valor for m in self.CATEGORY_MARKERS):
            return True
        if any(k in query for k in ("page=", "pagina=", "vmm=", "man=", "opt=", "cat=", "sort=")):
            return True
        if path in {"", "/", "/index.php", "/index.html"}:
            return True
        return False

    def _extraer_producto(self, producto, response):
        enlace = (
            producto.css(".product-box-title a")
            or producto.css(".product-title a")
            or producto.css(".product-name a")
            or producto.css("h2 a")
            or producto.css("h3 a")
            or producto.css("a[href]")
        )
        if not enlace:
            return None

        nombre = enlace.xpath("string(.)").get()
        if not nombre:
            nombre = enlace.attrib.get("title")
        nombre = (nombre or "").strip()
        if len(nombre) < 3:
            return None

        url = enlace.attrib.get("href")
        if not url:
            return None
        url = response.urljoin(url)
        if not self._misma_tienda(url) or not self._es_producto(url):
            return None

        precio_nodos = producto.css(
            ".current-price, .product-box-price, .price, [itemprop=price], [data-price]"
        )
        precio_texto = precio_nodos.xpath("string(.)").get() if precio_nodos else ""
        precio_limpio = re.sub(r"[^\d]", "", precio_texto or "")
        if not precio_limpio:
            return None
        precio = int(precio_limpio)
        if precio < 100:
            return None

        precio_anterior_elemento = producto.css(".product-box-old-price, .old-price")
        precio_anterior = None
        if precio_anterior_elemento:
            texto = precio_anterior_elemento.xpath("string(.)").get()
            limpio = re.sub(r"[^\d]", "", texto or "")
            if limpio:
                precio_anterior = int(limpio)

        imagen_elemento = producto.css("img")
        imagen = None
        if imagen_elemento:
            imagen = (
                imagen_elemento.attrib.get("src")
                or imagen_elemento.attrib.get("data-src")
                or imagen_elemento.attrib.get("data-lazy-src")
                or imagen_elemento.attrib.get("data-original")
            )
            if imagen:
                imagen = response.urljoin(imagen)

        onclick = enlace.attrib.get("onclick", "")
        id_producto = None
        match = re.search(r'"id":"([^"]+)"', onclick)
        if match:
            id_producto = match.group(1)
        if not id_producto:
            sku = producto.css("[itemprop=sku]::attr(content), .sku::text").get()
            id_producto = (sku or url).strip()

        return {
            "tienda": "Venex",
            "nombre": nombre,
            "precio": precio,
            "precio_anterior": precio_anterior,
            "stock": 1,
            "imagen": imagen,
            "url": url,
            "id_producto": id_producto,
        }

    def _extraer_cards(self, response):
        selectores = (
            ".item-prod-show .product-box",
            ".product-box",
            ".product-item",
            ".product-card",
            "article.product",
            "[itemtype*='Product']",
        )
        mejor = []
        for selector in selectores:
            cards = response.css(selector)
            if len(cards) > len(mejor):
                mejor = cards
        vistos = set()
        for card in mejor:
            producto = self._extraer_producto(card, response)
            if not producto:
                continue
            if producto["url"] in vistos:
                continue
            vistos.add(producto["url"])
            yield producto

    def _parse_sitemap(self, response):
        texto = response.text
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", texto, re.I | re.S)
        for loc in locs:
            url = response.urljoin(loc.strip())
            if not self._misma_tienda(url):
                continue
            if url.lower().endswith(".xml"):
                yield scrapy.Request(url, callback=self._parse_sitemap)
            elif self._es_producto(url):
                yield scrapy.Request(url, callback=self.parse_producto)
            elif self._es_lista(url):
                yield scrapy.Request(url, callback=self.parse)

    def parse_producto(self, response):
        # Ficha individual: JSON-LD primero, después selectores de la página.
        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                import json
                data = json.loads(script)
            except Exception:
                continue
            objetos = data if isinstance(data, list) else [data]
            for obj in objetos:
                if not isinstance(obj, dict):
                    continue
                tipos = obj.get("@type")
                tipos = tipos if isinstance(tipos, list) else [tipos]
                if not any(str(x).lower() == "product" for x in tipos):
                    continue
                offers = obj.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                precio = offers.get("price") or obj.get("price")
                precio_limpio = re.sub(r"[^\d]", "", str(precio or ""))
                nombre = str(obj.get("name") or "").strip()
                if nombre and precio_limpio:
                    yield {
                        "tienda": "Venex",
                        "nombre": nombre,
                        "precio": int(precio_limpio),
                        "precio_anterior": None,
                        "stock": 0 if "outofstock" in str(offers.get("availability", "")).lower() else 1,
                        "imagen": response.urljoin(obj.get("image")) if isinstance(obj.get("image"), str) else None,
                        "url": response.url,
                        "id_producto": str(obj.get("sku") or response.url),
                    }
                    return

        # Fallback para fichas sin JSON-LD.
        nombre = response.css("h1::text, .product-title::text, .product-name::text").get()
        precio = response.css(
            ".current-price::text, .price::text, [itemprop=price]::attr(content), [itemprop=price]::text"
        ).get()
        precio_limpio = re.sub(r"[^\d]", "", precio or "")
        if nombre and precio_limpio:
            yield {
                "tienda": "Venex",
                "nombre": nombre.strip(),
                "precio": int(precio_limpio),
                "precio_anterior": None,
                "stock": 1,
                "imagen": response.css('meta[property="og:image"]::attr(content)').get(),
                "url": response.url,
                "id_producto": response.url,
            }

    def parse(self, response):
        content_type = response.headers.get(b"Content-Type", b"").decode("latin1", "ignore").lower()
        if response.url.lower().endswith(".xml") or "xml" in content_type:
            yield from self._parse_sitemap(response)
            return

        if response.url.lower().endswith("robots.txt"):
            for linea in response.text.splitlines():
                if linea.lower().startswith("sitemap:"):
                    url = linea.split(":", 1)[1].strip()
                    yield scrapy.Request(url, callback=self._parse_sitemap)
            return

        yield from self._extraer_cards(response)

        # Descubrir categorías, filtros y paginación sin depender de una lista
        # cerrada de URLs. Esto es lo que faltaba en la versión anterior.
        vistos = set()
        for enlace in response.css("a[href]"):
            href = enlace.attrib.get("href")
            url = response.urljoin(href) if href else None
            if not url or url in vistos or url == response.url:
                continue
            vistos.add(url)
            texto = enlace.xpath("string(.)").get() or enlace.attrib.get("title") or ""
            if self._es_producto(url):
                yield scrapy.Request(url, callback=self.parse_producto)
            elif self._es_lista(url, texto):
                yield response.follow(url, callback=self.parse)
