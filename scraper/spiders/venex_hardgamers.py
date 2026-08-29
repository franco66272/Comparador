import json
import re
from urllib.parse import urlencode, urlparse, urlunparse

import scrapy


class VenexHardGamersSpider(scrapy.Spider):
    name = "venex_hardgamers"
    allowed_domains = ["hardgamers.com.ar", "www.hardgamers.com.ar"]

    HG_BASE = "https://www.hardgamers.com.ar"
    HG_STORE = "/stores/venex"
    PAGE_SIZE = 100
    MAX_PAGES = 200

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 30,
        "RETRY_TIMES": 2,
        "LOG_LEVEL": "INFO",
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.2,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.5,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_pages = set()
        self.seen_products = set()
        self.pages_ok = 0
        self.pages_failed = []
        self.source_items = 0
        self.raw_products = set()
        self.expected_total = None

    def hg_url(self, page):
        query = {"brand": "", "limit": str(self.PAGE_SIZE), "page": str(page), "province": "", "store": "venex"}
        return f"{self.HG_BASE}{self.HG_STORE}?{urlencode(query)}"

    async def start(self):
        # Scrapy 2.18+ uses the async start hook. Explicitly yielding the first
        # request prevents the spider from finishing immediately with 0 pages.
        url = self.hg_url(1)
        self.seen_pages.add(url)
        yield scrapy.Request(url, callback=self.parse_hg, errback=self.errback_page, meta={"page": 1})

    def start_requests(self):
        # Compatibility with older Scrapy releases.
        url = self.hg_url(1)
        if url not in self.seen_pages:
            self.seen_pages.add(url)
            yield scrapy.Request(url, callback=self.parse_hg, errback=self.errback_page, meta={"page": 1})

    @staticmethod
    def clean(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def num(value):
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

    def extract_product_objects(self, text):
        found = []
        marker = '"storeName":"Venex"'
        start = 0
        decoder = json.JSONDecoder()
        while True:
            pos = text.find(marker, start)
            if pos < 0:
                break
            brace = text.rfind("{", 0, pos)
            if brace >= 0:
                try:
                    obj, _ = decoder.raw_decode(text[brace:])
                    if isinstance(obj, dict) and obj.get("storeName") == "Venex":
                        found.append(obj)
                except Exception:
                    pass
            start = pos + len(marker)
        for key in ("highlightedProducts", "docs"):
            marker2 = f'"{key}":['
            pos = text.find(marker2)
            if pos >= 0:
                try:
                    arr, _ = decoder.raw_decode(text[pos + len(marker2) - 1:])
                    if isinstance(arr, list):
                        found.extend(x for x in arr if isinstance(x, dict))
                except Exception:
                    pass
        unique = {}
        for obj in found:
            pid = str(obj.get("_id") or obj.get("id") or obj.get("link") or "")
            if pid:
                unique[pid] = obj
        return list(unique.values())

    def normalize(self, doc):
        link = str(doc.get("link") or doc.get("url") or "").strip()
        if not link:
            return None
        p = urlparse(link)
        if p.netloc.lower().removeprefix("www.") != "venex.com.ar":
            return None
        clean_url = urlunparse(("https", "www.venex.com.ar", p.path, "", "", ""))
        name = self.clean(doc.get("name"))
        price = self.num(doc.get("price"))
        if not name or not price:
            return None
        image = doc.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if image:
            image = str(image)
            if image.startswith("/"):
                image = "https://www.venex.com.ar" + image
            elif not image.startswith(("http://", "https://")):
                image = "https://www.venex.com.ar/" + image.lstrip("/")
        available = bool(doc.get("availability", True)) and bool(doc.get("active", True))
        return {
            "tienda": "Venex", "nombre": name, "precio": price,
            "precio_anterior": self.num(doc.get("previousPrice")),
            "stock": 1 if available else 0, "imagen": image,
            "url": clean_url, "id_producto": str(doc.get("_id") or doc.get("id") or clean_url),
        }

    def parse_hg(self, response):
        page = int(response.meta["page"])
        self.pages_ok += 1
        docs = self.extract_product_objects(response.text)
        self.source_items += len(docs)
        new_count = 0
        for doc in docs:
            product = self.normalize(doc)
            if not product:
                continue
            self.raw_products.add(product["url"])
            key = product["id_producto"]
            if key in self.seen_products:
                continue
            self.seen_products.add(key)
            new_count += 1
            yield product
        text = self.clean(response.text)
        if self.expected_total is None:
            for pattern in (r'"(?:total|count|numFound)"\s*:\s*([0-9]+)', r"([0-9][0-9.]*)\s+resultados"):
                m = re.search(pattern, text, re.I)
                if m:
                    self.expected_total = int(re.sub(r"\D", "", m.group(1)))
                    break
        self.logger.info("VENEX via HARDGAMERS page=%d source=%d new=%d total=%d expected=%s", page, len(docs), new_count, len(self.seen_products), self.expected_total)
        if not docs or new_count == 0 or len(docs) < self.PAGE_SIZE or page >= self.MAX_PAGES:
            return
        next_url = self.hg_url(page + 1)
        if next_url in self.seen_pages:
            return
        self.seen_pages.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_hg, errback=self.errback_page, meta={"page": page + 1})

    def errback_page(self, failure):
        url = failure.request.url
        self.pages_failed.append(url)
        self.logger.warning("VENEX via HARDGAMERS failed: %s", url)

    def closed(self, reason):
        coverage = (len(self.raw_products) / self.expected_total) if self.expected_total else None
        print("=" * 70)
        print("VENEX CATALOG REPORT — HARDGAMERS SOURCE")
        print("=" * 70)
        print(f"reason={reason}")
        print(f"pages_ok={self.pages_ok}")
        print(f"pages_failed={len(self.pages_failed)}")
        print(f"source_items={self.source_items}")
        print(f"products_unique={len(self.seen_products)}")
        print(f"expected_total={self.expected_total}")
        print(f"coverage={coverage:.4f}" if coverage is not None else "coverage=n/a")
        for url in self.pages_failed[:20]:
            print(f"FAILED {url}")
        print("=" * 70)
