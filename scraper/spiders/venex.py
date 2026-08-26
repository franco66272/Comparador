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
        "CLOSESPIDER_PAGECOUNT": 1800,
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_product_ids = set()
        self.seen_listing_urls = set()

    async def start(self):
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url not in self.seen_listing_urls:
                self.seen_listing_urls.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "category", "page": 1})
        for term in self.SEARCH_TERMS:
            url = self.search_url(term, 1)
            if url not in self.seen_listing_urls:
                self.seen_listing_urls.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "search", "term": term, "page": 1})

    def search_url(self, term, page):
        return f"{self.SEARCH}?{urlencode({'keywords': term, 'limit': self.LIMIT, 'page': page})}"

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: (v[-1] if isinstance(v, list) else v) for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        path = p.path or "/"
        # Fix duplicated path fragments caused by malformed discovered links.
        for _ in range(3):
            new_path = re.sub(r"/([^/]+)/\1(?=/|$)", r"/\1", path, flags=re.I)
            if new_path == path:
                break
            path = new_path
        path = re.sub(r"/{2,}", "/", path)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar", path, p.params, urlencode(q), p.fragment))

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
        if not self.same_store(url) or not self.is_product(url):
            return None
        name = (link.xpath("string(.)").get() or link.attrib.get("title") or "").strip()
        if len(name) < 3:
            return None
        node = card.css(".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price")
        raw = node.xpath("string(.)").get() if node else None
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
        m = re.search(r'"id":"([^"]+)"', link.attrib.get("onclick", ""))
        product_id = m.group(1) if m else card.css("[itemprop=sku]::attr(content), .sku::text").get()
        key = (product_id or url).strip()
        return {"tienda":"Venex","nombre":name,"precio":price,"precio_anterior":old_price,
                "stock":1,"imagen":image,"url":url,"id_producto":key}

    def extract_products(self, response):
        selectors = (".item-prod-show .product-box", ".product-box", ".product-item", ".product-card", "article.product", "[itemtype*='Product']")
        best = max((response.css(s) for s in selectors), key=len, default=[])
        for card in best:
            product = self.extract_card(card, response)
            if product:
                yield product

    def emit_new(self, products):
        added = 0
        for product in products:
            key = str(product.get("id_producto") or product.get("url") or "").strip()
            if not key or key in self.seen_product_ids:
                continue
            self.seen_product_ids.add(key)
            added += 1
            yield product
        return added

    def current_page(self, response):
        vals = parse_qs(urlparse(response.url).query).get("page")
        try:
            return max(1, int(vals[0])) if vals else int(response.meta.get("page", 1))
        except (ValueError, TypeError):
            return 1

    def has_next_signal(self, response, count):
        if response.css('a[rel="next"], a.next, .pagination .next'):
            return True
        current = self.current_page(response)
        for href in response.css("a[href]::attr(href)").getall():
            qs = parse_qs(urlparse(response.urljoin(href)).query)
            vals = qs.get("page") or qs.get("pagina")
            if vals:
                try:
                    if int(vals[0]) > current:
                        return True
                except ValueError:
                    pass
        return count >= self.LIMIT

    def parse_listing(self, response):
        products = list(self.extract_products(response))
        new_count = 0
        for product in self.emit_new(products):
            new_count += 1
            yield product

        current = self.current_page(response)
        kind = response.meta.get("kind")
        # Stop a branch when the page is empty or contributes nothing new.
        if current >= 1 and (not products or (new_count == 0 and current > 1)):
            return
        # Never allow one listing/search branch to consume the whole crawl.
        max_pages = 60 if kind == "search" else 40
        if current < max_pages and self.has_next_signal(response, len(products)):
            next_url = self.listing_url(response.url, current + 1)
            if next_url not in self.seen_listing_urls:
                self.seen_listing_urls.add(next_url)
                yield scrapy.Request(next_url, callback=self.parse_listing,
                                     meta={**response.meta, "page": current + 1})

        # Categories are already seeded explicitly; do not recursively discover
        # every child category from every page.

    def parse(self, response):
        yield from self.parse_listing(response)
