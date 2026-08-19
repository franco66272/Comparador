import scrapy
import re


class VenexSpider(scrapy.Spider):

    name = "venex"

    allowed_domains = [
        "venex.com.ar",
        "www.venex.com.ar",
    ]

    start_urls = [
        "https://www.venex.com.ar/"
    ]

    def parse(self, response):

        productos = response.css(
            ".item-prod-show .product-box"
        )

        for producto in productos:

            enlace = producto.css(
                ".product-box-title a"
            )

            if not enlace:
                continue

            nombre = enlace.xpath(
                "string(.)"
            ).get()

            if not nombre:
                continue

            nombre = nombre.strip()

            url = enlace.attrib.get(
                "href"
            )

            precio_elemento = producto.css(
                ".current-price"
            )

            if not precio_elemento:
                continue

            precio_texto = precio_elemento.xpath(
                "string(.)"
            ).get()

            precio_limpio = re.sub(
                r"[^\d]",
                "",
                precio_texto or ""
            )

            if not precio_limpio:
                continue

            precio = int(
                precio_limpio
            )

            precio_anterior_elemento = producto.css(
                ".product-box-old-price"
            )

            precio_anterior = None

            if precio_anterior_elemento:

                texto = precio_anterior_elemento.xpath(
                    "string(.)"
                ).get()

                limpio = re.sub(
                    r"[^\d]",
                    "",
                    texto or ""
                )

                if limpio:
                    precio_anterior = int(
                        limpio
                    )

            imagen_elemento = producto.css(
                ".product-box-media img"
            )

            imagen = None

            if imagen_elemento:

                imagen = (
                    imagen_elemento.attrib.get("src")
                    or
                    imagen_elemento.attrib.get("data-src")
                    or
                    imagen_elemento.attrib.get("data-lazy-src")
                )

                if imagen:
                    imagen = response.urljoin(
                        imagen
                    )

            onclick = (
                enlace.attrib.get(
                    "onclick",
                    ""
                )
            )

            id_producto = None

            match = re.search(
                r'"id":"([^"]+)"',
                onclick
            )

            if match:
                id_producto = match.group(1)

            yield {
                "tienda": "Venex",
                "nombre": nombre,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "stock": 1,
                "imagen": imagen,
                "url": response.urljoin(url),
                "id_producto": id_producto,
            }