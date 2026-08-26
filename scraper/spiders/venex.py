import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 2500,
    }

    BASE = "https://www.venex.com.ar"
    SEARCH = BASE + "/resultado-busqueda.htm"
    LIMIT = 96

    # Direct category seeds plus generic search seeds. The goal is catalog
    # discovery, not filtering the final product set.
    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/placas-de-video/", "/memorias-ram/",
        "/componentes-de-pc/", "/monitores/", "/perifericos/", "/almacenamiento/",
        "/discos/", "/sillas-gamers/", "/pc-de-escritorio/", "/gaming/", "/conectividad/",
        "/audio/", "/impresion-y-scanners/", "/tablets/", "/camaras-ip/",
        "/relojes-smartwatch/", "/accesorios/", "/impresoras/", "/telefonia/",
        "/hogar-y-oficina/", "/fuentes/", "/gabinetes/", "/motherboards/",
    ]
    SEARCH_TERMS = [
        "notebook", "procesador", "placa", "video", "memoria", "ram", "ssd", "disco",
        "monitor", "motherboard", "gabinete", "fuente", "cooler", "teclado", "mouse",
        "auricular", "joystick", "webcam", "microfono", "router", "wifi", "impresora",
        "tablet", "silla", "pc gamer", "consola", "playstation", "xbox", "nintendo",
        "celular", "smartwatch", "audio", "cable", "adaptador", "camara", "gaming",
        "accesorio", "kingston", "asus", "msi", "lenovo", "hp", "intel", "amd", "nvidia",
    ]

    def start_requests(self):
        # Start with the real listing endpoints. Do not depend on the homepage.
        for path in self.CATEGORY_SEEDS:
            yield scrapy.Request(self._listing_url(self.BASE + path, 1), callback=self.parse_listing, meta={"seed": path, "page": 1})

        for term in self.SEARCH_TERMS:
            yield scrapy.Request(self._search_url(term, 1), callback=self.parse_listing, meta={"search_term": term, "page": 1})

        # One broad result view as a second index.
        yield scrapy.Request(self._search_url("y", 1), callback=self.parse_listing, meta={"search_term": "y", "page": 1, "broad": True})

    def _search_url(self, term, page):
        return f"{self.SEARCH}?{urlencode({'keywords': term, 'limit': self.LIMIT, 'page': page})}"

    def _listing_url(self, base, page):
        parsed = urlparse(base)
        qs = dict(parse_qs(parsed.query, keep_blank_values=True))
        qs = {k: (v[-1] if isinstance(v, list) and v else v) for k, v in qs.items()}
        qs["limit"] = str(self.LIMIT)
        qs["page"] = str(page)
        return urlunparse((parsed.scheme or "https", parsed.netloc or urlparse(self.BASE).netloc, parsed.path or "/", parsed.params, urlencode(qs), parsed.fragment))

    @staticmethod
    def same_store(url):
        try:
            return urlparse(url).netloc.lower().lstrip("www.") == "venex.com.ar"
        except Exception:
            return False

    @staticmethod
    def is_product(url):
        if not url:
            return False
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

    def image(self, card, response):
        img = card.css("img")[:1]
        if not img:
            return None
        src = (
            img.attrib.get("data-zoom-image")
            or img.attrib.get("data-large-image")
            or img.attrib.get("data-original")
            or img.attrib.get("data-lazy-src")
            or img.attrib.get("data-src")
            or img.attrib.get("src")
        )
        return response.urljoin(src) if src else None

    def extract_card(self, card, response):
        link = (
            card.css(".product-box-title a")
            or card.css(".product-title a")
            or card.css(".product-name a")
            or card.css("h2 a")
            or card.css("h3 a")
            or card.css("a[href]")
        )
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
        node = card.css(".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price")
        raw = node.xpath("string(.)").get() if node else None
        price = self.price(raw)
        if not price:
            text = card.xpath("string(.)").get() or ""
            m = re.search(r"\$\s*[\d.]+(?:,\d+)?", text)
            price = self.price(m.group(0)) if m else None
        if not price:
            return None
        old = card.css(".product-box-old-price, .old-price")
        old_price = self.price(old.xpath("string(.)").get()) if old else None
        onclick = link.attrib.get("onclick", "")
        match = re.search(r'"id":"([^"]+)"', onclick)
        product_id = match.group(1) if match else None
        if not product_id:
            sku = card.css("[itemprop=sku]::attr(content), .sku::text").get()
            product_id = (sku or url).strip()
        return {
            "tienda": "Venex", "nombre": name, "precio": price, "precio_anterior": old_price,
            "stock": 1, "imagen": self.image(card, response), "url": url, "id_producto": product_id,
        }

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
        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
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
                            yield {
                                "tienda": "Venex", "nombre": name, "precio": price, "precio_anterior": None,
                                "stock": 0 if "outofstock" in str((offers or {}).get("availability", "")).lower() else 1,
                                "imagen": response.urljoin(image) if isinstance(image, str) else None,
                                "url": response.url, "id_producto": str(obj.get("sku") or response.url),
                            }
                    for value in obj.values():
                        if isinstance(value, (dict, list)):
                            stack.append(value)
                elif isinstance(obj, list):
                    stack.extend(obj)

    def current_page(self, response):
        for key in ("page", "pagina"):
            vals = parse_qs(urlparse(response.url).query).get(key)
            if vals:
                try:
                    return max(1, int(vals[0]))
                except ValueError:
                    pass
        return int(response.meta.get("page", 1) or 1)

    def has_more_signal(self, response, extracted_count):
        # Strong signal: explicit next link.
        if response.css('a[rel="next"], a.next, .pagination .next'):
            return True
        # Strong signal: a numeric page > current page exists.
        current = self.current_page(response)
        for href in response.css("a[href]::attr(href)").getall():
            absolute = response.urljoin(href)
            qs = parse_qs(urlparse(absolute).query)
            vals = qs.get("page") or qs.get("pagina")
            if not vals:
                continue
            try:
                if int(vals[0]) > current:
                    return True
            except ValueError:
                pass
        # Result pages capped at LIMIT very likely have another page.
        return extracted_count >= self.LIMIT

    def next_listing(self, response, page):
        # Preserve search/category parameters and set page+limit explicitly.
        return self._listing_url(response.url, page)

    def discover_catalog_links(self, response):
        seen = set()
        for a in response.css("a[href]"):
            href = a.attrib.get("href")
            if not href:
                continue
            url = response.urljoin(href)
            if not self.same_store(url) or url in seen or self.blocked(url) or self.is_product(url):
                continue
            parsed = urlparse(url)
            path = parsed.path.lower()
            text = (a.xpath("string(.)").get() or "").strip().lower()
            query = parsed.query.lower()
            looks = (
                any(x in path for x in ("/notebook", "/microproces", "/placa", "/memoria", "/monitor", "/disco", "/almacen", "/component", "/perifer", "/pc-de-escritorio", "/gaming", "/audio", "/impres", "/tablet", "/silla", "/conect", "/acces", "/camara", "/reloj"))
                or any(x in text for x in ("notebook", "procesador", "memoria", "placa", "monitor", "almacenamiento", "periferico", "gabinete", "fuente", "gaming"))
                or any(k in query for k in ("page=", "pagina=", "limit=", "vmm=", "man=", "opt=", "cat="))
            )
            if looks:
                seen.add(url)
                yield url

    def parse_listing(self, response):
        products = list(self.extract_products(response))
        if not products:
            products = list(self.jsonld_products(response))

        # Emit products from this page.
        for p in products:
            yield p

        current = self.current_page(response)
        # Never rely on hidden total pages. Continue sequentially while there
        # are strong signals, and stop on the first empty page.
        if current < 200 and self.has_more_signal(response, len(products)):
            next_url = self.next_listing(response, current + 1)
            yield scrapy.Request(next_url, callback=self.parse_listing, meta={**response.meta, "page": current + 1})

        # Discover other category URLs from pages that are not product details.
        if not self.is_product(response.url) and current == 1:
            for url in self.discover_catalog_links(response):
                yield scrapy.Request(self._listing_url(url, 1), callback=self.parse_listing, meta={"category_discovered": True, "page": 1})

    def parse(self, response):
        yield from self.parse_listing(response)
