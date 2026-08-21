import scrapy
import re
from urllib.parse import urljoin, urlparse


class VenexSpider(scrapy.Spider):
    name = "venex"
    allowed_domains = ["venex.com.ar", "www.venex.com.ar"]
    start_urls = ["https://www.venex.com.ar/"]
    custom_settings = {
        "DEPTH_LIMIT": 4,
        "CLOSESPIDER_PAGECOUNT": 1500,
    }

    def _es_producto(self, href):
        return bool(href and ".html" in href.lower())

    def _es_lista(self, href):
        if not href:
            return False
        parsed = urlparse(href)
        if parsed.netloc not in {"venex.com.ar", "www.venex.com.ar"}:
            return False
        if self._es_producto(href):
            return False
        path = parsed.path.lower()
        return path in {"", "/", "/index.php", "/index.html"} or any(
            segmento in path
            for segmento in (
                "/notebooks", "/microprocesadores", "/placas-de-video",
                "/placas-video", "/memorias-ram", "/almacenamiento",
                "/discos", "/monitores", "/perifericos", "/gabinetes",
                "/fuentes", "/motherboards", "/componentes", "/pc-de-escritorio",
                "/conectividad", "/audio", "/impresoras", "/telefonia",
                "/tablets", "/gaming", "/accesorios", "/hogar-y-oficina",
            )
        ) or "page=" in parsed.query or "pagina=" in parsed.query

    def parse(self, response):
        productos = response.css(".item-prod-show .product-box")

        for producto in productos:
            enlace = producto.css(".product-box-title a")
            if not enlace:
                continue

            nombre = enlace.xpath("string(.)").get()
            if not nombre:
                continue
            nombre = nombre.strip()

            url = enlace.attrib.get("href")
            if not url:
                continue

            precio_elemento = producto.css(".current-price")
            if not precio_elemento:
                continue
            precio_texto = precio_elemento.xpath("string(.)").get()
            precio_limpio = re.sub(r"[^\d]", "", precio_texto or "")
            if not precio_limpio:
                continue
            precio = int(precio_limpio)

            precio_anterior_elemento = producto.css(".product-box-old-price")
            precio_anterior = None
            if precio_anterior_elemento:
                texto = precio_anterior_elemento.xpath("string(.)").get()
                limpio = re.sub(r"[^\d]", "", texto or "")
                if limpio:
                    precio_anterior = int(limpio)

            imagen_elemento = producto.css(".product-box-media img")
            imagen = None
            if imagen_elemento:
                imagen = (
                    imagen_elemento.attrib.get("src")
                    or imagen_elemento.attrib.get("data-src")
                    or imagen_elemento.attrib.get("data-lazy-src")
                )
                if imagen:
                    imagen = response.urljoin(imagen)

            onclick = enlace.attrib.get("onclick", "")
            id_producto = None
            match = re.search(r'"id":"([^"]+)"', onclick)
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

        candidatos = response.css("a::attr(href)").getall()
        vistos = set()
        for href in candidatos:
            url = response.urljoin(href)
            if url in vistos or url == response.url:
                continue
            vistos.add(url)
            parsed = urlparse(url)
            if parsed.netloc not in {"venex.com.ar", "www.venex.com.ar"}:
                continue
            if self._es_producto(url):
                continue
            if self._es_lista(url):
                yield response.follow(url, callback=self.parse)
