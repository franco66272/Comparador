import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "diagnostico_salida.html"
html = open(path, encoding="utf-8").read()

idx = html.find("itemsData = d")
if idx == -1:
    print("no encontrado \x27itemsData = d\x27")
else:
    inicio = max(0, idx - 2500)
    fin = min(len(html), idx + 500)
    print(html[inicio:fin])

print("\n\n--- Todas las apariciones de PageMethods en el HTML ---")
for m in re.findall(r"PageMethods\.\w+\([^)]{0,200}\)", html):
    print(f"  {m}")
