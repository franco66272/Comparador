import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

URL = "https://logg.com.ar/"

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
    timeout=30
)

print("STATUS:", r.status_code)
print("HTML:", len(r.text))

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

print()
print("TITLE:")
print(
    soup.title.get_text(strip=True)
    if soup.title
    else "SIN TITLE"
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
print("ENLACES RELEVANTES:")

vistos = set()

for a in soup.select("a[href]"):

    href = a.get("href", "")
    texto = a.get_text(
        " ",
        strip=True
    )

    combinado = (
        href + " " + texto
    ).lower()

    if any(
        palabra in combinado
        for palabra in [
            "producto",
            "productos",
            "catalogo",
            "categor",
            "tienda",
            "shop",
            "buscar",
            "search"
        ]
    ):

        url = urljoin(
            URL,
            href
        )

        if url not in vistos:

            vistos.add(url)

            print(
                "TEXTO:",
                texto,
                "| URL:",
                url
            )

print()
print("TEXTOS CON PRECIO:")

precios = []

for texto in soup.stripped_strings:

    texto = texto.strip()

    if "$" in texto:
        precios.append(texto)

for precio in precios[:50]:
    print(precio)

print()
print(
    "TOTAL TEXTOS CON $:",
    len(precios)
)

print()
print("PALABRAS CLAVE EN HTML:")

html = r.text.lower()

for palabra in [
    "api",
    "ajax",
    "fetch",
    "axios",
    "graphql",
    "product",
    "productos",
    "json",
    "prestashop",
    "woocommerce",
    "shopify",
    "magento",
    "vtex",
    "tiendanube"
]:

    print(
        palabra,
        ":",
        html.find(palabra)
    )