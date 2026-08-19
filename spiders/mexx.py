import scrapy
import re


class MexxSpider(scrapy.Spider):

    name = "mexx"

    allowed_domains = [
        "mexx.com.ar",
        "www.mexx.com.ar",
        "mexx-img-2019.s3.amazonaws.com",
    ]

    start_urls = [
        "https://www.mexx.com.ar/"
    ]


    def parse(self, response):

        productos = response.css("div.card-ecommerce")


        for producto in productos:

            nombre_elemento = producto.css(
                ".card-title a"
            ).get()


            if not nombre_elemento:
                continue


            nombre = producto.css(
                ".card-title a::text"
            ).get()


            if not nombre:
                nombre = producto.css(
                    ".card-title a"
                ).xpath("string(.)").get()


            nombre = nombre.strip()


            url = producto.css(
                ".card-title a::attr(href)"
            ).get()


            imagen = producto.css(
                ".view img::attr(src)"
            ).get()


            precio_texto = producto.css(
                ".price b::text"
            ).get()


            if not precio_texto:
                continue


            precio_limpio = re.sub(
                r"[^\d]",
                "",
                precio_texto
            )


            if not precio_limpio:
                continue


            precio = int(precio_limpio)


            tiene_stock = producto.css(
                ".enstocklistado"
            ).get() is not None


            stock = 1 if tiene_stock else 0


            id_producto = None

            if url:

                match = re.search(
                    r"/(\d+)-[^/]+\.html",
                    url
                )

                if match:
                    id_producto = int(
                        match.group(1)
                    )


            if url and not url.startswith("http"):

                url = response.urljoin(url)


            if imagen and not imagen.startswith("http"):

                imagen = response.urljoin(imagen)


            yield {

                "tienda": "Mexx",

                "nombre": nombre,

                "precio": precio,

                "stock": stock,

                "imagen": imagen,

                "url": url,

                "id_producto": id_producto,

            }