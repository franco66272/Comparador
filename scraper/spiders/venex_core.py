import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexCoreSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96
    MAX_PAGES_PER_CATEGORY = 300

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY": 0.05,
        "DOWNLOAD_TIMEOUT": 30,
        "RETRY_TIMES": 2,
    }

    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/accesorios/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
        "/hogar-y-oficina/", "/soportes/", "/celulares/", "/televisores/",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_products = set()
        self.seen_listings = set()
        self.seen_categories = set()
        self.page_signatures = set()

    async def start(self):
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url not in self.seen_listings:
                self.seen_listings.add(url)
                yield scrapy.Request(url, callback=self.parse_listing, meta={"page": 1, "discover_children": True}, dont_filter=True)

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
        return path.endswith(".html") and not path.endswith(("micrositio.html", "configurador-de-pc.html", "404.html"))

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: v[-1] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q.pop("page", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar", p.path, p.params, urlencode(q), p.fragment))

    @staticmethod
    def numeric_price(value):
        s = re.sub(r"[^0-9.,]", "", str(value or ""))
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

    def find_price(self, node):
        selectors = ("[itemprop='price']::attr(content)", "[itemprop='price']::text", "[data-price]::attr(data-price)", "[data-product-price]::attr(data-product-price)", ".product-box-price::text", ".product-price::text", ".current-price::text", ".price-final::text", ".special-price::text", ".price::text")
        for selector in selectors:
            for raw in node.css(selector).getall():
                price = self.numeric_price(raw)
                if price:
                    return price
        text = self.clean_text(node.xpath("string(.)").get())
        for raw in re.findall(r"(?:\$\s*|ARS\s+)([0-9][0-9.]*(?:,[0-9]{1,2})?)", text, re.I):
            price = self.numeric_price(raw)
            if price:
                return price
        return None

    def product_card(self, link):
        href = link.attrib.get("href", "")
        for node in link.xpath("ancestor::*"):
            text = self.clean_text(node.xpath("string(.)").get())
            if not 10 <= len(text) <= 1800:
                continue
            product_hrefs = []
            for anchor in node.css("a[href]"):
                ahref = anchor.attrib.get("href", "")
                if ahref.lower().split("?", 1)[0].endswith(".html"):
                    product_hrefs.append(ahref)
            if len(set(product_hrefs)) == 1 and product_hrefs[0] == href and self.find_price(node):
                return node
        return None

    def extract_product(self, link, response):
        href = link.attrib.get("href")
        if not href:
            return None
        url = response.urljoin(href).split("#", 1)[0]
        if not self.same_store(url) or not self.is_product(url):
            return None
        card = self.product_card(link)
        if card is None:
            return None
        name = self.clean_text(link.attrib.get("title") or link.attrib.get("aria-label") or link.xpath("string(.)").get())
        if not 3 <= len(name) <= 300:
            name = self.clean_text(card.css("h2::text, h3::text, h4::text, .product-name::text, .product-title::text").get())
        if not 3 <= len(name) <= 300:
            return None
        price = self.find_price(card)
        if not price:
            return None
        image = None
        img = card.css("img")[:1]
        if img:
            src = img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or img.attrib.get("data-src") or img.attrib.get("src")
            if src:
                image = response.urljoin(src)
        text = self.clean_text(card.xpath("string(.)").get()).lower()
        stock = 0 if "sin stock" in text or "producto sin stock" in text else 1
        return {"tienda":"Venex", "nombre":name, "precio":price, "precio_anterior":None, "stock":stock, "imagen":image, "url":url, "id_producto":url}

    def structured_products(self, response):
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
                    stack.extend(obj); continue
                if not isinstance(obj, dict):
                    continue
                if isinstance(obj.get("@graph"), list):
                    stack.extend(obj["@graph"])
                typ = obj.get("@type")
                if "Product" not in (typ if isinstance(typ, list) else [typ]):
                    continue
                url = response.urljoin(str(obj.get("url") or "")).split("#", 1)[0]
                offers = obj.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                price = self.numeric_price(offers.get("price")) if isinstance(offers, dict) else None
                name = self.clean_text(obj.get("name"))
                if not name or not price or not self.same_store(url) or not self.is_product(url):
                    continue
                image = obj.get("image")
                if isinstance(image, list): image = image[0] if image else None
                result.append({"tienda":"Venex", "nombre":name, "precio":price, "precio_anterior":None, "stock":1, "imagen":response.urljoin(image) if image else None, "url":url, "id_producto":str(obj.get("sku") or obj.get("mpn") or url)})
        return result

    def extract_products(self, response):
        products = {p["url"]: p for p in self.structured_products(response)}
        for link in response.css("a[href$='.html'], a[href*='.html?']"):
            p = self.extract_product(link, response)
            if p:
                products.setdefault(p["url"], p)
        return list(products.values())

    def raw_product_urls(self, response):
        urls = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if self.same_store(url) and self.is_product(url):
                urls.add(url)
        return urls

    def discover_child_categories(self, response):
        found = set()
        parent = urlparse(response.url).path.rstrip("/").lower()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if not self.same_store(url) or self.is_product(url):
                continue
            path = urlparse(url).path.rstrip("/").lower()
            if path == parent or not path.startswith(parent + "/"):
                continue
            if any(x in path for x in ("resultado-busqueda", "micrositio", "configurador", "login", "cart")):
                continue
            normalized = self.listing_url(url, 1)
            if normalized not in self.seen_listings:
                found.add(normalized)
        return found

    def parse_listing(self, response):
        raw_urls = self.raw_product_urls(response)
        category = urlparse(response.url).path.rstrip("/").lower()
        signature = (category, tuple(sorted(raw_urls)))
        repeated = signature in self.page_signatures
        self.page_signatures.add(signature)
        for product in self.extract_products(response):
            key = product["id_producto"]
            if key not in self.seen_products:
                self.seen_products.add(key)
                yield product
        page = int(response.meta.get("page", 1))
        if response.meta.get("discover_children") and page == 1:
            for child in self.discover_child_categories(response):
                self.seen_categories.add(child); self.seen_listings.add(child)
                yield scrapy.Request(child, callback=self.parse_listing, meta={"page":1, "discover_children":True})
        if repeated or not raw_urls or len(raw_urls) < self.LIMIT or page >= self.MAX_PAGES_PER_CATEGORY:
            return
        next_url = self.listing_url(response.url, page + 1)
        if next_url in self.seen_listings:
            return
        self.seen_listings.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing, meta={"page":page+1, "discover_children":False})

    def parse(self, response):
        yield from self.parse_listing(response)
