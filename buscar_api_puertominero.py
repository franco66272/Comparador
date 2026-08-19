import requests
import re

BASE = "https://www.puertominero.com.ar"

CHUNKS = [
    "/_next/static/chunks/717-90777cf66af99b0e.js",
    "/_next/static/chunks/360-ba0526dea4837d6b.js",
    "/_next/static/chunks/218-34116904cf332972.js",
    "/_next/static/chunks/3-46076bc283f652c3.js",
    "/_next/static/chunks/main-b8f84b59676c4ac1.js",
    "/_next/static/chunks/pages/_app-c0ef1847cc05dc3f.js",
]

for chunk in CHUNKS:

    url = BASE + chunk

    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        print()
        print("=" * 80)
        print(chunk)
        print("STATUS:", r.status_code)
        print("BYTES:", len(r.text))

        if r.status_code != 200:
            continue

        if "4244:function" in r.text:

            print(">>> ENCONTRADO MODULO 4244 <<<")

            pos = r.text.find("4244:function")

            print()
            print(r.text[pos:pos + 15000])

        coincidencias = re.findall(
            r'["\']([^"\']*(?:products|categories|api)[^"\']*)["\']',
            r.text,
            re.IGNORECASE
        )

        if coincidencias:

            print()
            print("REFERENCIAS ENCONTRADAS:")

            for x in sorted(set(coincidencias)):
                print(x)

    except Exception as e:

        print("ERROR:", e)