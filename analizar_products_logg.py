import requests
from bs4 import BeautifulSoup

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

soup = BeautifulSoup(
    r.text,
    "html.parser"
)

cards = soup.select(
    ".product-card"
)

print(
    "PRODUCT CARDS:",
    len(cards)
)

if cards:

    card = cards[0]

    print()
    print("=" * 80)
    print("PRIMERA TARJETA")
    print("=" * 80)

    print(
        card.prettify()[:12000]
    )

    print()
    print("=" * 80)
    print("TEXTO")
    print("=" * 80)

    print(
        card.get_text(
            " ",
            strip=True
        )
    )

    print()
    print("=" * 80)
    print("IMAGENES")
    print("=" * 80)

    for img in card.select("img"):

        print(
            "SRC:",
            img.get("src")
        )

        print(
            "ALT:",
            img.get("alt")
        )

    print()
    print("=" * 80)
    print("SPANS / H4 / H5 / H6")
    print("=" * 80)

    for elemento in card.select(
        "span, h3, h4, h5, h6, p"
    ):

        texto = elemento.get_text(
            " ",
            strip=True
        )

        if texto:

            print(
                elemento.name,
                "|",
                elemento.get("class"),
                "|",
                texto
            )