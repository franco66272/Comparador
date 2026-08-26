import json
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]

    custom_settings = {
        "DEPTH_LIMIT": 20,
        "CLOSESPIDER_PAGECOUNT": 5000,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 12,
        "DOWNLOAD_DELAY": 0.1,
        "DOWNLOAD_TIMEOUT": 20,
        "ROBOTSTXT_OBEY": True,
    }

    SEARCH_URL = "https://www.venex.com.ar/resultado-busqueda.htm"
    PAGE_SIZE = 96

    # Explicit category seeds. These are real catalog sections, not keyword
    # guesses. The spider expands pagination from each section.
    CATEGORY_SEEDS = [
        "https://www.venex.com.ar/notebooks?limit=96&page=1",
        "https://www.venex.com.ar/procesadores?limit=96&page=1",
        "https://www.venex.com.ar/microprocesadores?limit=96&page=1",
        "https://www.venex.com.ar/placas-de-video?limit=96&page=1",
        "https://www.venex.com.ar/memorias-ram?limit=96&page=1",
        "https://www.venex.com.ar/componentes-de-pc?limit=96&page=1",
        "https://www.venex.com.ar/componentes-de-pc/discos-solidos-ssd?limit=96&page=1",
        "https://www.venex.com.ar/monitores?limit=96&page=1",
        "https://www.venex.com.ar/perifericos?limit=96&page=1",
        "https://www.venex.com.ar/gabinetes?limit=96&page=1",
        "https://www.venex.com.ar/fuentes?limit=96&page=1",
        "https://www.venex.com.ar/motherboards?limit=96&page=1",
        "https://www.venex.com.ar/pc-de-escritorio?limit=96&page=1",
        "https://www.venex.com.ar/gaming?limit=96&page=1",
        "https://www.venex.com.ar/audio?limit=96&page=1",
        "https://www.venex.com.ar/impresion-y-scanners?limit=96&page=1",
        "https://www.venex.com.ar/tablets?limit=96&page=1",
        "https://www.venex.com.ar/sillas-gamers?limit=96&page=1",
        "https://www.venex.com.ar/conectividad?limit=96&page=1",
        "https://www.venex.com.ar/accesorios?limit=96&page=1",
        "https://www.venex.com.ar/camaras-ip?limit=96&page=1",
    ]

    # Search seeds are only a secondary discovery layer for products/categories
    # that are not exposed through the top-level category URLs.
    SEARCH_SEEDS = [
        "ryzen", "intel", "rtx", "radeon", "ssd", "nvme", "ddr4", "ddr5",
        "wifi", "router", "joystick", "teclado", "mouse", "auricular",
        "webcam", "microfono", "impresora", "tablet", "smartwatch", "gaming",
    ]

    BLOCKED_PATHS = (
        "/entrar", "/login", "/registr", "/contact", "/corporativo", "/envio",
        "/politica", "/terminos", "/carrito", "/checkout", "/landing", "/create_account",
    )

    def start_requests(self):
        for url in self.CATEGORY_SEEDS:
            yield scrapy.Request(url, callback=self.parse, meta={"listing_root": url, "listing_page": 1})
        for term in self.SEARCH_SEEDS:
            yield scrapy.Request(
                self._search_url(term, 1),
                callback=self.parse,
                dont_filter=True,
                meta={"search_seed": term, "search_page": 1},
            )

    def _search_url(self, term, page=1):
        return f"{self.SEARCH_URL}?{urlencode({'keywords': term, 'limit': self.PAGE_SIZE, 'page': page})}"

    def _same_store(self, url):
        try:
            return urlparse(url).netloc.lower().lstrip("www.") == "venex.com.ar"
        except Exception:
            return False

    def _is_blocked(self, url):
        return any(x in urlparse(url).path.lower() for x in self.BLOCKED_PATHS)

    def _is_product(self, url):
        if not url:
            return False
        path = urlparse(url).path.lower()
        return path.endswith(".html") or any(x in path for x in ("/producto/", "/product/", "/productos/"))

    def _clean_int(self, value):
        txt = re.sub(r"[^\d]", "", str(value or ""))
        if not txt:
            return None
        number = int(txt)
        return number if number >= 100 else None

    def _image(self, card, response):
        img = card.css("img")
        if not img:
            return None
        value = (
            img.attrib.get("data-zoom-image")
            or img.attrib.get("data-large-image")
            or img.attrib.get("data-original")
            or img.attrib.get("data-lazy-src")
            or img.attrib.get("data-src")
            or img.attrib.get("src")
        )
        return response.urljoin(value) if value else None

    def _extract_card(self, card, response):
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
        if not self._same_store(url) or not self._is_product(url) or self._is_blocked(url):
            return None

        name = (link.xpath("string(.)").get() or link.attrib.get("title") or "").strip()
        if len(name) < 3:
            return None

        price_nodes = card.css(".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price")
        price = self._clean_int(price_nodes.xpath("string(.)").get() if price_nodes else None)
        if not price:
            text = card.xpath("string(.)").get() or ""
            match = re.search(r"\$\s*[\d.]+(?:,\d+)?", text)
            price = self._clean_int(match.group(0) if match else None)
        if not price:
            return None

        old_nodes = card.css(".product-box-old-price, .old-price")
        old_price = self._clean_int(old_nodes.xpath("string(.)").get() if old_nodes else None)
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
            "imagen": self._image(card, response),
            "url": url,
            "id_producto": product_id,
        }

    def _extract_cards(self, response):
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
        for card in best:
            product = self._extract_card(card, response)
            if product:
                yield product

    def _extract_jsonld_products(self, response):
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
                        price = self._clean_int(offers.get("price") if isinstance(offers, dict) else None)
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

    def _current_page(self, response):
        qs = parse_qs(urlparse(response.url).query)
        for key in ("page", "pagina"):
            if qs.get(key):
                try:
                    return max(1, int(qs[key][0]))
                except Exception:
                    pass
        return 1

    def _page_url(self, response_url, page):
        parsed = urlparse(response_url)
        qs = dict((k, v[-1]) for k, v in parse_qs(parsed.query).items())
        qs["limit"] = str(self.PAGE_SIZE)
        qs["page"] = str(page)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs), parsed.fragment))

    def _pagination_pages(self, response):
        pages = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            if not self._same_store(url):
                continue
            qs = parse_qs(urlparse(url).query)
            for key in ("page", "pagina"):
                for value in qs.get(key, []):
                    if str(value).isdigit():
                        pages.add(int(value))
        for text in response.css(".pagination a::text, .pager a::text, .pagination li::text").getall():
            text = str(text).strip()
            if text.isdigit():
                pages.add(int(text))
        return pages

    def _follow_pagination(self, response, yielded_count):
        current = self._current_page(response)
        pages = self._pagination_pages(response)
        if pages:
            target = max(pages)
            for page in range(current + 1, min(target, current + 99) + 1):
                yield scrapy.Request(
                    self._page_url(response.url, page),
                    callback=self.parse,
                    meta={
                        "search_seed": response.meta.get("search_seed"),
                        "listing_root": response.meta.get("listing_root") or response.url,
                        "listing_page": page,
                    },
                )
        elif yielded_count >= 40:
            # Many Venex listings do not expose a clean total page count. If a
            # full-ish page is returned, continue sequentially until an empty
            # page is encountered. The spider close/page limits stop runaway loops.
            next_page = current + 1
            yield scrapy.Request(
                self._page_url(response.url, next_page),
                callback=self.parse,
                meta={
                    "search_seed": response.meta.get("search_seed"),
                    "listing_root": response.meta.get("listing_root") or response.url,
                    "listing_page": next_page,
                },
            )

    def parse(self, response):
        yielded = 0
        seen = set()
        for product in self._extract_cards(response):
            if product["url"] in seen:
                continue
            seen.add(product["url"])
            yielded += 1
            yield product

        if yielded == 0:
            for product in self._extract_jsonld_products(response):
                yield product

        yield from self._follow_pagination(response, yielded)

        # Discover real category/listing links from category/search pages. Do
        # this only for the first page of each listing to limit redundant work.
        current = self._current_page(response)
        if current != 1:
            return
        for a in response.css("a[href]"):
            href = a.attrib.get("href")
            if not href:
                continue
            url = response.urljoin(href)
            if not self._same_store(url) or self._is_blocked(url) or self._is_product(url):
                continue
            path = urlparse(url).path.lower()
            text = (a.xpath("string(.)").get() or "").strip().lower()
            if any(k in path for k in ("/notebook", "/microproces", "/procesador", "/placa", "/memoria", "/monitor", "/disco", "/perifer", "/gabinete", "/fuente", "/mother", "/componente", "/pc-de-escritorio", "/gaming", "/audio", "/impres", "/tablet", "/silla", "/conect", "/acces", "/camara")) or any(k in text for k in ("notebook", "procesador", "placa", "memoria", "monitor", "almacenamiento", "perifericos", "gaming")):
                yield scrapy.Request(
                    self._page_url(url, 1),
                    callback=self.parse,
                    meta={"listing_root": url, "listing_page": 1},
                )
