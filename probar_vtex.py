import requests

TIENDAS = [
    ("Venex", "https://www.venex.com.ar/"),
    ("Quantum", "https://quantumhardstore.com/"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def probar(tienda, base):

    print("\n" + "=" * 70)
    print(tienda)
    print(base)

    endpoints = [
        "api/catalog_system/pub/products/search",
        "api/catalog_system/pub/products/search/?_from=0&_to=9",
        "api/catalog_system/pub/products/search?ft=rtx",
    ]

    for endpoint in endpoints:

        url = base.rstrip("/") + "/" + endpoint

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=20
            )

            print()
            print("URL:", url)
            print("STATUS:", r.status_code)
            print("CONTENT:", r.headers.get("Content-Type"))
            print("BYTES:", len(r.content))

            if r.status_code == 200:

                try:

                    datos = r.json()

                    print(
                        "TIPO:",
                        type(datos).__name__
                    )

                    if isinstance(datos, list):

                        print(
                            "PRODUCTOS:",
                            len(datos)
                        )

                        if datos:

                            print(
                                "PRIMER PRODUCTO:"
                            )

                            print(
                                datos[0]
                            )

                        return

                except Exception as e:

                    print(
                        "JSON ERROR:",
                        e
                    )

        except Exception as e:

            print(
                "REQUEST ERROR:",
                e
            )


for tienda, url in TIENDAS:

    probar(
        tienda,
        url
    )