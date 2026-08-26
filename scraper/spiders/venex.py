import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]

    BASE = "https://www.venex.com.ar"
    SEARCH = BASE + "/resultado-busqueda.htm"
    LIMIT = 96

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 2500,
    }

    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/placas-de-video/", "/memorias-ram/",
        "/componentes-de-pc/", "/monitores/", "/perifericos/", "/almacenamiento/",
        "/discos/", "/sillas-gamers/", "/pc-de-escritorio/", "/gaming/",
        "/conectividad/", "/audio/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/accesorios/", "/impresoras/",
        "/telefonia/", "/hogar-y-oficina/", "/fuentes/", "/gabinetes/", "/motherboards/",
    ]

    SEARCH_TERMS = [
        "notebook", "procesador", "placa", "video", "memoria", "ram", "ssd", "disco",
        "monitor", "motherboard", "gabinete", "fuente", "cooler", "teclado", "mouse",
        "auricular", "joystick", "webcam", "microfono", "router", "wifi", "impresora",
        "tablet", "silla", "pc gamer", "consola", "playstation", "xbox", "nintendo",
        "celular", "smartwatch", "audio", "cable", "adaptador", "camara", "gaming",
        "accesorio", "kingston", "asus", "msi", "lenovo", "hp", "intel", "amd", "nvidia",
    ]

    async def start(self):
        """Scrapy 2.18 removed start_requests(); initial requests must be yielded here."""
        seen = set()
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url not in seen:
                seen.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "category", "page": 1})

        for term in self.SEARCH_TERMS:
            url = self.search_url(term, 1)
            if url not in seen:
                seen.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "search", "term": term, "page": 1})

        url = self.search_url("y", 1)
        if url not in seen:
            yield scrapy.Request(url, callback=self.parse_listing,
                                 meta={"kind": "search", "term": "y", "page": 1, "broad": True})

    def search_url(self, term, page):
        return f"{self.SEARCH}?{urlencode({'keywords': term, 'limit': self.LIMIT, 'page': page})}"

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: (v[-1] if isinstance(v, list) else v) for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar", p.path or "/", p.params, urlencode(q), p.fragment))

    @staticmethod
    def same_store(url):
        try:
            return urlparse(url).netloc.lower().removeprefix("www.") == "venex.com.ar"
        except Exception:
            return False

    @staticmethod
    def is_product(url):
        path = urlparse(url).path.lower()
        return path.endswith(".html") or any(x in path for x in ("/producto/", "/product/", "/productos/"))

    @staticmethod
    def blocked(url):
        path = urlparse(url).path.lower()
        return any(x in path for x in ("/login", "/entrar", "/carrito", "/checkout", "/contact", "/terminos", "/politica"))

    @staticmethod
    def price(value):
        digits = re.sub(r"[^\d]", "", str(value or ""))
        if not digits:
            return None
        n = int(digits)
        return n if n >= 100 else None

    def extract_card(self, card, response):
        link = (card.css(".product-box-title a") or card.css(".product-title a") or
                card.css(".product-name a") or card.css("h2 a") or card.css("h3 a") or
                card.css("a[href]"))
        if not link:
            return None
        href = link.attrib.get("href")
        if not href:
            return None
        url = response.urljoin(href)
        if not self.same_store(url) or not self.is_product(url) or self.blocked(url):
            return None
        name = (link.xpath("string(.)").get() or link.attrib.get("title") or "").strip()
        if len(name) < 3:
            return None

        nodes = card.css(".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price")
        raw = nodes.xpath("string(.)").get() if nodes else None
        price = self.price(raw)
        if not price:
            m = re.search(r"\$\s*[\d.]+(?:,\d+)?", card.xpath("string(.)").get() or "")
            price = self.price(m.group(0)) if m else None
        if not price:
            return None

        old = card.css(".product-box-old-price, .old-price")
        old_price = self.price(old.xpath("string(.)").get()) if old else None

        img = card.css("img")[:1]
        image = None
        if img:
            src = (img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or
                   img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or
                   img.attrib.get("data-src") or img.attrib.get("src"))
            if src:
                image = response.urljoin(src)

        onclick = link.attrib.get("onclick", "")
        m = re.search(r'"id":"([^"]+)"', onclick)
        product_id = m.group(1) if m else card.css("[itemprop=sku]::attr(content), .sku::text").get()
        return {"tienda": "Venex", "nombre": name, "precio": price, "precio_anterior": old_price,
                "stock": 1, "imagen": image, "url": url, "id_producto": (product_id or url).strip()}

    def extract_products(self, response):
        selectors = (".item-prod-show .product-box", ".product-box", ".product-item", ".product-card", "article.product", "[itemtype*='Product']")
        best = []
        for selector in selectors:
            cards = response.css(selector)
            if len(cards) > len(best):
                best = cards
        seen = set()
        for card in best:
            p = self.extract_card(card, response)
            if p and p["url"] not in seen:
                seen.add(p["url"])
                yield p

    def jsonld_products(self, response):
        for raw in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(raw)
            except Exception:
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                obj = stack.pop()
                if isinstance(obj, dict):
                    typ = obj.get("@type")
                    types = typ if isinstance(typ, list) else [typ]
                    if any(str(x).lower() == "product" for x in types):
                        offers = obj.get("offers") or {}
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        price = self.price(offers.get("price") if isinstance(offers, dict) else None)
                        name = str(obj.get("name") or "").strip()
                        if name and price:
                            image = obj.get("image")
                            if isinstance(image, list):
                                image = image[0] if image else None
                            yield {"tienda": "Venex", "nombre": name, "precio": price,
                                   "precio_anterior": None, "stock": 1,
                                   "imagen": response.urljoin(image) if isinstance(image, str) else None,
                                   "url": response.url, "id_producto": str(obj.get("sku") or response.url)}
                    for value in obj.values():
                        if isinstance(value, (dict, list)):
                            stack.append(value)
                elif isinstance(obj, list):
                    stack.extend(obj)

    def current_page(self, response):
        vals = parse_qs(urlparse(response.url).query).get("page") or parse_qs(urlparse(response.url).query).get("pagina")
        try:
            return max(1, int(vals[0])) if vals else int(response.meta.get("page", 1))
        except (ValueError, TypeError):
            return 1

    def has_next(self, response, count):
        if response.css('a[rel="next"], a.next, .pagination .next'):
            return True
        current = self.current_page(response)
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            q = parse_qs(urlparse(url).query)
            vals = q.get("page") or q.get("pagina")
            if vals:
                try:
                    if int(vals[0]) > current:
                        return True
                except ValueError:
                    pass
        return count >= self.LIMIT

    def discover_categories(self, response):
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            if not self.same_store(url) or self.is_product(url) or self.blocked(url):
                continue
            path = urlparse(url).path.lower()
            if any(x in path for x in ("/notebook", "/microproces", "/placa", "/memoria", "/monitor", "/disco", "/almacen", "/component", "/perifer", "/pc-de-escritorio", "/gaming", "/audio", "/impres", "/tablet", "/silla", "/conect", "/acces", "/camara", "/reloj")):
                yield self.listing_url(url, 1)

    def parse_listing(self, response):
        products = list(self.extract_products(response))
        if not products:
            products = list(self.jsonld_products(response))
        for product in products:
            yield product

        current = self.current_page(response)
        if current < 200 and self.has_next(response, len(products)):
            yield scrapy.Request(self.listing_url(response.url, current + 1),
                                 callback=self.parse_listing,
                                 meta={**response.meta, "page": current + 1})

        if current == 1 and not self.is_product(response.url) and response.meta.get("discover", True):
            for url in self.discover_categories(response):
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "category", "page": 1, "discover": False})

    def parse(self, response):
        yield from self.parse_listing(response)
