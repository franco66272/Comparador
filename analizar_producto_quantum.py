import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

URL = "https://quantumhardstore.com/productos/msi-rtx-3080-gaming-z-trio-outlet-144qk/"

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
print("TITLE:")

print(
    soup.title.get_text(strip=True)
    if soup.title
    else None
)


print()
print("H1:")

h1 = soup.find("h1")

print(
    h1.get_text(" ", strip=True)
    if h1
    else None
)


print()
print("PRECIOS:")

precios = []

for texto in soup.stripped_strings:

    if "$" in texto:

        precios.append(
            texto.strip()
        )

for precio in precios[:30]:

    print(precio)


print()
print("IMAGENES:")

imagenes = []

for img in soup.select("img"):

    src = (
        img.get("src")
        or img.get("data-src")
        or img.get("data-lazy-src")
    )

    if src:

        src = urljoin(
            URL,
            src
        )

        if src not in imagenes:

            imagenes.append(src)


for imagen in imagenes[:20]:

    print(imagen)


print()
print("ENLACES:")

for a in soup.select("a[href]"):

    href = a.get("href")

    if href:

        href = urljoin(
            URL,
            href
        )

        if "producto" in href.lower():

            print(href)


print()
print("STOCK / DISPONIBILIDAD:")

texto = soup.get_text(
    " ",
    strip=True
).lower()

for palabra in [
    "stock",
    "disponible",
    "agotado",
    "sin stock",
    "últimas unidades",
    "ultimas unidades"
]:

    print(
        palabra,
        ":",
        palabra in texto
    )