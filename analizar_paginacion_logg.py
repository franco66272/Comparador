import requests
from bs4 import BeautifulSoup
import re


URL = "https://logg.com.ar/Products/"

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
print("=" * 80)
print("FORMS")
print("=" * 80)

for i, form in enumerate(
    soup.select("form")
):

    print()
    print("FORM:", i)
    print(
        "ACTION:",
        form.get("action")
    )
    print(
        "METHOD:",
        form.get("method")
    )

    for elemento in form.select(
        "input, select, button"
    ):

        print(
            elemento.name,
            "| name=",
            elemento.get("name"),
            "| id=",
            elemento.get("id"),
            "| type=",
            elemento.get("type"),
            "| value=",
            elemento.get("value")
        )


print()
print("=" * 80)
print("TEXTO / ATRIBUTOS RELACIONADOS CON PAGINACION")
print("=" * 80)

patrones = [
    "page",
    "pages",
    "pagesize",
    "pageSize",
    "page-number",
    "pageNumber",
    "currentPage",
    "skip",
    "offset",
    "take",
    "limit",
    "size",
    "total",
    "productcount",
    "productCount",
]


for patron in patrones:

    posiciones = [
        m.start()
        for m in re.finditer(
            patron,
            r.text,
            re.IGNORECASE
        )
    ]

    print(
        patron,
        ":",
        len(posiciones)
    )

    if posiciones:

        pos = posiciones[0]

        print(
            r.text[
                max(0, pos - 250):
                pos + 500
            ]
        )


print()
print("=" * 80)
print("BOTONES / LINKS DE NAVEGACION")
print("=" * 80)

for elemento in soup.select(
    "a, button"
):

    texto = elemento.get_text(
        " ",
        strip=True
    )

    href = elemento.get(
        "href"
    )

    if any(
        palabra in (
            texto
            + " "
            + str(href)
        ).lower()
        for palabra in [
            "siguiente",
            "anterior",
            "next",
            "prev",
            "más",
            "mas",
            "cargar",
            "ver más",
            "ver mas"
        ]
    ):

        print(
            "TEXTO:",
            texto,
            "| HREF:",
            href
        )


print()
print("=" * 80)
print("PRODUCT CARDS")
print("=" * 80)

cards = soup.select(
    "a.product-card"
)

print(
    "TOTAL:",
    len(cards)
)


if cards:

    card = cards[0]

    print(
        "ATRIBUTOS:",
        card.attrs
    )