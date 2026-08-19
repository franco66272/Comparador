import scrapy
import re


class CompraGamerSpider(scrapy.Spider):

    name = "compragamer"

    allowed_domains = [
        "static.compragamer.com",
        "compragamer.com",
        "imagenes.compragamer.com",
    ]

    start_urls = [
        "https://static.compragamer.com/productos"
    ]

    def parse(self, response):

        productos = response.json()

        self.logger.info(
            f"Productos recibidos: {len(productos)}"
        )

        for producto in productos:

            nombre = producto.get(
                "nombre",
                ""
            )

            precio = (
                producto.get("precioEspecial")
                or producto.get("precioLista")
                or 0
            )

            stock = producto.get(
                "stock",
                0
            )

            producto_id = producto.get(
                "id_producto"
            )

            imagen = None

            imagenes = producto.get(
                "imagenes",
                []
            )

            if imagenes:

                primera = imagenes[0]

                if isinstance(
                    primera,
                    dict
                ):
                    nombre_imagen = primera.get(
                        "nombre"
                    )
                else:
                    nombre_imagen = primera

                if nombre_imagen:

                    imagen = (
                        "https://imagenes.compragamer.com/"
                        "productos/"
                        "compragamer_Imganen_general_"
                        f"{nombre_imagen}-grn.jpg"
                    )

            slug = re.sub(
                r"[^a-zA-Z0-9]+",
                "_",
                nombre
            ).strip("_")

            url = (
                "https://compragamer.com/producto/"
                f"{slug}_{producto_id}"
            )

            yield {
                "tienda": "CompraGamer",
                "nombre": nombre,
                "precio": precio,
                "precio_anterior": (
                    producto.get(
                        "precioEspecialAnterior"
                    )
                    or
                    producto.get(
                        "precioListaAnterior"
                    )
                ),
                "stock": stock,
                "imagen": imagen,
                "url": url,
                "id_producto": producto_id,
            }