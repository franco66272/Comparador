import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy


class VenexHardGamersSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["hardgamers.com.ar", "www.hardgamers.com.ar", "venex.com.ar", "www.venex.com.ar"]

    HG_BASE = "https://www.hardgamers.com.ar"
    HG_STORE = "/stores/venex"
    PAGE_SIZE = 100
    MAX_PAGES = 200

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.10,
        "DOWNLOAD_TIMEOUT": 30,
        "RETRY_TIMES": 2,
        "LOG_LEVEL": "INFO",
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.2,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "CLOSESPIDER_ERRORCOUNT": 25,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_hg_pages = set()
        self.seen_products = set()
        self.raw_products = set()
        self.source_items = 0
        self.pages_ok = 0
        self.pages_failed = []
        self.expected_total = None

    def start_requests(self):
        yield scrapy.Request(
            self.hg_url(1),
            callback=self.parse_hg,
            errback=self.errback_page,
            meta={"page": 1},
        )

    def hg_url(self, page):
        query = {"brand": "", "limit": str(self.PAGE_SIZE), "page": str(page), "store": "venex"}
        return f"{self.HG_BASE}{self.HG_STORE}?{urlencode(query)}"

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

    def parse_embedded_docs(self, response):
        # HardGamers currently embeds the store result set as JSON in the page.
        # Prefer this structured payload because it already contains the Venex
        # canonical product link, price and availability without scraping the
        # visual card layout.
        text = response.text
        docs = []
        patterns = [
            r'"docs"\s*:\s*(\[[\s\S]*?\])\s*,\s*"(?:total|count|page|limit)"',
            r'"docs"\s*:\s*(\[[\s\S]*?\])\s*\}',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                candidate = match.group(1)
                try:
                    data = json.loads(candidate)
                except Exception:
                    continue
                if isinstance(data, list):
                    docs.extend(x for x in data if isinstance(x, dict))
                    if docs:
                        return docs
        return docs

    def parse_cards(self, response):
        # Fallback for the rendered/standard HTML representation.
        docs = []
        for card in response.css("article, .product-card, .card-product, .product-item"):
            link = card.css("a[href*='venex.com.ar']::attr(href), a[href$='.html']::attr(href)").get()
            if not link:
                continue
            name = self.clean(card.css("h2::text, h3::text, h4::text, .name::text, .title::text").get())
            price = self.num(card.css(".price::text, [class*='price']::text").get())
            if not link or not name or not price:
                continue
            docs.append({"name": name, "price": price, "availability": True, "link": response.urljoin(link)})
        return docs

    def normalize_doc(self, doc):
        link = str(doc.get("link") or doc.get("url") or "").strip()
        if not link:
            return None
        parsed = urlparse(link)
        if parsed.netloc.lower().removeprefix("www.") != "venex.com.ar":
            return None
        clean_url = urlunparse(("https", "www.venex.com.ar", parsed.path, "", "", ""))
        name = self.clean(doc.get("name"))
        price = self.num(doc.get("price"))
        if not name or not price:
            return None
        image = doc.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if image:
            image = response_urljoin = urlparse(str(image))
            if not response_urljoin.scheme:
                image = "https://www.venex.com.ar" + (str(doc.get("image")) if str(doc.get("image")).startswith("/") else "/" + str(doc.get("image")))
            else:
                image = image.geturl()
        availability = bool(doc.get("availability", True))
        product_id = str(doc.get("_id") or doc.get("id") or clean_url)
        return {
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": None,
            "stock": 1 if availability and bool(doc.get("active", True)) else 0,
            "imagen": image,
            "url": clean_url,
            "id_producto": product_id,
        }

    def parse_hg(self, response):
        page = int(response.meta.get("page", 1))
        self.pages_ok += 1

        docs = self.parse_embedded_docs(response)
        if not docs:
            docs = self.parse_cards(response)

        self.source_items += len(docs)
        new_items = 0
        for doc in docs:
            product = self.normalize_doc(doc)
            if not product:
                continue
            self.raw_products.add(product["url"])
            key = product["id_producto"] or product["url"]
            if key in self.seen_products:
                continue
            self.seen_products.add(key)
            new_items += 1
            yield product

        text = self.clean(response.text)
        if self.expected_total is None:
            for pattern in (r"([0-9][0-9.]*)\s+resultados", r'"(?:total|count)"\s*:\s*([0-9]+)'):
                match = re.search(pattern, text, re.I)
                if match:
                    self.expected_total = self.num(match.group(1)) or int(re.sub(r"\D", "", match.group(1)))
                    break

        self.logger.info(
            "VENEX via HARDGAMERS page=%d source=%d new=%d total=%d expected=%s",
            page, len(docs), new_items, len(self.seen_products), self.expected_total,
        )

        # Continue while the source page supplies a full page. HardGamers has a
        # finite result set for this store, avoiding any Venex navigation crawl.
        if page >= self.MAX_PAGES or len(docs) < self.PAGE_SIZE:
            return
        next_page = page + 1
        next_url = self.hg_url(next_page)
        if next_url in self.seen_hg_pages:
            return
        self.seen_hg_pages.add(next_url)
        yield scrapy.Request(next_url, callback=self.parse_hg, errback=self.errback_page,
                             meta={"page": next_page})

    def errback_page(self, failure):
        url = failure.request.url
        self.pages_failed.append(url)
        self.logger.warning("VENEX via HARDGAMERS failed: %s", url)

    def closed(self, reason):
        coverage = None
        if self.expected_total:
            coverage = len(self.raw_products) / self.expected_total
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
        if self.pages_failed:
            print("failed_pages=")
            for url in self.pages_failed[:20]:
                print(f"  {url}")
        print("=" * 70)
