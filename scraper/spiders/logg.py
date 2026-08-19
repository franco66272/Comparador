import scrapy
import re
from urllib.parse import urljoin, urlparse, parse_qs


class LoggSpider(scrapy.Spider):

    name = "logg"

    allowed_domains = [
        "logg.com.ar"
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "ROBOTSTXT_OBEY": True,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    def start_requests(self):

        yield scrapy.Request(
            "https://logg.com.ar/Products/",
            callback=self.parse
        )

    def parse(self, response):

        cards = response.css(
            "a.product-card"
        )

        pagina = self.obtener_pagina(
            response.url
        )

        self.logger.info(
            "PÁGINA %s | PRODUCTOS: %s | URL: %s",
            pagina,
            len(cards),
            response.url
        )

        for card in cards:

            href = card.attrib.get(
                "href"
            )

            if not href:
                continue

            if "ProductDetail/" not in href:
                continue

            url = response.urljoin(
                href
            )

            nombre = card.css(
                ".card-text::text"
            ).get()

            if not nombre:
                continue

            nombre = nombre.strip()

            onclick = card.attrib.get(
                "onclick",
                ""
            )

            id_producto = None
            precio = None

            match = re.search(
                r"callGtagFunction\("
                r"'[^']*',"
                r"\s*'([^']*)',"
                r"\s*'[^']*',"
                r"\s*'[^']*',"
                r"\s*'[^']*',"
                r"\s*'[^']*',"
                r"\s*[^,]+,"
                r"\s*([0-9]+(?:\.[0-9]+)?),",
                onclick
            )

            if match:

                id_producto = match.group(1)

                try:
                    precio = round(
                        float(
                            match.group(2)
                        )
                    )
                except ValueError:
                    precio = None

            if not id_producto:
                id_producto = (
                    href
                    .rstrip("/")
                    .split("/")[-1]
                )

            if precio is None:
                continue

            imagen = card.css(
                ".card-img-top::attr(src)"
            ).get()

            if imagen:
                imagen = response.urljoin(
                    imagen
                )

            yield {
                "tienda": "Logg",
                "nombre": nombre,
                "precio": precio,
                "precio_anterior": None,
                "stock": 1,
                "imagen": imagen,
                "url": url,
                "id_producto": id_producto
            }

        # -----------------------------------------
        # BUSCAR SIGUIENTES PÁGINAS REALES
        # -----------------------------------------

        targets = []

        for button in response.css(
            "ul.pagination button[formaction]"
        ):

            formaction = button.attrib.get(
                "formaction"
            )

            if not formaction:
                continue

            if "handler=GoToPage" not in formaction:
                continue

            url = urljoin(
                response.url,
                formaction
            )

            if url not in targets:
                targets.append(url)

        # La página inicial suele mostrar 1,2,3...
        # Tomamos el siguiente número que todavía
        # no hayamos procesado.

        for url in targets:

            numero = self.obtener_pagina(
                url
            )

            if numero > pagina:

                token = response.css(
                    'input[name="__RequestVerificationToken"]::attr(value)'
                ).get()

                formdata = {
                    "HeaderCategory.Name": "Productos",
                    "FilterText": "",
                    "order": "3",
                    "PageSize": "100",
                    "ViewCardProductMode": "0",
                }

                if token:
                    formdata[
                        "__RequestVerificationToken"
                    ] = token

                yield scrapy.FormRequest(
                    url=url,
                    formdata=formdata,
                    callback=self.parse,
                    dont_filter=True
                )

                break

    @staticmethod
    def obtener_pagina(url):

        query = parse_qs(
            urlparse(url).query
        )

        if "pageNumber" in query:

            try:
                return int(
                    query["pageNumber"][0]
                )
            except ValueError:
                pass

        # Primera página
        return 1