import requests
from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urljoin


URL = "https://www.venex.com.ar/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


respuesta = requests.get(
    URL,
    headers=HEADERS,
    timeout=20
)

respuesta.raise_for_status()


soup = BeautifulSoup(
    respuesta.text,
    "html.parser"
)


productos = soup.select(
    ".item-prod-show .product-box"
)


print("Productos encontrados:", len(productos))


resultados = []


for producto in productos:

    enlace = producto.select_one(
        ".product-box-title a"
    )

    if not enlace:
        continue


    nombre = enlace.get_text(
        " ",
        strip=True
    )


    url_producto = enlace.get(
        "href"
    )


    precio_elemento = producto.select_one(
        ".current-price"
    )

    if not precio_elemento:
        continue


    precio_texto = precio_elemento.get_text(
        " ",
        strip=True
    )


    precio = re.sub(
        r"[^\d]",
        "",
        precio_texto
    )


    if not precio:
        continue


    precio = int(precio)


    precio_anterior_elemento = producto.select_one(
        ".product-box-old-price"
    )


    precio_anterior = None


    if precio_anterior_elemento:

        precio_anterior = re.sub(
            r"[^\d]",
            "",
            precio_anterior_elemento.get_text(
                " ",
                strip=True
            )
        )

        if precio_anterior:
            precio_anterior = int(
                precio_anterior
            )


    imagen_elemento = producto.select_one(
        ".product-box-media img"
    )


    imagen = None


    if imagen_elemento:

        imagen = (
            imagen_elemento.get("src")
            or imagen_elemento.get("data-src")
            or imagen_elemento.get("data-lazy-src")
        )

        if imagen:

            imagen = urljoin(
                URL,
                imagen
            )


    onclick = (
        enlace.get("onclick")
        or ""
    )


    id_producto = None


    match = re.search(
        r'"id":"([^"]+)"',
        onclick
    )


    if match:

        id_producto = match.group(1)


    resultados.append({

        "tienda": "Venex",

        "nombre": nombre,

        "precio": precio,

        "precio_anterior": precio_anterior,

        "stock": 1,

        "imagen": imagen,

        "url": urljoin(
            URL,
            url_producto
        ),

        "id_producto": id_producto,

    })


print()
print("Productos extraídos:", len(resultados))


for producto in resultados[:10]:

    print()
    print(json.dumps(
        producto,
        ensure_ascii=False,
        indent=2
    ))