import scrapy


class PuertoMineroSpider(scrapy.Spider):

    name = "puertominero"

    allowed_domains = [
        "api.puertominero.com.ar"
    ]

    page_size = 100

    start_urls = [
        "https://api.puertominero.com.ar/products?pageSize=100&page=0&showInWeb=true&noStock=false"
    ]

    def parse(self, response):

        datos = response.json()

        entries = datos.get(
            "entries",
            []
        )

        pagination = datos.get(
            "pagination",
            {}
        )

        total = pagination.get(
            "total",
            0
        )

        pagina_actual = pagination.get(
            "page",
            0
        )

        self.logger.info(
            f"Productos recibidos: {len(entries)} / {total}"
        )

        for producto in entries:

            precio = (
                producto.get(
                    "price",
                    {}
                ).get(
                    "amount"
                )
            )

            if precio is None:
                continue

            imagenes = producto.get(
                "images",
                []
            )

            imagen = (
                imagenes[0]
                if imagenes
                else None
            )

            stock = (
                producto.get(
                    "stock",
                    {}
                ).get(
                    "quantity",
                    0
                )
            )

            url_name = producto.get(
                "urlName"
            )

            url_producto = None

            if url_name:

                url_producto = (
                    "https://www.puertominero.com.ar/"
                    "productos/"
                    f"{url_name}"
                )

            yield {
                "tienda": "Puerto Minero",
                "nombre": producto.get(
                    "name",
                    ""
                ),
                "precio": round(
                    float(precio)
                ),
                "precio_anterior": None,
                "stock": stock,
                "imagen": imagen,
                "url": url_producto,
                "id_producto": producto.get(
                    "id"
                ),
            }

        siguiente = pagina_actual + 1

        if siguiente * self.page_size < total:

            yield scrapy.Request(
                url=(
                    "https://api.puertominero.com.ar/products"
                    f"?pageSize={self.page_size}"
                    f"&page={siguiente}"
                    "&showInWeb=true"
                    "&noStock=false"
                ),
                callback=self.parse
            )