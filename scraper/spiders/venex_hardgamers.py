import html
import json
import re
from urllib.parse import urlencode, urlparse, urlunparse

import scrapy


class VenexHardGamersSpider(scrapy.Spider):
    name = "venex_hardgamers"
    allowed_domains = ["hardgamers.com.ar", "www.hardgamers.com.ar"]
    HG_BASE = "https://www.hardgamers.com.ar"
    HG_STORE = "/stores/venex"
    PAGE_SIZE = 24
    MAX_PAGES = 200

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 0.1,
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
        self.expected_pages = None

    def hg_url(self, page):
        query = {"brand": "", "limit": str(self.PAGE_SIZE), "page": str(page), "province": "", "store": "venex"}
        return f"{self.HG_BASE}{self.HG_STORE}?{urlencode(query)}"

    async def start(self):
        url = self.hg_url(1)
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
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "." in s or "," in s:
            s = s.replace(".", "").replace(",", "")
        try:
            n = int(float(s))
        except ValueError:
            return None
        return n if n >= 1000 else None

    def _looks_like_product(self, obj):
        if not isinstance(obj, dict):
            return False
        link = obj.get("link") or obj.get("url")
        return isinstance(link, str) and "venex.com.ar/" in link.lower() and bool(obj.get("name")) and obj.get("price") is not None

    def _walk(self, value, docs, metadata):
        if isinstance(value, dict):
            if self._looks_like_product(value):
                docs.append(value)
            for key, child in value.items():
                if key == "total" and isinstance(child, (int, float)):
                    metadata.setdefault("total", int(child))
                elif key == "pages" and isinstance(child, int):
                    metadata.setdefault("pages", child)
                if isinstance(child, (dict, list)):
                    self._walk(child, docs, metadata)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)):
                    self._walk(child, docs, metadata)

    def _decode_embedded(self, text):
        """Decode embedded JSON objects without assuming a specific framework."""
        variants = [text, html.unescape(text), text.replace('\\"', '"')]
        seen = set()
        decoder = json.JSONDecoder()
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            for match in re.finditer(r"[\[{]", variant):
                try:
                    obj, _ = decoder.raw_decode(variant[match.start():])
                except (ValueError, json.JSONDecodeError):
                    continue
                yield obj

    def extract_catalog(self, text):
        docs = []
        metadata = {}
        for root in self._decode_embedded(text):
            self._walk(root, docs, metadata)

        # Last-resort extraction for HTML containing escaped product links.
        if not docs:
            decoded = html.unescape(text).replace('\\"', '"')
            for match in re.finditer(r'"link"\s*:\s*"(https?://(?:www\.)?venex\.com\.ar/[^"\\]+)"', decoded, re.I):
                start = decoded.rfind("{", 0, match.start())
                if start < 0:
                    continue
                try:
                    obj, _ = json.JSONDecoder().raw_decode(decoded[start:])
                except (ValueError, json.JSONDecodeError):
                    continue
                if self._looks_like_product(obj):
                    docs.append(obj)

        unique = {}
        for doc in docs:
            pid = str(doc.get("_id") or doc.get("id") or doc.get("link") or doc.get("url") or "")
            if pid:
                unique[pid] = doc

        if "total" not in metadata:
            m = re.search(r'"total"\s*:\s*(\d+)', text)
            if m:
                metadata["total"] = int(m.group(1))
        if "pages" not in metadata:
            m = re.search(r'"pages"\s*:\s*(\d+)', text)
            if m:
                metadata["pages"] = int(m.group(1))

        return list(unique.values()), metadata.get("total"), metadata.get("pages")

    def normalize(self, doc):
        link = str(doc.get("link") or doc.get("url") or "").strip()
        p = urlparse(link)
        if p.netloc.lower().removeprefix("www.") != "venex.com.ar":
            return None
        name = self.clean(doc.get("name"))
        price = self.num(doc.get("price"))
        if not name or not price:
            return None
        clean_url = urlunparse(("https", "www.venex.com.ar", p.path, "", "", ""))
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
            "url": clean_url,
            "id_producto": str(doc.get("_id") or doc.get("id") or clean_url),
        }

    def parse_hg(self, response):
        page = int(response.meta["page"])
        docs, total, pages = self.extract_catalog(response.text)
        self.pages_ok += 1
        self.source_items += len(docs)
        if total is not None:
            self.expected_total = total
        if pages is not None:
            self.expected_pages = pages

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

        self.logger.info("VENEX via HARDGAMERS page=%d source=%d new=%d total=%d expected_total=%s expected_pages=%s", page, len(docs), new_count, len(self.seen_products), self.expected_total, self.expected_pages)

        if not docs or page >= self.MAX_PAGES:
            return
        if self.expected_pages is not None and page >= self.expected_pages:
            return
        if self.expected_pages is None and len(docs) < self.PAGE_SIZE:
            return

        next_url = self.hg_url(page + 1)
        if next_url in self.seen_pages:
            return
        self.seen_pages.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_hg, errback=self.errback_page, meta={"page": page + 1})

    def errback_page(self, failure):
        self.pages_failed.append(failure.request.url)
        self.logger.warning("VENEX via HARDGAMERS failed: %s", failure.request.url)

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
        print(f"expected_pages={self.expected_pages}")
        print(f"coverage={coverage:.4f}" if coverage is not None else "coverage=n/a")
        for url in self.pages_failed[:20]:
            print(f"FAILED {url}")
        print("=" * 70)
