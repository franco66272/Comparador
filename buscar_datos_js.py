import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "diagnostico_salida.html"
html = open(path, encoding="utf-8").read()

idxs = [m.start() for m in re.finditer(r"item_id", html)]
print(f"\x27item_id\x27 aparece {len(idxs)} veces\n")

if idxs:
    primero = idxs[0]
    inicio = max(0, primero - 800)
    fin = min(len(html), primero + 1500)
    print("--- Contexto alrededor de la primera aparición ---")
    print(html[inicio:fin])
