import requests
import re

URL = "https://www.puertominero.com.ar/productos"

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
print()

# Buscar scripts de Next.js
scripts = re.findall(
    r'<script[^>]+src="([^"]+)"',
    r.text
)

print("SCRIPTS ENCONTRADOS:")
for s in scripts:
    print(s)

# Buscar __NEXT_DATA__
print()
print("NEXT DATA:")
print(
    "__NEXT_DATA__" in r.text
)

# Buscar referencias a endpoints / APIs
print()
print("POSIBLES ENDPOINTS:")

patrones = [
    r'https?://[^"\']+',
    r'["\'](/api/[^"\']+)',
    r'fetch\(["\']([^"\']+)',
    r'axios\.(?:get|post)\(["\']([^"\']+)',
]

vistos = set()

for patron in patrones:

    for coincidencia in re.findall(
        patron,
        r.text,
        re.IGNORECASE
    ):

        if isinstance(coincidencia, tuple):
            coincidencia = coincidencia[0]

        if coincidencia not in vistos:

            vistos.add(coincidencia)

            print(
                coincidencia
            )

# Buscar nombres típicos de funciones/endpoints
print()
print("PALABRAS RELEVANTES:")

html = r.text.lower()

for palabra in [
    "api",
    "fetch",
    "axios",
    "products",
    "product",
    "productos",
    "graphql",
    "supabase",
    "firebase",
    "strapi",
    "payload",
    "getproducts",
    "getproducts",
    "catalog"
]:

    print(
        palabra,
        ":",
        html.find(palabra)
    )