import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 6,
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 20,
        "CLOSESPIDER_PAGECOUNT": 1200,
    }

    CATEGORY_SEEDS = [
        "/hogar-y-oficina/", "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/accesorios/", "/impresion-y-scanners/", "/tablets/",
        "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
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
        self.discovered_categories = set()

    async def start(self):
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url not in self.seen_listing_urls:
                self.seen_listing_urls.add(url)
                yield scrapy.Request(url, callback=self.parse_listing,
                                     meta={"kind": "category", "branch": path, "page": 1,
                                           "discover_children": True})

    @staticmethod
    def _clean_path(path):
        path = path or "/"
        path = re.sub(r"/{2,}", "/", path)
        for _ in range(8):
            new_path = re.sub(r"/([^/]+)/\1(?=/|$)", r"/\1", path, flags=re.I)
            if new_path == path:
                break
            path = new_path
        for token in ("perifericos", "componentes-de-pc", "impresion-y-scanners",
                      "pc-de-escritorio", "conectividad-y-redes", "accesorios",
                      "almacenamiento", "memorias-ram", "placas-de-video", "monitores",
                      "hogar-y-oficina"):
            path = path.replace("/" + token + token + "/", "/" + token + "/")
        return path

    def listing_url(self, url, page):
        p = urlparse(url)
        q = {k: (v[-1] if isinstance(v, list) else v) for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        path = self._clean_path(p.path)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar", path, p.params, urlencode(q), p.fragment))

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
    def clean_text(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _card_container(self, link):
        ancestors = link.xpath("ancestor::*")
        best = None
        best_score = -1
        # Inspect several ancestor levels. Venex uses more than one card markup,
        # so depending on a single CSS class silently loses most products.
        for node in ancestors[-12:]:
            text = self.clean_text(node.xpath("string(.)").get())
            if not text or len(text) > 3000:
                continue
            price_count = len(re.findall(r"(?:\$|ARS)?\s*[0-9][0-9.]{2,}", text))
            if not price_count:
                continue
            score = min(price_count, 5)
            cls = (node.attrib.get("class") or "").lower()
            if any(x in cls for x in ("product", "item", "card", "box", "catalog")):
                score += 5
            # Prefer the smallest useful ancestor: it is less likely to mix prices
            # from neighbouring products.
            score += max(0, 12 - len(ancestors) + ancestors.index(node)) * 0.01
            if score > best_score:
                best, best_score = node, score
        return best or (ancestors[-3] if len(ancestors) >= 3 else link)

    def _product_from_link(self, link, response):
        href = link.attrib.get("href")
        if not href:
            return None
        url = response.urljoin(href).split("#", 1)[0]
        if not self.same_store(url) or not self.is_product(url):
            return None

        node = self._card_container(link)
        text = self.clean_text(node.xpath("string(.)").get())

        # Price may be visible text or an attribute on the card/link.
        sources = [text]
        for attr in ("data-price", "data-product-price", "data-price-amount", "content", "value"):
            if link.attrib.get(attr):
                sources.append(link.attrib[attr])
        if node is not None:
            for attr in ("data-price", "data-product-price", "data-price-amount"):
                if node.attrib.get(attr):
                    sources.append(node.attrib[attr])

        prices = []
        for source in sources:
            for value in re.findall(r"(?:\$|ARS)?\s*([0-9][0-9.]*)", str(source)):
                p = self.price(value)
                if p and p not in prices:
                    prices.append(p)

        # Final fallback: inspect nearby ancestors one by one.
        if not prices:
            for ancestor in link.xpath("ancestor::*")[-10:]:
                t = self.clean_text(ancestor.xpath("string(.)").get())
                for value in re.findall(r"\$\s*([0-9][0-9.]*)", t):
                    p = self.price(value)
                    if p and p not in prices:
                        prices.append(p)
                if prices:
                    break

        if not prices:
            return None
        price = prices[0]
        old_price = prices[1] if len(prices) > 1 else None

        name = ""
        for value in (
            link.attrib.get("title"), link.attrib.get("aria-label"),
            link.css("h1::text, h2::text, h3::text, h4::text, strong::text").get(),
            link.xpath("string(.)").get(),
        ):
            value = self.clean_text(value)
            if len(value) >= 3:
                name = value
                break
        if len(name) < 3:
            return None

        image = None
        img = node.css("img")[:1] if node else []
        if img:
            src = (img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or
                   img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or
                   img.attrib.get("data-src") or img.attrib.get("src"))
            if src:
                image = response.urljoin(src)

        product_id = None
        for attr in ("data-id", "data-product-id", "data-sku"):
            product_id = link.attrib.get(attr) or (node.attrib.get(attr) if node else None)
            if product_id:
                break
        if not product_id:
            m = re.search(r"(?:id|sku)[^0-9]{0,4}(\d{2,})", text, re.I)
            product_id = m.group(1) if m else None
        key = str(product_id or url).strip()
        return {"tienda": "Venex", "nombre": name, "precio": price,
                "precio_anterior": old_price, "stock": 1, "imagen": image,
                "url": url, "id_producto": key}

    def extract_products(self, response):
        seen_urls = set()
        for link in response.css("a[href]"):
            p = self._product_from_link(link, response)
            if not p or p["url"] in seen_urls:
                continue
            seen_urls.add(p["url"])
            yield p

        for p in self.jsonld_products(response):
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
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
                        name = self.clean_text(obj.get("name"))
                        if name and price:
                            image = obj.get("image")
                            if isinstance(image, list):
                                image = image[0] if image else None
                            url = response.urljoin(obj.get("url") or response.url)
                            yield {"tienda": "Venex", "nombre": name, "precio": price,
                                   "precio_anterior": None, "stock": 1,
                                   "imagen": response.urljoin(image) if isinstance(image, str) else None,
                                   "url": url,
                                   "id_producto": str(obj.get("sku") or url)}
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

    def _category_key(self, url):
        return self._clean_path(urlparse(url).path).rstrip("/").lower() or "/"

    def discover_child_categories(self, response):
        found = set()
        parent_key = self._category_key(response.url)
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href)
            if not self.same_store(url) or self.is_product(url):
                continue
            normalized = self.listing_url(url, 1)
            if normalized in self.seen_listing_urls or normalized in self.discovered_categories:
                continue
            if "resultado-busqueda" in urlparse(normalized).path.lower():
                continue
            child_key = self._category_key(normalized)
            if child_key == parent_key or not child_key.startswith(parent_key.rstrip("/") + "/"):
                continue
            if not any(hint in child_key for hint in self.CATEGORY_HINTS):
                continue
            found.add(normalized)
        return found

    def parse_listing(self, response):
        products = list(self.extract_products(response))
        for product in products:
            key = str(product.get("id_producto") or product.get("url") or "").strip()
            if not key or key in self.seen_product_ids:
                continue
            self.seen_product_ids.add(key)
            yield product

        current = self.current_page(response)
        if response.meta.get("discover_children") and current == 1:
            for child in self.discover_child_categories(response):
                self.discovered_categories.add(child)
                self.seen_listing_urls.add(child)
                child_key = self._category_key(child)
                yield scrapy.Request(child, callback=self.parse_listing,
                                     meta={"kind": "category", "branch": child_key, "page": 1,
                                           "discover_children": True})

        if not products or current >= 20:
            return

        next_url = self.listing_url(response.url, current + 1)
        if next_url in self.seen_listing_urls:
            return
        self.seen_listing_urls.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing,
                             meta={**response.meta, "page": current + 1, "discover_children": False})

    def parse(self, response):
        yield from self.parse_listing(response)
