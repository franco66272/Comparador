import requests
import json

BASE = "https://api.puertominero.com.ar"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}


endpoints = [
    "/products",
    "/products/",
    "/api/products",
    "/api/products/",
    "/products/by-ids",
]


for endpoint in endpoints:

    url = BASE + endpoint

    print()
    print("=" * 70)
    print(url)

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            params={
                "pageSize": 5,
                "showInWeb": "true",
                "noStock": "false"
            },
            timeout=20
        )

        print("STATUS:", r.status_code)
        print("CONTENT TYPE:", r.headers.get("Content-Type"))
        print("BYTES:", len(r.content))

        print()

        if r.status_code == 200:

            try:

                datos = r.json()

                print(
                    json.dumps(
                        datos,
                        ensure_ascii=False,
                        indent=2
                    )[:8000]
                )

            except Exception as e:

                print(
                    "NO ES JSON:",
                    e
                )

        else:

            print(
                r.text[:1000]
            )

    except Exception as e:

        print(
            "ERROR:",
            e
        )