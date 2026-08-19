import requests
from bs4 import BeautifulSoup

TIENDAS = [
    ("Venex", "https://www.venex.com.ar/"),
    ("Puerto Minero", "https://www.puertominero.com.ar/"),
    ("Quantum", "https://quantumhardstore.com/"),
    ("Logg", "https://logg.com.ar/"),
    ("Maximus", "https://www.maximus.com.ar/"),
    ("Fullh4rd", "https://fullh4rd.com.ar/"),
]

for nombre, url in TIENDAS:

    print("\n" + "=" * 80)
    print(nombre)
    print(url)

    try:
        r = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        print("STATUS:", r.status_code)
        print("HTML:", len(r.text))

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        print("TITLE:", soup.title.get_text(strip=True) if soup.title else None)

        print("INPUT SEARCH:", len(
            soup.select(
                'input[type="search"], input[name*="search"], input[name*="buscar"]'
            )
        ))

        print("IMG:", len(soup.select("img")))
        print("LINKS:", len(soup.select("a[href]")))

        print("PRICE WORDS:", sum(
            1 for x in soup.stripped_strings
            if "$" in x
        ))

        print("JSON-LD:", len(
            soup.select(
                'script[type="application/ld+json"]'
            )
        ))

        print("SHOPIFY:", "shopify" in r.text.lower())
        print("WOOCOMMERCE:", "woocommerce" in r.text.lower())
        print("PRESTASHOP:", "prestashop" in r.text.lower())
        print("VTEX:", "vtex" in r.text.lower())
        print("TIENDANUBE:", "tiendanube" in r.text.lower())

    except Exception as e:

        print("ERROR:", e)