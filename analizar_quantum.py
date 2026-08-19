import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://quantumhardstore.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )
}


r = requests.get(
    URL,
    headers=HEADERS,
    timeout=20
)

print("STATUS:", r.status_code)
print("HTML:", len(r.text))

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

print()
print("PLATAFORMA:")

html = r.text.lower()

for nombre in [
    "tiendanube",
    "acdn-us.mitiendanube.com",
    "mitiendanube",
]:

    print(
        nombre,
        ":",
        nombre in html
    )


print()
print("SCRIPTS:")

for script in soup.select("script[src]"):

    src = script.get("src")

    if src:
        print(
            urljoin(
                URL,
                src
            )
        )


print()
print("ENLACES DE PRODUCTOS:")

enlaces = []

for a in soup.select("a[href]"):

    href = a.get("href", "")
    texto = a.get_text(
        " ",
        strip=True
    )

    combinado = (
        href + " " + texto
    ).lower()

    if (
        "producto" in combinado
        or "/products/" in href.lower()
        or "/product/" in href.lower()
    ):

        enlace = urljoin(
            URL,
            href
        )

        if enlace not in enlaces:
            enlaces.append(enlace)


for enlace in enlaces[:50]:
    print(enlace)


print()
print(
    "TOTAL ENLACES POSIBLEMENTE DE PRODUCTOS:",
    len(enlaces)
)


print()
print("IMAGENES DE MITIENDANUBE:")

imagenes = re.findall(
    r'https://acdn-us\.mitiendanube\.com/[^"\']+',
    r.text
)

imagenes_unicas = []

for imagen in imagenes:

    if imagen not in imagenes_unicas:

        imagenes_unicas.append(
            imagen
        )


for imagen in imagenes_unicas[:20]:

    print(imagen)


print()
print(
    "TOTAL IMAGENES:",
    len(imagenes_unicas)
)


print()
print("SELECTORES CON POSIBLES PRODUCTOS:")

selectores = [
    ".product",
    ".product-item",
    ".product-card",
    ".js-item-product",
    ".item-product",
    ".product-grid-item",
    "[data-product-id]",
    "[data-product]",
]

for selector in selectores:

    print(
        selector,
        ":",
        len(soup.select(selector))
    )


print()
print("TEXTO CON PRECIOS:")

precios = []

for texto in soup.stripped_strings:

    if "$" in texto:

        precios.append(
            texto.strip()
        )


for precio in precios[:30]:

    print(precio)


print()
print(
    "TOTAL TEXTOS CON $:",
    len(precios)
)