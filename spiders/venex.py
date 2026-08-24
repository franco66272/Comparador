import json
import re
from urllib.parse import urlparse, parse_qs

import scrapy


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]

    custom_settings = {
        "DEPTH_LIMIT": 12,
        "CLOSESPIDER_PAGECOUNT": 2500,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY": 0.15,
        "DOWNLOAD_TIMEOUT": 20,
    }

    # Venex exposes a real internal search/listing endpoint. We use it as an
    # index instead of relying on the homepage to link every catalog page.
    SEARCH_URL = "https://www.venex.com.ar/resultado-busqueda.htm"
    PAGE_SIZE = 96

    # Broad seed terms. They are discovery seeds, not product filters: every
    # result page is parsed and deduplicated, including generic/other products.
    SEARCH_SEEDS = [
        "notebook", "procesador", "microprocesador", "placa de video", "memoria ram",
        "ssd", "disco", "monitor", "motherboard", "gabinete", "fuente", "cooler",
        "teclado", "mouse", "auricular", "joystick", "webcam", "microfono", "router",
        "wifi", "impresora", "tablet", "silla gamer", "pc gamer", "consola", "playstation",
        "xbox", "nintendo", "celular", "smartwatch", "audio", "cable", "adaptador",
        "parlante", "ups", "nas", "camara", "streaming", "accesorio", "gaming",
    ]

    BLOCKED_PATHS = (
        "/entrar", "/login", "/registr", "/contact", "/corporativo", "/envio",
        "/politica", "/terminos", "/carrito", "/checkout", "/landing", "/create_account",
    )

    def start_requests(self):
        # Always seed the real search endpoint instead of only the homepage.
        for term in self.SEARCH_SEEDS:
            yield scrapy.Request(
                self._search_url(term, 1),
                callback=self.parse,
                dont_filter=True,
                meta={"search_seed": term, "search_page": 1},
            )

        # Also seed the public result pages used by Venex itself for broad
        # category/search views. These catch products that do not match our
        # initial terms exactly.
        yield scrapy.Request(
            f"{self.SEARCH_URL}?keywords=y&limit={self.PAGE_SIZE}&page=1",
            callback=self.parse,
            dont_filter=True,
            meta={"search_seed": "__broad__", "search_page": 1},
        )

    def _search_url(self, term, page=1):
        # The endpoint accepts keywords + limit + page. Keep encoding in the
        # URL so Scrapy handles redirects/canonicalization consistently.
        from urllib.parse import urlencode
        params = {"keywords": term, "limit": self.PAGE_SIZE, "page": page}
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _same_store(self, url):
        try:
            return urlparse(url).netloc.lower().lstrip("www.") == "venex.com.ar"
        except Exception:
            return False

    def _is_product(self, url):
        if not url:
            return False
        path = urlparse(url).path.lower()
        return path.endswith(".html") or any(x in path for x in ("/producto/", "/product/", "/productos/"))

    def _is_blocked(self, url):
        path = urlparse(url).path.lower()
        return any(x in path for x in self.BLOCKED_PATHS)

    def _clean_int(self, value):
        txt = re.sub(r"[^\d]", "", str(value or ""))
        if not txt:
            return None
        n = int(txt)
        return n if n >= 100 else None

    def _image(self, img, response):
        if not img:
            return None
        value = (
            img.attrib.get("data-zoom-image")
            or img.attrib.get("data-large-image")
            or img.attrib.get("data-original")
            or img.attrib.get("data-lazy-src")
            or img.attrib.get("data-src")
            or img.attrib.get("src")
        )
        return response.urljoin(value) if value else None

    def _extract_card(self, card, response):
        link = (
            card.css(".product-box-title a")
            or card.css(".product-title a")
            or card.css(".product-name a")
            or card.css("h2 a")
            or card.css("h3 a")
            or card.css("a[href]")
        )
        if not link:
            return None

        href = link.attrib.get("href")
        if not href:
            return None
        url = response.urljoin(href)
        if not self._same_store(url) or not self._is_product(url) or self._is_blocked(url):
            return None

        name = link.xpath("string(.)").get() or link.attrib.get("title") or ""
        name = name.strip()
        if len(name) < 3:
            return None

        price_node = card.css(
            ".current-price, .product-box-price, .price, [itemprop=price], [data-price], .special-price"
        )
        price = self._clean_int(price_node.xpath("string(.)").get() if price_node else None)
        if not price:
            # Search card text as a final fallback.
            price = self._clean_int(re.search(r"\$\s*[\d.]+", card.xpath("string(.)").get() or "").group(0) if re.search(r"\$\s*[\d.]+", card.xpath("string(.)").get() or "") else None)
        if not price:
            return None

        old_node = card.css(".product-box-old-price, .old-price")
        old_price = self._clean_int(old_node.xpath("string(.)").get() if old_node else None)

        onclick = link.attrib.get("onclick", "")
        match = re.search(r'"id":"([^"]+)"', onclick)
        product_id = match.group(1) if match else None
        if not product_id:
            sku = card.css("[itemprop=sku]::attr(content), .sku::text").get()
            product_id = (sku or url).strip()

        return {
            "tienda": "Venex",
            "nombre": name,
            "precio": price,
            "precio_anterior": old_price,
            "stock": 1,
            "imagen": self._image(card.css("img").get() and card.css("img")[0], response),
            "url": url,
            "id_producto": product_id,
        }

    def _extract_cards(self, response):
        selectors = (
            ".item-prod-show .product-box",
            ".product-box",
            ".product-item",
            ".product-card",
            "article.product",
            "[itemtype*='Product']",
        )
        best = []
        for selector in selectors:
            cards = response.css(selector)
            if len(cards) > len(best):
                best = cards

        for card in best:
            product = self._extract_card(card, response)
            if product:
                yield product

    def _extract_jsonld_products(self, response):
        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
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
                        price = self._clean_int(offers.get("price") if isinstance(offers, dict) else None)
                        name = str(obj.get("name") or "").strip()
                        if name and price:
                            image = obj.get("image")
                            if isinstance(image, list):
                                image = image[0] if image else None
                            yield {
                                "tienda": "Venex",
                                "nombre": name,
                                "precio": price,
                                "precio_anterior": None,
                                "stock": 0 if "outofstock" in str((offers or {}).get("availability", "")).lower() else 1,
                                "imagen": response.urljoin(image) if isinstance(image, str) else None,
                                "url": response.url,
                                "id_producto": str(obj.get("sku") or response.url),
                            }
                    for value in obj.values():
                        if isinstance(value, (dict, list)):
                            stack.append(value)
                elif isinstance(obj, list):
                    stack.extend(obj)

    def _listing_total_pages(self, response):
        # Prefer explicit pagination links / data-total-pages when present.
        candidates = []
        for attr in (
            "data-total-pages", "data-pages", "data-totalpages",
        ):
            value = response.css(f"[{attr}]::attr({attr})").get()
            if value and value.isdigit():
                candidates.append(int(value))
        for href in response.css("a[href]").xpath("@href").getall():
            if "page=" not in href.lower() and "pagina=" not in href.lower():
                continue
            qs = parse_qs(urlparse(response.urljoin(href)).query)
            for key in ("page", "pagina"):
                if key in qs:
                    try:
                        candidates.append(int(qs[key][0]))
                    except Exception:
                        pass
        # If no page count is exposed, infer from pagination controls by taking
        # the highest numeric page we can see.
        for text in response.css(".pagination a::text, .pager a::text").getall():
            if str(text).strip().isdigit():
                candidates.append(int(str(text).strip()))
        return max(candidates) if candidates else None

    def _follow_listing_pagination(self, response):
        seen = set()
        # Explicit next link first.
        for href in response.css('a[rel="next"]::attr(href), a.next::attr(href)').getall():
            url = response.urljoin(href)
            if url not in seen and self._same_store(url):
                seen.add(url)
                yield scrapy.Request(url, callback=self.parse, meta={"from_pagination": True})

        current_page = 1
        for key in ("page", "pagina"):
            values = parse_qs(urlparse(response.url).query).get(key)
            if values:
                try:
                    current_page = int(values[0])
                except Exception:
                    pass
                break

        total = self._listing_total_pages(response)
        if total and total <= 100:
            # Hard cap avoids infinite pagination loops.
            for page in range(current_page + 1, total + 1):
                url = response.url
                from urllib.parse import parse_qsl, urlencode, urlunparse
                parsed = urlparse(url)
                qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
                qs["page"] = str(page)
                next_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs), parsed.fragment))
                if next_url not in seen:
                    seen.add(next_url)
                    yield scrapy.Request(next_url, callback=self.parse, meta={"from_pagination": True})
        else:
            # Generic search/listing fallback: advance pages until a page has no
            # products. This is useful when the site does not expose total pages.
            next_page = current_page + 1
            url = self._search_url(response.meta.get("search_seed", ""), next_page) if response.meta.get("search_seed") else None
            if url and url not in seen:
                seen.add(url)
                yield scrapy.Request(url, callback=self.parse, meta={"search_seed": response.meta.get("search_seed", ""), "search_page": next_page})

    def parse(self, response):
        # Always extract what is directly visible on the listing page.
        yielded = 0
        seen_urls = set()
        for product in self._extract_cards(response):
            if product["url"] in seen_urls:
                continue
            seen_urls.add(product["url"])
            yielded += 1
            yield product

        # JSON-LD gives additional products on some catalog pages.
        if yielded == 0:
            for product in self._extract_jsonld_products(response):
                yield product

        # Follow internal listing pagination from this exact listing URL.
        yield from self._follow_listing_pagination(response)

        # Discover other category/listing/search links from the current page.
        if response.meta.get("search_seed") in (None, "__broad__"):
            seen = set()
            for a in response.css("a[href]"):
                href = a.attrib.get("href")
                if not href:
                    continue
                url = response.urljoin(href)
                if not self._same_store(url) or url in seen or self._is_blocked(url):
                    continue
                if self._is_product(url):
                    # Do not request every product individually here; listing
                    # pages already contain the structured product data.
                    continue
                seen.add(url)
                text = (a.xpath("string(.)").get() or "").strip().lower()
                path = urlparse(url).path.lower()
                query = urlparse(url).query.lower()
                looks_like_listing = (
                    any(k in path for k in ("/notebook", "/component", "/perifer", "/memoria", "/monitor", "/disco", "/placa", "/pc-de-escritorio", "/gaming", "/audio", "/impres", "/table", "/silla", "/almacen", "/conect", "/acces"))
                    or any(k in text for k in ("notebook", "procesador", "memoria", "placa", "monitor", "almacenamiento", "periferico", "gabinete", "fuente", "gaming"))
                    or any(k in query for k in ("page=", "pagina=", "vmm=", "man=", "opt=", "cat=", "sort="))
                )
                if looks_like_listing:
                    yield scrapy.Request(url, callback=self.parse, meta={"category_seed": text[:80]})
