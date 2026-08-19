import scrapy
import json
import re
from urllib.parse import urlparse


class QuantumSpider(scrapy.Spider):

    name = "quantum"

    allowed_domains = [
        "quantumhardstore.com"
    ]

    custom_settings = {
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
        "DOWNLOAD_DELAY": 0,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "ROBOTSTXT_OBEY": True,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    start_urls = [
        "https://quantumhardstore.com/productos/"
    ]


    def parse(self, response):

        enlaces = response.css(
            "a::attr(href)"
        ).getall()

        vistos = set()

        for href in enlaces:

            if not href:
                continue

            href = href.strip()

            try:
                ruta = urlparse(href).path
            except Exception:
                continue

            if ruta.rstrip("/") == "/productos":
                continue

            if re.match(
                r"^/productos/page/\d+/?$",
                ruta
            ):
                continue

            if not re.match(
                r"^/productos/[^/]+/?$",
                ruta
            ):
                continue

            url = response.urljoin(
                href.split("#")[0]
            )

            if url in vistos:
                continue

            vistos.add(url)

            yield scrapy.Request(
                url,
                callback=self.parse_producto
            )


        paginas = response.css(
            'a[href*="/productos/page/"]::attr(href)'
        ).getall()

        for href in paginas:

            url = response.urljoin(
                href
            )

            if url == response.url:
                continue

            yield scrapy.Request(
                url,
                callback=self.parse
            )


    def parse_producto(self, response):

        h1 = response.css("h1")

        if not h1:
            return

        nombre = h1.xpath(
            "string(.)"
        ).get()

        if not nombre:
            return

        nombre = nombre.strip()

        if nombre.lower() == "productos":
            return


        precio = None
        imagen = None


        # ==============================
        # JSON-LD
        # ==============================

        scripts = response.css(
            'script[type="application/ld+json"]::text'
        ).getall()

        for script in scripts:

            try:
                datos = json.loads(script)
            except Exception:
                continue

            elementos = (
                datos
                if isinstance(datos, list)
                else [datos]
            )

            for dato in elementos:

                if not isinstance(
                    dato,
                    dict
                ):
                    continue

                if dato.get("@type") != "Product":
                    continue


                img = dato.get(
                    "image"
                )

                if isinstance(
                    img,
                    list
                ):

                    if img:
                        imagen = img[0]

                elif isinstance(
                    img,
                    str
                ):

                    imagen = img


                ofertas = dato.get(
                    "offers"
                )

                if isinstance(
                    ofertas,
                    list
                ):

                    ofertas = (
                        ofertas[0]
                        if ofertas
                        else None
                    )

                if isinstance(
                    ofertas,
                    dict
                ):

                    valor = ofertas.get(
                        "price"
                    )

                    try:

                        if valor is not None:

                            candidato = float(
                                valor
                            )

                            if candidato > 0:

                                precio = candidato

                    except Exception:
                        pass


        # ==============================
        # FALLBACK PRECIO
        # ==============================

        if precio is None:

            valores = response.css(
                '[itemprop="price"]::attr(content), '
                '[itemprop="price"]::text'
            ).getall()

            for valor in valores:

                valor = valor.strip()

                limpio = re.sub(
                    r"[^\d,.]",
                    "",
                    valor
                )

                if not limpio:
                    continue

                try:

                    if "," in limpio:

                        limpio = (
                            limpio
                            .replace(".", "")
                            .replace(",", ".")
                        )

                    elif limpio.count(".") > 1:

                        limpio = limpio.replace(
                            ".",
                            ""
                        )

                    candidato = float(
                        limpio
                    )

                except ValueError:
                    continue

                if candidato >= 10000:

                    precio = candidato
                    break


        if precio is None:

            self.logger.warning(
                "SIN PRECIO: %s",
                response.url
            )

            return


        # ==============================
        # FALLBACK IMAGEN
        # ==============================

        if not imagen:

            for img in response.css(
                "img"
            ):

                src = (
                    img.attrib.get("src")
                    or
                    img.attrib.get("data-src")
                    or
                    img.attrib.get("data-lazy-src")
                )

                if not src:
                    continue

                if (
                    "mitiendanube.com"
                    in src
                    and
                    "/products/"
                    in src
                ):

                    imagen = response.urljoin(
                        src
                    )

                    break


        # ==============================
        # STOCK
        # ==============================

        texto = response.text.lower()

        if (
            "agotado" in texto
            or
            "sin stock" in texto
            or
            "no disponible" in texto
        ):

            stock = 0

        else:

            stock = 1


        # ==============================
        # ID
        # ==============================

        id_producto = None

        match = re.search(
            r"/productos/[^/]+-([a-z0-9]+)/?$",
            response.url,
            re.IGNORECASE
        )

        if match:

            id_producto = match.group(1)


        yield {

            "tienda":
                "Quantum Hardstore",

            "nombre":
                nombre,

            "precio":
                round(precio),

            "precio_anterior":
                None,

            "stock":
                stock,

            "imagen":
                imagen,

            "url":
                response.url,

            "id_producto":
                id_producto
        }