import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 2000,
    }

    BASE = "https://www.venex.com.ar"
    SEARCH = BASE + "/resultado-busqueda.htm"
    LIMIT = 96

    # Rutas de catálogo observadas en Venex. Son semillas de descubrimiento,
    # no filtros de producto; cada listado se recorre completo.
    CATEGORY_SEEDS = [
        "/notebooks/",
        "/microprocesadores/",
        "/placas-de-video/",
        "/memorias-ram/",
        "/componentes-de-pc/",
        "/monitores/",
        "/perifericos/",
        "/almacenamiento/",
        "/discos/",
        "/sillas-gamers/",
        "/pc-de-escritorio/",
        "/gaming/",
        "/conectividad/",
        "/audio/",
        "/impresion-y-scanners/",
        "/tablets/",
        "/camaras-ip/",
        "/relojes-smartwatch/",
        "/accesorios/",
    ]

    SEARCH_TERMS = [
        "notebook", "procesador", "placa", "memoria", "ram", "ssd", "monitor",
        "motherboard", "gabinete", "fuente", "cooler", "teclado", "mouse",
        "auricular", "joystick", "webcam", "microfono", "router", "wifi",
        "impresora", "tablet", "silla", "pc gamer", "consola", "playstation",
        "xbox", "nintendo", "celular", "smartwatch", "audio", "cable",
        "adaptador", "camara", "gaming", "accesorio",
    ]

    def start_requests(self):
        # 1) Semillas directas de categorías.
        for path in self.CATEGORY_SEEDS:
            yield scrapy.Request(self.BASE + path, callback=self.parse_listing, meta={"seed": path})

        # 2) Índice por búsqueda interna, útil para productos que no estén
        # correctamente vinculados desde categorías.
        for term in self.SEARCH_TERMS:
            yield scrapy.Request(
                self.search_url(term, 1),
                callback=self.parse_listing,
                meta={"search_term": term, "page": 1},
            )

        # 3) Vista amplia del buscador.
        yield scrapy.Request(
            self.search_url("y", 1),
            callback=self.parse_listing,
            meta={"search_term": "y", "page": 1, "broad": True},
        )

    def search_url(self, term, page):
        return f"{self.SEARCH}?{urlencode({'keywords': term, 'limit': self.LIMIT, 'page': page})}"

    @staticmethod
    def same_store(url):
        try:
            return urlparse(url).netloc.lower().lstrip("www.") == "venex.com.ar"
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
        number = int(digits)
        return number if number >= 100 else None

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
        raw_price = node.xpath("string(.)").get() if node else None
        price = self.price(raw_price)
        if not price:
            text = card.xpath("string(.)").get() or ""
            match = re.search(r"\$\s*[\d.]+(?:,\d+)?", text)
            price = self.price(match.group(0)) if match else None
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
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": old_price,
            "stock": 1,
            "imagen": self.image(card, response),
            "url": url,
            "id_producto": product_id,
        }

    def extract_products(self, response):
        selectors = (
            ".item-prod-show .product-box",
            ".product-box",
            ".product-item",
            ".product-card",
            "article.product",
            "[itemtype*='Product']",
        )
        best = []
        for selector in selectors:
            cards = response.css(selector)
            if len(cards) > len(best):
                best = cards

        seen = set()
        for card in best:
            product = self.extract_card(card, response)
            if not product or product["url"] in seen:
                continue
            seen.add(product["url"])
            yield product

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
                        raw_price = offers.get("price") if isinstance(offers, dict) else None
                        price = self.price(raw_price)
                        name = str(obj.get("name") or "").strip()
                        if name and price:
                            image = obj.get("image")
                            if isinstance(image, list):
                                image = image[0] if image else None
                            yield {
                                "tienda": "Venex",
                                "nombre": name,
                                "precio": price,
                                "precio_anterior": None,
                                "stock": 0 if "outofstock" in str((offers or {}).get("availability", "")).lower() else 1,
                                "imagen": response.urljoin(image) if isinstance(image, str) else None,
                                "url": response.url,
                                "id_producto": str(obj.get("sku") or response.url),
                            }
                    for value in obj.values():
                        if isinstance(value, (dict, list)):
                            stack.append(value)
                elif isinstance(obj, list):
                    stack.extend(obj)

    def current_page(self, response):
        for key in ("page", "pagina"):
            values = parse_qs(urlparse(response.url).query).get(key)
            if values:
                try:
                    return max(1, int(values[0]))
                except ValueError:
                    pass
        return 1

    def pagination_total(self, response):
        # Look for explicit page counts first.
        vals = []
        for selector in (
            "[data-total-pages]::attr(data-total-pages)",
            "[data-pages]::attr(data-pages)",
            "[data-totalpages]::attr(data-totalpages)",
        ):
            value = response.css(selector).get()
            if value and value.isdigit():
                vals.append(int(value))

        # Numeric pagination anchors.
        for text in response.css(".pagination a::text, .pagination span::text, .pager a::text").getall():
            text = text.strip()
            if text.isdigit():
                vals.append(int(text))

        # Page links in hrefs.
        for href in response.css("a[href]::attr(href)").getall():
            if "page=" not in href.lower() and "pagina=" not in href.lower():
                continue
            qs = parse_qs(urlparse(response.urljoin(href)).query)
            for key in ("page", "pagina"):
                if key in qs:
                    try:
                        vals.append(int(qs[key][0]))
                    except ValueError:
                        pass

        return max(vals) if vals else None

    def replace_page(self, response, page):
        parsed = urlparse(response.url)
        qs = dict(parse_qs(parsed.query, keep_blank_values=True))
        qs = {k: v[-1] if isinstance(v, list) and v else v for k, v in qs.items()}
        qs["page"] = str(page)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs), parsed.fragment))

    def follow_pages(self, response):
        current = self.current_page(response)
        total = self.pagination_total(response)

        # Prefer explicit next link, but still synthesize page URLs when possible.
        seen = set()
        for href in response.css('a[rel="next"]::attr(href), a.next::attr(href), .pagination .next::attr(href)').getall():
            url = response.urljoin(href)
            if self.same_store(url) and url not in seen:
                seen.add(url)
                yield scrapy.Request(url, callback=self.parse_listing, meta={**response.meta, "page": current + 1})

        if total and 1 < total <= 200:
            for page in range(current + 1, total + 1):
                url = self.replace_page(response, page)
                if url not in seen:
                    seen.add(url)
                    yield scrapy.Request(url, callback=self.parse_listing, meta={**response.meta, "page": page})
            return

        # When total pages is hidden, continue until a page becomes empty. This
        # only occurs for pages generated from a listing/search URL.
        has_products = bool(response.css(".item-prod-show .product-box, .product-box, .product-item, .product-card"))
        if has_products and current < 200:
            page = current + 1
            url = self.replace_page(response, page)
            if url not in seen:
                yield scrapy.Request(url, callback=self.parse_listing, meta={**response.meta, "page": page})

    def discover_categories(self, response):
        seen = set()
        for a in response.css("a[href]"):
            href = a.attrib.get("href")
            if not href:
                continue
            url = response.urljoin(href)
            if not self.same_store(url) or url in seen or self.blocked(url) or self.is_product(url):
                continue
            seen.add(url)
            text = (a.xpath("string(.)").get() or "").strip().lower()
            path = urlparse(url).path.lower()
            query = urlparse(url).query.lower()
            looks = (
                any(x in path for x in (
                    "/notebook", "/microproces", "/placa", "/memoria", "/monitor", "/disco",
                    "/almacen", "/component", "/perifer", "/pc-de-escritorio", "/gaming",
                    "/audio", "/impres", "/tablet", "/silla", "/conect", "/acces", "/camara",
                    "/reloj",
                ))
                or any(x in text for x in (
                    "notebook", "procesador", "memoria", "placa", "monitor", "almacenamiento",
                    "periferico", "gabinete", "fuente", "gaming", "audio", "tablet",
                ))
                or any(x in query for x in ("page=", "pagina=", "limit=", "vmm=", "man=", "opt=", "cat="))
            )
            if looks:
                yield scrapy.Request(url, callback=self.parse_listing, meta={"category_discovered": True})

    def parse_listing(self, response):
        seen_urls = set()
        count = 0
        for product in self.extract_products(response):
            if product["url"] in seen_urls:
                continue
            seen_urls.add(product["url"])
            count += 1
            yield product

        # JSON-LD as a fallback/additional source, not as the primary index.
        if count == 0:
            for product in self.jsonld_products(response):
                yield product

        # Pagination is mandatory for list/search pages.
        yield from self.follow_pages(response)

        # Category discovery only from category/listing pages; prevents a crawl
        # explosion from product-detail links.
        if response.meta.get("discover_categories", True):
            yield from self.discover_categories(response)

    def parse(self, response):
        yield from self.parse_listing(response)
