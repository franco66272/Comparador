import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96
    MAX_PAGES_PER_CATEGORY = 60

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.20,
        "DOWNLOAD_TIMEOUT": 30,
        "CLOSESPIDER_PAGECOUNT": 2500,
    }

    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/accesorios/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
        "/hogar-y-oficina/", "/soportes/", "/celulares/", "/televisores/",
    ]

    STRUCTURED_PRODUCT_KEYS = (
        "product", "products", "items", "itemListElement", "offers"
    )

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
                yield scrapy.Request(
                    url,
                    callback=self.parse_listing,
                    meta={"page": 1, "discover_children": True},
                    dont_filter=True,
                )

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
        blocked = ("micrositio.html", "configurador-de-pc.html", "404.html")
        return not path.endswith(blocked)

    @staticmethod
    def _clean_path(path):
        path = re.sub(r"/{2,}", "/", path or "/")
        known = (
            "perifericos", "componentes-de-pc", "impresion-y-scanners",
            "pc-de-escritorio", "conectividad-y-redes", "accesorios",
            "almacenamiento", "memorias-ram", "placas-de-video", "monitores",
            "hogar-y-oficina", "celulares", "televisores", "soportes",
        )
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
        for key in ("pagina", "page"):
            q.pop(key, None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((
            p.scheme or "https",
            p.netloc or "www.venex.com.ar",
            self._clean_path(p.path), p.params,
            urlencode(q), p.fragment,
        ))

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
            number = int(s)
        except ValueError:
            return None
        return number if number >= 1000 else None

    def _find_price(self, node):
        selectors = (
            "[itemprop='price']::attr(content)",
            "[itemprop='price']::text",
            "[data-price]::attr(data-price)",
            "[data-product-price]::attr(data-product-price)",
            "[data-price-amount]::attr(data-price-amount)",
            "[data-price-value]::attr(data-price-value)",
            ".product-box-price::text",
            ".product-price::text",
            ".current-price::text",
            ".price-final::text",
            ".special-price::text",
            ".price::text",
        )
        for selector in selectors:
            for raw in node.css(selector).getall():
                price = self._numeric_price(raw)
                if price:
                    return price

        text = self.clean_text(node.xpath("string(.)").get())
        for raw in re.findall(r"(?:\$\s*|ARS\s+)([0-9][0-9.]*(?:,[0-9]{1,2})?)", text, flags=re.I):
            price = self._numeric_price(raw)
            if price:
                return price
        return None

    def _find_old_price(self, node):
        for selector in (
            ".product-box-old-price::text", ".old-price::text",
            ".price-old::text", ".was-price::text", ".price-list::text",
        ):
            for raw in node.css(selector).getall():
                value = self._numeric_price(raw)
                if value:
                    return value
        return None

    def _product_card(self, link):
        # Stop at the first *small* meaningful ancestor, avoiding page-wide
        # containers that can mix the neighboring products' data.
        for node in link.xpath("ancestor::*"):
            cls = (node.attrib.get("class") or "").lower()
            if not any(token in cls for token in ("product", "item", "card", "box")):
                continue
            text = self.clean_text(node.xpath("string(.)").get())
            if not (20 <= len(text) <= 2200):
                continue
            if len(node.xpath(".//a[contains(@href,'.html')]").getall()) > 4:
                continue
            if self._find_price(node):
                return node
        return None

    def _structured_products(self, response):
        """Read JSON-LD product objects when the page exposes them."""
        result = []
        for raw in response.css("script[type='application/ld+json']::text").getall():
            try:
                data = json.loads(raw)
            except Exception:
                continue

            stack = data if isinstance(data, list) else [data]
            while stack:
                obj = stack.pop()
                if isinstance(obj, list):
                    stack.extend(obj)
                    continue
                if not isinstance(obj, dict):
                    continue
                if "@graph" in obj and isinstance(obj["@graph"], list):
                    stack.extend(obj["@graph"])
                typ = obj.get("@type")
                types = typ if isinstance(typ, list) else [typ]
                if "Product" not in types:
                    continue
                name = self.clean_text(obj.get("name"))
                url = obj.get("url")
                image = obj.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                if url:
                    url = response.urljoin(str(url)).split("#", 1)[0]
                if not url or not self.same_store(url) or not self.is_product(url):
                    continue
                offers = obj.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                price = offers.get("price") if isinstance(offers, dict) else None
                price = self._numeric_price(price)
                product_id = obj.get("sku") or obj.get("mpn") or obj.get("productID")
                if not name or not price:
                    continue
                result.append({
                    "tienda": "Venex",
                    "nombre": name,
                    "precio": price,
                    "precio_anterior": None,
                    "stock": self._stock_value_from_offer(offers),
                    "imagen": response.urljoin(image) if image else None,
                    "url": url,
                    "id_producto": str(product_id or url),
                })
        return result

    @staticmethod
    def _stock_value_from_offer(offers):
        if not isinstance(offers, dict):
            return 0
        availability = str(offers.get("availability") or "").lower()
        if any(x in availability for x in ("instock", "limitedavailability")):
            return 1
        if availability:
            return 0
        return 0

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

        name = self.clean_text(
            link.attrib.get("title") or
            link.attrib.get("aria-label") or
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
            src = (
                img.attrib.get("data-zoom-image") or
                img.attrib.get("data-large-image") or
                img.attrib.get("data-original") or
                img.attrib.get("data-lazy-src") or
                img.attrib.get("data-src") or
                img.attrib.get("src")
            )
            if src:
                image = response.urljoin(src)

        product_id = None
        for attr in ("data-id", "data-product-id", "data-sku"):
            product_id = link.attrib.get(attr) or card.attrib.get(attr)
            if product_id:
                break

        stock_text = self.clean_text(card.xpath("string(.)").get()).lower()
        stock = 1 if any(x in stock_text for x in ("en stock", "disponible", "comprar")) else 0
        if "sin stock" in stock_text or "producto sin stock" in stock_text:
            stock = 0

        return {
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": self._find_old_price(card),
            "stock": stock,
            "imagen": image,
            "url": url,
            "id_producto": str(product_id or url),
        }

    def extract_products(self, response):
        local = {}
        for product in self._structured_products(response):
            local[product["url"]] = product

        for link in response.css("a[href$='.html'], a[href*='.html?']"):
            product = self._extract_product(link, response)
            if product:
                local.setdefault(product["url"], product)

        return list(local.values())

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
            if any(token in path for token in ("resultado-busqueda", "micrositio", "configurador", "login", "cart")):
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
        products = self.extract_products(response)
        unique_page_urls = set()
        for product in products:
            unique_page_urls.add(product["url"])
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
                yield scrapy.Request(
                    child,
                    callback=self.parse_listing,
                    meta={"page": 1, "discover_children": True},
                )

        # Stop on a genuinely empty page, not because one selector failed.
        if not unique_page_urls or current >= self.MAX_PAGES_PER_CATEGORY:
            return

        next_url = self.listing_url(response.url, current + 1)
        if next_url in self.seen_listings:
            return
        self.seen_listings.add(next_url)
        yield scrapy.Request(
            next_url,
            callback=self.parse_listing,
            meta={"page": current + 1, "discover_children": False},
        )

    def parse(self, response):
        yield from self.parse_listing(response)
