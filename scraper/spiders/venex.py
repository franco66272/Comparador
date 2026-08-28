import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96
    MAX_PAGES_PER_CATEGORY = 20

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 6,
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 1200,
    }

    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/accesorios/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
        "/hogar-y-oficina/",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_products = set()
        self.seen_listings = set()
        self.seen_categories = set()

    async def start(self):
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url not in self.seen_listings:
                self.seen_listings.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"page": 1, "discover_children": True})

    @staticmethod
    def clean_text(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def same_store(url):
        try:
            return urlparse(url).netloc.lower().removeprefix("www.") == "venex.com.ar"
        except Exception:
            return False

    @staticmethod
    def is_product(url):
        path = urlparse(url).path.lower()
        if not path.endswith(".html"):
            return False
        blocked = ("micrositio.html", "configurador-de-pc.html")
        return not path.endswith(blocked)

    @staticmethod
    def _clean_path(path):
        path = re.sub(r"/{2,}", "/", path or "/")
        known = ("perifericos", "componentes-de-pc", "impresion-y-scanners",
                 "pc-de-escritorio", "conectividad-y-redes", "accesorios",
                 "almacenamiento", "memorias-ram", "placas-de-video",
                 "monitores", "hogar-y-oficina")
        for token in known:
            path = path.replace(f"/{token}{token}/", f"/{token}/")
        for _ in range(8):
            new_path = re.sub(r"/([^/]+)/\1(?=/|$)", r"/\1", path, flags=re.I)
            if new_path == path:
                break
            path = new_path
        return path

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: v[-1] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar",
                           self._clean_path(p.path), p.params, urlencode(q), p.fragment))

    def _category_key(self, url):
        return self._clean_path(urlparse(url).path).rstrip("/").lower() or "/"

    @staticmethod
    def _numeric_price(value):
        if value is None:
            return None
        s = str(value).strip().replace("$", "").replace("ARS", "")
        s = re.sub(r"[^0-9.,]", "", s)
        if not s:
            return None
        if "," in s and "." in s:
            s = s.split(",", 1)[0].replace(".", "")
        elif "," in s:
            s = s.split(",", 1)[0]
        else:
            s = s.replace(".", "")
        try:
            n = int(s)
        except ValueError:
            return None
        return n if n >= 1000 else None

    def _find_price(self, card):
        # Venex exposes the current price in the product card. Never inspect
        # arbitrary text: RAM capacities, monitor sizes, years, etc. are numbers too.
        selectors = (
            "[itemprop='price']::attr(content)", "[itemprop='price']::text",
            "[data-price]::attr(data-price)", "[data-product-price]::attr(data-product-price)",
            "[data-price-amount]::attr(data-price-amount)",
            ".product-box-price::text", ".product-price::text", ".current-price::text",
            ".price-final::text", ".special-price::text", ".price::text",
        )
        for selector in selectors:
            for raw in card.css(selector).getall():
                value = self._numeric_price(raw)
                if value:
                    return value
        return None

    def _find_old_price(self, card):
        for selector in (".product-box-old-price::text", ".old-price::text",
                         ".price-old::text", ".was-price::text"):
            for raw in card.css(selector).getall():
                value = self._numeric_price(raw)
                if value:
                    return value
        return None

    def _product_card(self, link):
        # Do NOT walk to an arbitrary large ancestor. Pick the nearest ancestor
        # that actually looks like a product tile. This prevents one card's price
        # or image from leaking into neighboring products.
        for node in link.xpath("ancestor::*"):
            cls = (node.attrib.get("class") or "").lower()
            if not any(x in cls for x in ("product", "item", "card", "box")):
                continue
            text = self.clean_text(node.xpath("string(.)").get())
            if 20 <= len(text) <= 1800 and self._find_price(node):
                return node
        return None

    def _extract_product(self, link, response):
        href = link.attrib.get("href")
        if not href:
            return None
        url = response.urljoin(href).split("#", 1)[0]
        if not self.same_store(url) or not self.is_product(url):
            return None

        card = self._product_card(link)
        if card is None:
            return None

        # Prefer a title attached to the product link; otherwise use the card's
        # heading, not arbitrary link text such as "Ver producto".
        name = self.clean_text(
            link.attrib.get("title") or link.attrib.get("aria-label") or
            card.css("h2::text, h3::text, h4::text, .product-name::text, .product-title::text").get()
        )
        if len(name) < 3:
            name = self.clean_text(link.xpath("string(.)").get())
        if len(name) < 3 or len(name) > 300:
            return None

        price = self._find_price(card)
        if not price:
            return None

        image = None
        img = card.css("img")[:1]
        if img:
            src = (img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or
                   img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or
                   img.attrib.get("data-src") or img.attrib.get("src"))
            if src:
                image = response.urljoin(src)

        product_id = None
        for attr in ("data-id", "data-product-id", "data-sku"):
            product_id = link.attrib.get(attr) or card.attrib.get(attr)
            if product_id:
                break

        return {
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": self._find_old_price(card),
            "stock": 1,
            "imagen": image,
            "url": url,
            "id_producto": str(product_id or url),
        }

    def extract_products(self, response):
        local = set()
        # Product links are .html links. Restrict extraction to these instead of
        # scanning every href and accidentally treating navigation as a product.
        for link in response.css("a[href$='.html']"):
            product = self._extract_product(link, response)
            if not product or product["url"] in local:
                continue
            local.add(product["url"])
            yield product

    def discover_child_categories(self, response):
        found = set()
        parent = self._category_key(response.url).rstrip("/")
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if not self.same_store(url) or self.is_product(url):
                continue
            normalized = self.listing_url(url, 1)
            path = self._category_key(normalized).rstrip("/")
            if path == parent or not path.startswith(parent + "/"):
                continue
            if normalized in self.seen_listings or normalized in self.seen_categories:
                continue
            if any(x in path for x in ("resultado-busqueda", "micrositio", "configurador")):
                continue
            found.add(normalized)
        return found

    def current_page(self, response):
        try:
            return max(1, int(response.meta.get("page", 1)))
        except (TypeError, ValueError):
            try:
                return max(1, int(parse_qs(urlparse(response.url).query).get("page", [1])[-1]))
            except (TypeError, ValueError):
                return 1

    def parse_listing(self, response):
        products = list(self.extract_products(response))
        for product in products:
            key = str(product.get("id_producto") or product.get("url"))
            if key in self.seen_products:
                continue
            self.seen_products.add(key)
            yield product

        current = self.current_page(response)
        if response.meta.get("discover_children") and current == 1:
            for child in self.discover_child_categories(response):
                self.seen_categories.add(child)
                self.seen_listings.add(child)
                yield scrapy.Request(child, callback=self.parse_listing,
                                     meta={"page": 1, "discover_children": True})

        if not products or current >= self.MAX_PAGES_PER_CATEGORY:
            return

        next_url = self.listing_url(response.url, current + 1)
        if next_url in self.seen_listings:
            return
        self.seen_listings.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing,
                             meta={"page": current + 1, "discover_children": False})

    def parse(self, response):
        yield from self.parse_listing(response)
