import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import json
import time


BASE = "https://quantumhardstore.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )
}


session = requests.Session()
session.headers.update(HEADERS)


def precio_desde_texto(texto):

    patrones = re.findall(
        r"\$\s*[\d\.]+(?:,\d+)?",
        texto
    )

    valores = []

    for patron in patrones:

        limpio = re.sub(
            r"[^\d,.]",
            "",
            patron
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

            valor = float(limpio)

            if valor >= 100:

                valores.append(
                    valor
                )

        except ValueError:
            continue


    if not valores:
        return None


    # En los listados de Quantum suele haber
    # precio contado + cuotas.
    # El menor valor positivo es el precio
    # de contado que queremos comparar.

    return round(
        min(valores)
    )


def buscar_tarjeta(anchor):

    actual = anchor

    for _ in range(8):

        actual = actual.parent

        if actual is None:
            break

        texto = actual.get_text(
            " ",
            strip=True
        )

        imagenes = actual.select(
            "img"
        )

        tiene_precio = "$" in texto
        tiene_imagen = bool(
            imagenes
        )

        if tiene_precio and tiene_imagen:

            return actual

    return None


def extraer_catalogo():

    productos = {}

    paginas_sin_productos = 0


    for pagina in range(
        1,
        60
    ):

        if pagina == 1:

            url = (
                f"{BASE}/productos/"
            )

        else:

            url = (
                f"{BASE}/productos/page/"
                f"{pagina}/"
            )


        print(
            f"Catálogo {pagina}: {url}"
        )


        try:

            r = session.get(
                url,
                timeout=30
            )

        except Exception as e:

            print(
                "  ERROR:",
                e
            )

            break


        if r.status_code == 429:

            print(
                "  ERROR 429: "
                "la tienda está limitando "
                "las solicitudes."
            )

            break


        if r.status_code != 200:

            print(
                "  STATUS:",
                r.status_code
            )

            break


        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )


        encontrados = 0


        for anchor in soup.select(
            "a[href]"
        ):

            href = anchor.get(
                "href"
            )

            if not href:
                continue


            ruta = urlparse(
                href
            ).path


            # Solo productos reales.
            if not re.match(
                r"^/productos/[^/]+/?$",
                ruta
            ):
                continue


            if ruta.rstrip(
                "/"
            ) == "/productos":
                continue


            producto_url = urljoin(
                BASE,
                ruta
            )


            # Ya visto en otra página.
            if producto_url in productos:
                continue


            # Buscar la tarjeta del producto.
            tarjeta = buscar_tarjeta(
                anchor
            )


            if tarjeta is None:
                continue


            # -----------------------------
            # NOMBRE
            # -----------------------------

            nombre = anchor.get_text(
                " ",
                strip=True
            )


            if not nombre:

                titulo = tarjeta.select_one(
                    "h1, h2, h3, h4, h5"
                )

                if titulo:

                    nombre = titulo.get_text(
                        " ",
                        strip=True
                    )


            if not nombre:
                continue


            if nombre.lower() == "productos":
                continue


            # -----------------------------
            # PRECIO
            # -----------------------------

            precio = precio_desde_texto(
                tarjeta.get_text(
                    " ",
                    strip=True
                )
            )


            if precio is None:
                continue


            # -----------------------------
            # IMAGEN
            # -----------------------------

            imagen = None


            for img in tarjeta.select(
                "img"
            ):

                src = (
                    img.get("src")
                    or
                    img.get("data-src")
                    or
                    img.get("data-lazy-src")
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

                    imagen = urljoin(
                        BASE,
                        src
                    )

                    break


            # -----------------------------
            # STOCK
            # -----------------------------

            texto = tarjeta.get_text(
                " ",
                strip=True
            ).lower()


            if (
                "agotado" in texto
                or
                "sin stock" in texto
            ):

                stock = 0

            else:

                stock = 1


            # -----------------------------
            # ID
            # -----------------------------

            id_producto = None

            match = re.search(
                r"/productos/[^/]+-([a-z0-9]+)/?$",
                producto_url,
                re.IGNORECASE
            )

            if match:

                id_producto = (
                    match.group(1)
                )


            productos[
                producto_url
            ] = {

                "tienda":
                    "Quantum Hardstore",

                "nombre":
                    nombre,

                "precio":
                    precio,

                "precio_anterior":
                    None,

                "stock":
                    stock,

                "imagen":
                    imagen,

                "url":
                    producto_url,

                "id_producto":
                    id_producto

            }


            encontrados += 1


        print(
            f"  Productos nuevos: "
            f"{encontrados}"
        )


        if encontrados == 0:

            paginas_sin_productos += 1

        else:

            paginas_sin_productos = 0


        # Si encontramos dos páginas
        # consecutivas sin productos,
        # dejamos de consultar.
        if paginas_sin_productos >= 2:

            break


        # No bombardear la tienda.
        time.sleep(1)


    return list(
        productos.values()
    )


print("=" * 70)
print("EXTRAYENDO QUANTUM DESDE LOS CATÁLOGOS")
print("=" * 70)


inicio = time.time()


productos = extraer_catalogo()


productos.sort(
    key=lambda x:
    x["nombre"].lower()
)


with open(
    "quantum.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        productos,
        f,
        ensure_ascii=False,
        indent=2
    )


print()
print("=" * 70)
print(
    "PRODUCTOS EXTRAÍDOS:",
    len(productos)
)

print(
    "CON IMAGEN:",
    sum(
        bool(x.get("imagen"))
        for x in productos
    )
)

print(
    "CON STOCK:",
    sum(
        x.get("stock", 0) > 0
        for x in productos
    )
)

print(
    "TIEMPO:",
    round(
        time.time() - inicio,
        1
    ),
    "segundos"
)

print("=" * 70)