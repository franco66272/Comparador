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
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 700,
        "DUPEFILTER_DEBUG": False,
    }

    # Broad category roots currently exposed by Venex.
    CATEGORY_SEEDS = [
        "/hogar-y-oficina/", "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/accesorios/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
    ]

    SEARCH_TERMS = [
        "notebook", "procesador", "placa de video", "memoria ram", "ssd", "disco",
        "monitor", "motherboard", "gabinete", "fuente", "cooler", "teclado", "mouse",
        "auricular", "joystick", "webcam", "microfono", "router", "wifi", "impresora",
        "tablet", "silla gamer", "pc gamer", "consola", "playstation", "xbox", "nintendo",
        "smartwatch", "cable", "adaptador", "camara", "kingston", "asus", "msi", "lenovo",
        "hp", "intel", "amd", "nvidia",
    ]

    CATEGORY_HINTS = (
        "/notebook", "/microproces", "/placa", "/memoria", "/monitor", "/disco", "/almacen",
        "/component", "/perifer", "/pc-de-escritorio", "/gaming", "/audio", "/impres",
        "/tablet", "/silla", "/conect", "/acces", "/camara", "/reloj", "/hogar",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_product_ids = set()
        self.seen_listing_urls = set()
        self.seen_category_paths = set()

    async def start(self):
        # Only root categories are seeded. Child categories are discovered once
        # from each root, preventing dozens of duplicate branches.
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            key = self.category_key(url)
            if key in self.seen_category_paths:
                continue
            self.seen_category_paths.add(key)
            self.seen_listing_urls.add(url)
            yield scrapy.Request(url, callback=self.parse_listing,
                                 meta={"kind": "category", "branch": key,
                                       "page": 1, "discover_children": True})

        # Search is fallback discovery only. One page per term is sufficient to
        # catch products absent from the root category pages without exploding
        # the request count.
        for term in self.SEARCH_TERMS:
            url = self.search_url(term, 1)
            if url not in self.seen_listing_urls:
                self.seen_listing_urls.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "search", "branch": term,
                                           "page": 1, "discover_children": False})

    def search_url(self, term, page):
        return f"{self.SEARCH}?{urlencode({'keywords': term, 'limit': self.LIMIT, 'page': page})}"

    @staticmethod
    def _clean_path(path):
        path = re.sub(r"/{2,}", "/", path or "/")
        for _ in range(10):
            new_path = re.sub(r"/([^/]+)/\1(?=/|$)", r"/\1", path, flags=re.I)
            if new_path == path:
                break
            path = new_path
        return path

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: (v[-1] if isinstance(v, list) else v)
             for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        path = self._clean_path(p.path)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar",
                           path, p.params, urlencode(q), p.fragment))

    @staticmethod
    def same_store(url):
        try:
            return urlparse(url).netloc.lower().removeprefix("www.") == "venex.com.ar"
        except Exception:
            return False

    @staticmethod
    def is_product(url):
        if not url:
            return False
        path = urlparse(url).path.lower()
        return path.endswith(".html") or any(x in path for x in ("/producto/", "/product/", "/productos/"))

    @staticmethod
    def price(value):
        digits = re.sub(r"[^\d]", "", str(value or ""))
        if not digits:
            return None
        n = int(digits)
        return n if n >= 100 else None

    @staticmethod
    def absolute_image(response, src):
        if not src:
            return None
        return response.urljoin(src.strip())

    def extract_card(self, card, response):
        link = (card.css(".product-box-title a") or card.css(".product-title a") or
                card.css(".product-name a") or card.css("h2 a") or
                card.css("h3 a") or card.css("a[href]"))
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

        nodes = card.css(".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price")
        price = self.price(nodes.xpath("string(.)").get() if nodes else None)
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
            image = self.absolute_image(response, src)

        m = re.search(r'"id":"([^"]+)"', link.attrib.get("onclick", ""))
        product_id = m.group(1) if m else card.css("[itemprop=sku]::attr(content), .sku::text").get()
        key = (product_id or url).strip()
        return {
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": old_price,
            "stock": 1,
            "imagen": image,
            "url": url,
            "id_producto": key,
        }

    def extract_products(self, response):
        selectors = (
            ".item-prod-show .product-box", ".product-box", ".product-item",
            ".product-card", "article.product", "[itemtype*='Product']"
        )
        best = max((response.css(s) for s in selectors), key=len, default=[])
        for card in best:
            product = self.extract_card(card, response)
            if product:
                yield product

    def current_page(self, response):
        vals = parse_qs(urlparse(response.url).query).get("page") or parse_qs(urlparse(response.url).query).get("pagina")
        try:
            return max(1, int(vals[0])) if vals else int(response.meta.get("page", 1))
        except (ValueError, TypeError):
            return 1

    def category_key(self, url):
        return self._clean_path(urlparse(url).path).rstrip("/").lower() or "/"

    def discover_child_categories(self, response):
        parent = self.category_key(response.url)
        children = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            if not self.same_store(url) or self.is_product(url):
                continue
            normalized = self.listing_url(url, 1)
            if "resultado-busqueda" in urlparse(normalized).path.lower():
                continue
            child = self.category_key(normalized)
            if child == parent or not child.startswith(parent.rstrip("/") + "/"):
                continue
            if not any(h in child for h in self.CATEGORY_HINTS):
                continue
            if child in self.seen_category_paths:
                continue
            children.add(normalized)
        return children

    def has_pagination_signal(self, response):
        current = self.current_page(response)
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            q = parse_qs(urlparse(url).query)
            vals = q.get("page") or q.get("pagina")
            if not vals:
                continue
            try:
                if int(vals[0]) > current:
                    return True
            except ValueError:
                continue
        return bool(response.css('a[rel="next"], a.next, .pagination .next'))

    def parse_listing(self, response):
        products = list(self.extract_products(response))

        new_products = []
        for product in products:
            key = str(product.get("id_producto") or product.get("url") or "").strip()
            if not key or key in self.seen_product_ids:
                continue
            self.seen_product_ids.add(key)
            new_products.append(product)
            yield product

        current = self.current_page(response)
        kind = response.meta.get("kind")

        # Discover the real child category tree once per root/child page.
        if response.meta.get("discover_children") and current == 1:
            for child in self.discover_child_categories(response):
                child_key = self.category_key(child)
                self.seen_category_paths.add(child_key)
                self.seen_listing_urls.add(child)
                yield scrapy.Request(
                    child,
                    callback=self.parse_listing,
                    meta={"kind": "category", "branch": child_key, "page": 1,
                          "discover_children": True},
                )

        if not products:
            return

        # Paginate categories deeper than searches, but only while Venex exposes
        # a real next-page signal. This avoids blindly walking fabricated pages.
        max_pages = 12 if kind == "category" else 4
        if current >= max_pages or not self.has_pagination_signal(response):
            return

        next_url = self.listing_url(response.url, current + 1)
        if next_url in self.seen_listing_urls:
            return
        self.seen_listing_urls.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing,
                             meta={**response.meta, "page": current + 1,
                                   "discover_children": False})

    def parse(self, response):
        yield from self.parse_listing(response)
