import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexCatalogV2Spider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    BASE = "https://www.venex.com.ar"
    LIMIT = 96
    MAX_PAGES_PER_CATEGORY = 80

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 6,
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 25,
        "RETRY_TIMES": 1,
        "LOG_LEVEL": "INFO",
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.10,
        "AUTOTHROTTLE_MAX_DELAY": 3.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 3.0,
    }

    # Fixed catalogue entry points. We intentionally do NOT recursively crawl
    # navigation/filter URLs: that was the source of the previous runaway crawl.
    CATEGORY_SEEDS = [
        "/notebooks/", "/microprocesadores/", "/perifericos/",
        "/almacenamiento-portatil/", "/almacenamiento/", "/placas-de-video/",
        "/componentes-de-pc/", "/pc-de-escritorio/", "/memorias-ram/",
        "/monitores/", "/sillas-gamers/", "/sillas-y-butacas/", "/accesorios/",
        "/impresion-y-scanners/", "/tablets/", "/camaras-ip/",
        "/relojes-smartwatch/", "/audio/", "/conectividad/", "/hogar-y-oficina/",
        "/soportes/", "/celulares/", "/televisores/",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_pages = set()
        self.seen_products = set()
        self.page_signatures = set()
        self.pages_ok = 0
        self.pages_failed = []
        self.raw_urls = set()

    @staticmethod
    def clean(value):
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
        q.pop("page", None)
        q.pop("pagina", None)
        q["limit"] = str(self.LIMIT)
        q["page"] = str(page)
        return urlunparse((p.scheme or "https", p.netloc or "www.venex.com.ar", p.path.rstrip("/") or "/", p.params, urlencode(q), p.fragment))

    def start_requests(self):
        for seed in self.CATEGORY_SEEDS:
            url = self.listing_url(self.BASE + seed, 1)
            self.seen_pages.add(url)
            yield scrapy.Request(url, callback=self.parse_listing, errback=self.errback_listing, meta={"page": 1, "seed": seed})

    def price(self, value):
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
            return n if n >= 1000 else None
        except ValueError:
            return None

    def find_price(self, node):
        selectors = (
            "[itemprop='price']::attr(content)", "[itemprop='price']::text",
            "[data-price]::attr(data-price)", "[data-product-price]::attr(data-product-price)",
            "[data-price-amount]::attr(data-price-amount)", ".product-box-price::text",
            ".product-price::text", ".current-price::text", ".price-final::text",
            ".special-price::text", ".price::text",
        )
        for selector in selectors:
            for raw in node.css(selector).getall():
                p = self.price(raw)
                if p:
                    return p
        text = self.clean(node.xpath("string(.)").get())
        for raw in re.findall(r"(?:\$\s*|ARS\s+)([0-9][0-9.]*(?:,[0-9]{1,2})?)", text, re.I):
            p = self.price(raw)
            if p:
                return p
        return None

    def extract_card(self, link, response):
        href = link.attrib.get("href", "")
        url = response.urljoin(href).split("#", 1)[0]
        if not self.same_store(url) or not self.is_product(url):
            return None
        for node in link.xpath("ancestor::*"):
            text = self.clean(node.xpath("string(.)").get())
            if not 10 <= len(text) <= 1800:
                continue
            links = []
            for a in node.css("a[href]"):
                h = a.attrib.get("href", "")
                if h.lower().split("?", 1)[0].endswith(".html"):
                    links.append(h)
            if not links or len(set(links)) != 1 or links[0] != href:
                continue
            p = self.find_price(node)
            if not p:
                continue
            name = self.clean(link.attrib.get("title") or link.attrib.get("aria-label") or link.xpath("string(.)").get())
            if not 3 <= len(name) <= 300:
                name = self.clean(node.css("h2::text, h3::text, h4::text, .product-name::text, .product-title::text").get())
            if not name:
                continue
            image = None
            img = node.css("img")[:1]
            if img:
                src = (img.attrib.get("data-zoom-image") or img.attrib.get("data-large-image") or
                       img.attrib.get("data-original") or img.attrib.get("data-lazy-src") or
                       img.attrib.get("data-src") or img.attrib.get("src"))
                if src:
                    image = response.urljoin(src)
            lower = text.lower()
            stock = 0 if any(x in lower for x in ("sin stock", "producto sin stock", "agotado")) else 1
            return {"tienda":"Venex", "nombre":name, "precio":p, "precio_anterior":None,
                    "stock":stock, "imagen":image, "url":url, "id_producto":url}
        return None

    def extract_structured(self, response):
        out = []
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
                p = self.price(offers.get("price")) if isinstance(offers, dict) else None
                name = self.clean(obj.get("name"))
                if not name or not p or not self.same_store(url) or not self.is_product(url):
                    continue
                image = obj.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                out.append({"tienda":"Venex", "nombre":name, "precio":p, "precio_anterior":None,
                            "stock":1, "imagen":response.urljoin(image) if image else None,
                            "url":url, "id_producto":str(obj.get("sku") or obj.get("mpn") or url)})
        return out

    def extract_products(self, response):
        by_url = {p["url"]: p for p in self.extract_structured(response)}
        for link in response.css("a[href$='.html'], a[href*='.html?']"):
            p = self.extract_card(link, response)
            if p:
                by_url.setdefault(p["url"], p)
        return list(by_url.values())

    def parse_listing(self, response):
        page = int(response.meta["page"])
        seed = response.meta["seed"]
        raw = set()
        for href in response.css("a[href]::attr(href)").getall():
            url = response.urljoin(href).split("#", 1)[0]
            if self.same_store(url) and self.is_product(url):
                raw.add(url)
        self.raw_urls.update(raw)
        signature = (seed, tuple(sorted(raw)))
        repeated = signature in self.page_signatures
        self.page_signatures.add(signature)
        products = self.extract_products(response)
        self.pages_ok += 1
        new_count = 0
        for p in products:
            key = p["id_producto"]
            if key in self.seen_products:
                continue
            self.seen_products.add(key)
            new_count += 1
            yield p
        self.logger.info("VENEX %s page=%d raw=%d products=%d new=%d total=%d", seed, page, len(raw), len(products), new_count, len(self.seen_products))

        # A listing with no product URLs or an identical page is the reliable
        # end condition. No child-category discovery is performed.
        if repeated or not raw or len(raw) < self.LIMIT or page >= self.MAX_PAGES_PER_CATEGORY:
            return
        next_url = self.listing_url(response.url, page + 1)
        if next_url in self.seen_pages:
            return
        self.seen_pages.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_listing, errback=self.errback_listing,
                             meta={"page": page + 1, "seed": seed})

    def errback_listing(self, failure):
        url = failure.request.url
        self.pages_failed.append(url)
        self.logger.warning("VENEX FAILED %s", url)

    def closed(self, reason):
        print("=" * 70)
        print("VENEX CATALOG REPORT V2")
        print("=" * 70)
        print(f"reason={reason}")
        print(f"seed_categories={len(self.CATEGORY_SEEDS)}")
        print(f"listing_pages_ok={self.pages_ok}")
        print(f"raw_product_urls={len(self.raw_urls)}")
        print(f"products_unique={len(self.seen_products)}")
        print(f"pages_failed={len(self.pages_failed)}")
        if self.pages_failed:
            for url in self.pages_failed[:20]:
                print(f"FAILED {url}")
        print("=" * 70)
