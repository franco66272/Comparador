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
        "CONCURRENT_REQUESTS_PER_DOMAIN": 6,
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 40,
        "RETRY_TIMES": 3,
    }

    EXCLUDED_PATH_PARTS = (
        "resultado-busqueda", "micrositio", "configurador", "login", "cart",
        "checkout", "mi-cuenta", "contacto", "quienes-somos", "oficinas",
        "terminos", "politicas", "garantia", "promociones", "envio-express",
        "create_account", "entrar", "recuperar", "registro",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_products = set()
        self.seen_listings = set()
        self.seen_categories = set()
        self.page_signatures = set()
        self.category_pages = {}
        self.category_products = {}
        self.product_urls_seen = set()
        self.product_urls_extracted = set()
        self.pages_failed = 0

    def start_requests(self):
        # The previous revision accidentally removed the spider entry point.
        # Without start_requests/start_urls Scrapy started and immediately closed
        # without visiting Venex, which caused actualizar.py to keep the old catalog.
        url = self.listing_url(self.BASE + "/", 1)
        self.seen_listings.add(url)
        yield scrapy.Request(url, callback=self.parse_listing,
                             meta={"page": 1, "discover": True},
                             dont_filter=True)

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

    def _clean_path(self, path):
        path = re.sub(r"/{2,}", "/", path or "/")
        for _ in range(5):
            new = re.sub(r"/([^/]+)/\1(?=/|$)", r"/\1", path, flags=re.I)
            if new == path:
                break
            path = new
        return path

    def listing_url(self, url, page=1):
        p = urlparse(url)
        q = {k: v[-1] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
        q.pop("pagina", None)
        q.pop("page", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar",
                           self._clean_path(p.path), p.params, urlencode(q), p.fragment))

    def category_key(self, url):
        return self._clean_path(urlparse(url).path).rstrip("/").lower() or "/"

    @staticmethod
    def numeric_price(value):
        s = re.sub(r"[^0-9.,]", "", str(value or ""))
        if not s:
            return None
        if "," in s and "." in s:
            integer, decimal = s.rsplit(",", 1)
            s = integer if len(decimal) <= 2 else s.replace(",", "")
            s = s.replace(".", "")
        elif "," in s:
            parts = s.split(",")
            s = parts[0] if len(parts[-1]) <= 2 else "".join(parts)
        else:
            s = s.replace(".", "")
        try:
            value = int(s)
        except ValueError:
            return None
        return value if value >= 1000 else None

    def find_price(self, node):
        selectors = (
            "[itemprop='price']::attr(content)", "[itemprop='price']::text",
            "[data-price]::attr(data-price)", "[data-product-price]::attr(data-product-price)",
            "[data-price-amount]::attr(data-price-amount)", "[data-price-value]::attr(data-price-value)",
            ".product-box-price::text", ".product-price::text", ".current-price::text",
            ".price-final::text", ".special-price::text", ".price::text",
        )
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
            src = (img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or
                   img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or
                   img.attrib.get("data-src") or img.attrib.get("src"))
            if src:
                image = response.urljoin(src)
        text = self.clean_text(card.xpath("string(.)").get()).lower()
        stock = 0 if any(term in text for term in ("sin stock", "producto sin stock", "agotado")) else 1
        self.product_urls_extracted.add(url)
        return {
            "tienda": "Venex", "nombre": name, "precio": price,
            "precio_anterior": None, "stock": stock, "imagen": image,
            "url": url, "id_producto": url,
        }

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
                    stack.extend(obj)
                    continue
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
                if isinstance(image, list):
                    image = image[0] if image else None
                self.product_urls_extracted.add(url)
                result.append({
                    "tienda": "Venex", "nombre": name, "precio": price,
                    "precio_anterior": None, "stock": 1,
                    "imagen": response.urljoin(image) if image else None,
                    "url": url,
                    "id_producto": str(obj.get("sku") or obj.get("mpn") or url),
                })
        return result

    def extract_products(self, response):
        products = {p["url"]: p for p in self.structured_products(response)}
        for link in response.css("a[href$='.html'], a[href*='.html?']"):
            product = self.extract_product(link, response)
            if product:
                products.setdefault(product["url"], product)
        return list(products.values())

    def raw_product_urls(self, response):
        urls = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if self.same_store(url) and self.is_product(url):
                urls.add(url)
        return urls

    def discover_categories(self, response):
        found = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if not self.same_store(url) or self.is_product(url):
                continue
            path = self._clean_path(urlparse(url).path).rstrip("/") or "/"
            low = path.lower()
            if any(part in low for part in self.EXCLUDED_PATH_PARTS):
                continue
            # Only crawl catalogue-like paths. This prevents the root page from
            # turning the spider into a generic site crawler.
            if path == "/" or "." in path.rsplit("/", 1)[-1]:
                continue
            normalized = self.listing_url(url, 1)
            if normalized not in self.seen_listings and normalized not in self.seen_categories:
                found.add(normalized)
        return found

    def page_number(self, response):
        try:
            return max(1, int(response.meta.get("page", 1)))
        except (TypeError, ValueError):
            try:
                return max(1, int(parse_qs(urlparse(response.url).query).get("page", [1])[-1]))
            except (TypeError, ValueError):
                return 1

    def parse_listing(self, response):
        category = self.category_key(response.url)
        page = self.page_number(response)
        self.category_pages.setdefault(category, set()).add(page)
        raw_urls = self.raw_product_urls(response)
        self.product_urls_seen.update(raw_urls)
        signature = (category, tuple(sorted(raw_urls)))
        repeated = signature in self.page_signatures
        self.page_signatures.add(signature)

        products = self.extract_products(response)
        self.category_products.setdefault(category, set()).update(p["url"] for p in products)
        for product in products:
            key = product["id_producto"]
            if key in self.seen_products:
                continue
            self.seen_products.add(key)
            yield product

        # Discover subcategories recursively from every first page.
        if page == 1:
            for child in self.discover_categories(response):
                self.seen_categories.add(child)
                self.seen_listings.add(child)
                yield scrapy.Request(child, callback=self.parse_listing,
                                     meta={"page": 1, "discover": True})

        if repeated or not raw_urls or page >= self.MAX_PAGES_PER_CATEGORY:
            return
        next_url = self.listing_url(response.url, page + 1)
        if next_url in self.seen_listings:
            return
        self.seen_listings.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing,
                             meta={"page": page + 1, "discover": False})

    def closed(self, reason):
        pages = sum(len(v) for v in self.category_pages.values())
        print("=" * 72)
        print("VENEX CATALOG REPORT")
        print("=" * 72)
        print(f"reason={reason}")
        print(f"categories_discovered={len(self.seen_categories)}")
        print(f"listing_pages={pages}")
        print(f"raw_product_urls={len(self.product_urls_seen)}")
        print(f"products_extracted={len(self.product_urls_extracted)}")
        print(f"products_unique={len(self.seen_products)}")
        print("=" * 72)

    def parse(self, response):
        yield from self.parse_listing(response)
