import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexCatalogSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96
    MAX_PAGES_PER_CATEGORY = 200

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 35,
        "RETRY_TIMES": 2,
        "LOG_LEVEL": "INFO",
        "CLOSESPIDER_ERRORCOUNT": 50,
    }

    # Known catalog entry points. They are deliberately finite: the previous
    # recursive whole-site crawl could enqueue navigation/filter URLs forever.
    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/", "/monitores/",
        "/sillas-gamers/", "/sillas-y-butacas/", "/accesorios/", "/impresion-y-scanners/",
        "/tablets/", "/camaras-ip/", "/relojes-smartwatch/", "/audio/", "/conectividad/",
        "/hogar-y-oficina/", "/soportes/", "/celulares/", "/televisores/",
    ]

    EXCLUDED_PATH_PARTS = (
        "resultado-busqueda", "micrositio", "configurador", "login", "cart",
        "checkout", "mi-cuenta", "contacto", "quienes-somos", "oficinas",
        "terminos", "politicas", "garantia", "promociones", "envio-express",
        "create_account", "entrar", "recuperar", "registro",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_products = set()
        self.seen_pages = set()
        self.category_pages = {}
        self.category_products = {}
        self.failed_pages = []
        self.raw_product_urls = set()
        self.extracted_urls = set()
        self.page_signatures = set()

    def start_requests(self):
        for path in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + path, 1)
            if url in self.seen_pages:
                continue
            self.seen_pages.add(url)
            yield scrapy.Request(url, callback=self.parse_listing, errback=self.errback_listing,
                                 meta={"page": 1, "category_seed": path})

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

    @staticmethod
    def category_path(url):
        return urlparse(url).path.rstrip("/").lower() or "/"

    def listing_url(self, url, page=1):
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
            a, b = s.rsplit(",", 1)
            s = a if len(b) <= 2 else s.replace(",", "")
            s = s.replace(".", "")
        elif "," in s:
            parts = s.split(",")
            s = parts[0] if len(parts[-1]) <= 2 else "".join(parts)
        else:
            s = s.replace(".", "")
        try:
            n = int(s)
        except ValueError:
            return None
        return n if n >= 1000 else None

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
            hrefs = []
            for anchor in node.css("a[href]"):
                ahref = anchor.attrib.get("href", "")
                if ahref.lower().split("?", 1)[0].endswith(".html"):
                    hrefs.append(ahref)
            if hrefs and len(set(hrefs)) == 1 and hrefs[0] == href and self.find_price(node):
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
        price = self.find_price(card)
        if not name or not price:
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
        stock = 0 if any(x in text for x in ("sin stock", "producto sin stock", "agotado")) else 1
        return {
            "tienda": "Venex", "nombre": name, "precio": price,
            "precio_anterior": None, "stock": stock, "imagen": image,
            "url": url, "id_producto": url,
        }

    def extract_structured(self, response):
        products = []
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
                if not self.same_store(url) or not self.is_product(url):
                    continue
                offers = obj.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                price = self.numeric_price(offers.get("price")) if isinstance(offers, dict) else None
                name = self.clean_text(obj.get("name"))
                if not name or not price:
                    continue
                image = obj.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                products.append({
                    "tienda": "Venex", "nombre": name, "precio": price,
                    "precio_anterior": None, "stock": 1,
                    "imagen": response.urljoin(image) if image else None,
                    "url": url, "id_producto": str(obj.get("sku") or obj.get("mpn") or url),
                })
        return products

    def extract_products(self, response):
        by_url = {p["url"]: p for p in self.extract_structured(response)}
        for link in response.css("a[href$='.html'], a[href*='.html?']"):
            product = self.extract_product(link, response)
            if product:
                by_url.setdefault(product["url"], product)
        return list(by_url.values())

    def child_categories(self, response):
        found = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if not self.same_store(url) or self.is_product(url):
                continue
            path = self.category_path(url)
            if path == "/" or any(part in path for part in self.EXCLUDED_PATH_PARTS):
                continue
            # Only discover one additional level beneath a seeded category.
            # This retains coverage without recursively crawling the entire site.
            parent = self.category_path(response.url)
            if parent != "/" and not path.startswith(parent + "/"):
                continue
            normalized = self.listing_url(url, 1)
            if normalized not in self.seen_pages:
                found.add(normalized)
        return found

    def parse_listing(self, response):
        category = self.category_path(response.url)
        page = int(response.meta.get("page", 1))
        self.category_pages.setdefault(category, set()).add(page)
        raw_urls = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if self.same_store(url) and self.is_product(url):
                raw_urls.add(url)
        self.raw_product_urls.update(raw_urls)
        signature = (category, tuple(sorted(raw_urls)))
        repeated = signature in self.page_signatures
        self.page_signatures.add(signature)

        products = self.extract_products(response)
        self.category_products.setdefault(category, set()).update(p["url"] for p in products)
        for product in products:
            key = product["id_producto"]
            if key not in self.seen_products:
                self.seen_products.add(key)
                yield product

        if page == 1:
            for child in self.child_categories(response):
                self.seen_pages.add(child)
                yield scrapy.Request(child, callback=self.parse_listing, errback=self.errback_listing,
                                     meta={"page": 1, "category_seed": response.meta.get("category_seed", category)})

        if repeated or not raw_urls or page >= self.MAX_PAGES_PER_CATEGORY:
            return
        next_url = self.listing_url(response.url, page + 1)
        if next_url in self.seen_pages:
            return
        self.seen_pages.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing, errback=self.errback_listing,
                             meta={"page": page + 1, "category_seed": response.meta.get("category_seed", category)})

    def errback_listing(self, failure):
        request = failure.request
        self.failed_pages.append(request.url)
        self.logger.warning("Venex listing failed: %s", request.url)

    def closed(self, reason):
        pages = sum(len(v) for v in self.category_pages.values())
        print("=" * 72)
        print("VENEX CATALOG REPORT")
        print("=" * 72)
        print(f"reason={reason}")
        print(f"categories={len(self.category_pages)}")
        print(f"listing_pages={pages}")
        print(f"raw_product_urls={len(self.raw_product_urls)}")
        print(f"products_unique={len(self.seen_products)}")
        print(f"pages_failed={len(self.failed_pages)}")
        if self.failed_pages:
            print("failed_pages=")
            for url in self.failed_pages[:20]:
                print(f"  {url}")
        print("=" * 72)

    def parse(self, response):
        yield from self.parse_listing(response)
