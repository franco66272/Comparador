import requests
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )
}


def descargar(url):

    try:
        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        respuesta.raise_for_status()

        return respuesta.text

    except Exception as e:

        print(f"ERROR descargando {url}")
        print(e)

        return None


def limpiar_precio(texto):

    if texto is None:
        return None

    numeros = re.sub(
        r"[^\d]",
        "",
        str(texto)
    )

    if not numeros:
        return None

    return int(numeros)


def buscar_json_ld(soup):

    resultados = []

    scripts = soup.select(
        'script[type="application/ld+json"]'
    )

    for script in scripts:

        texto = script.string

        if not texto:
            continue

        try:
            datos = json.loads(texto)

        except Exception:
            continue

        if isinstance(datos, dict):

            if "@graph" in datos:
                elementos = datos["@graph"]

            else:
                elementos = [datos]

        elif isinstance(datos, list):

            elementos = datos

        else:

            continue


        for producto in elementos:

            if not isinstance(producto, dict):
                continue


            tipo = producto.get("@type")

            if isinstance(tipo, list):

                es_producto = (
                    "Product" in tipo
                )

            else:

                es_producto = (
                    tipo == "Product"
                )


            if not es_producto:
                continue


            nombre = producto.get("name")
            url = producto.get("url")
            imagen = producto.get("image")
            ofertas = producto.get("offers")


            if isinstance(imagen, list):

                imagen = (
                    imagen[0]
                    if imagen
                    else None
                )


            precio = None
            stock = 0


            if isinstance(ofertas, list):

                ofertas = (
                    ofertas[0]
                    if ofertas
                    else None
                )


            if isinstance(ofertas, dict):

                precio = (
                    ofertas.get("price")
                    or ofertas.get("lowPrice")
                    or ofertas.get("highPrice")
                )

                disponibilidad = str(
                    ofertas.get(
                        "availability",
                        ""
                    )
                )


                if "InStock" in disponibilidad:

                    stock = 1


            if nombre and precio:

                try:
                    precio = float(precio)

                except Exception:
                    continue


                resultados.append({

                    "nombre": nombre,

                    "precio": int(precio),

                    "stock": stock,

                    "imagen": imagen,

                    "url": url,

                })


    return resultados


def buscar_html_generico(soup, base_url):

    resultados = []

    posibles = soup.select(
        ".product, "
        ".product-item, "
        ".product-card, "
        ".product-box, "
        ".card-product, "
        ".card-ecommerce, "
        "article"
    )


    vistos = set()


    for elemento in posibles:

        nombre = None


        for selector in [
            ".product-name",
            ".product-title",
            ".card-title",
            ".name",
            "h2",
            "h3",
            "h4"
        ]:

            encontrado = elemento.select_one(
                selector
            )

            if encontrado:

                nombre = encontrado.get_text(
                    " ",
                    strip=True
                )

                if nombre:
                    break


        if not nombre:
            continue


        precio = None


        for selector in [
            ".price",
            ".precio",
            ".product-price",
            ".price-final",
            ".special-price",
            ".sale-price"
        ]:

            encontrado = elemento.select_one(
                selector
            )

            if encontrado:

                precio = limpiar_precio(
                    encontrado.get_text(
                        " ",
                        strip=True
                    )
                )

                if precio:
                    break


        if not precio:
            continue


        enlace = elemento.select_one(
            "a[href]"
        )


        url = None

        if enlace:

            url = urljoin(
                base_url,
                enlace.get("href")
            )


        imagen = None

        imagen_elemento = elemento.select_one(
            "img"
        )


        if imagen_elemento:

            imagen = (
                imagen_elemento.get("src")
                or imagen_elemento.get(
                    "data-src"
                )
                or imagen_elemento.get(
                    "data-lazy-src"
                )
            )


            if imagen:

                imagen = urljoin(
                    base_url,
                    imagen
                )


        texto = elemento.get_text(
            " ",
            strip=True
        ).lower()


        stock = 0

        for palabra in [
            "en stock",
            "stock disponible",
            "disponible",
            "hay stock",
            "últimas unidades",
            "ultimas unidades"
        ]:

            if palabra in texto:

                stock = 1
                break


        clave = (
            nombre.lower(),
            precio
        )


        if clave in vistos:
            continue


        vistos.add(clave)


        resultados.append({

            "nombre": nombre,

            "precio": precio,

            "stock": stock,

            "imagen": imagen,

            "url": url,

        })


    return resultados


def analizar_tienda(tienda):

    nombre_tienda = tienda["nombre"]
    url = tienda["url"]


    print()
    print("=" * 60)
    print(nombre_tienda)
    print(url)
    print("=" * 60)


    html = descargar(url)


    if not html:

        return []


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    productos = buscar_json_ld(soup)


    if productos:

        metodo = "JSON-LD"

    else:

        productos = buscar_html_generico(
            soup,
            url
        )

        metodo = "HTML"


    print(
        f"Encontrados mediante {metodo}: "
        f"{len(productos)}"
    )


    for producto in productos:

        producto["tienda"] = (
            nombre_tienda
        )


        if producto.get("url"):

            producto["url"] = urljoin(
                url,
                producto["url"]
            )


        if producto.get("imagen"):

            producto["imagen"] = urljoin(
                url,
                producto["imagen"]
            )


    return productos


def main():

    with open(
        "tiendas.json",
        "r",
        encoding="utf-8"
    ) as archivo:

        tiendas = json.load(
            archivo
        )


    todos = []


    for tienda in tiendas:

        productos = analizar_tienda(
            tienda
        )

        todos.extend(
            productos
        )


    with open(
        "productos_todas_tiendas.json",
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            todos,
            archivo,
            ensure_ascii=False,
            indent=2
        )


    print()
    print("=" * 60)
    print(
        f"TOTAL PRODUCTOS: {len(todos)}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()