import re
import requests

url = "https://www.maximus.com.ar/App_Scripts/frameworkgbp.js"
resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
print(f"STATUS: {resp.status_code}")
js = resp.text
print(f"Longitud: {len(js)}\n")

open("frameworkgbp.js", "w", encoding="utf-8").write(js)
print("Guardado en frameworkgbp.js\n")

print("--- BASE_URL ---")
for m in re.findall(r"BASE_URL[^;,\n]{0,150}", js):
    print(f"  {m.strip()}")

print("\n--- fetch/axios/ajax con \x27item\x27 o \x27product\x27 o \x27api\x27 ---")
for patron in [
    r"fetch\([^)]{0,200}\)",
    r"axios\.\w+\([^)]{0,200}\)",
    r"\.ajax\(\{[^}]{0,300}\}",
    r"[\"\x27][^\"\x27]{0,80}(?:api|Item|Product|item_id)[^\"\x27]{0,80}[\"\x27]",
]:
    for m in re.findall(patron, js, re.IGNORECASE):
        if any(k in m.lower() for k in ["item", "product", "api", "search"]):
            print(f"  {m.strip()[:200]}")
