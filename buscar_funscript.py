import re

js = open("frameworkgbp.js", encoding="utf-8").read()

idx = js.find("funScript")
print(f"\x27funScript\x27 aparece {js.count('funScript')} veces\n")
if idx != -1:
    inicio = max(0, idx - 100)
    fin = min(len(js), idx + 1200)
    print("--- Contexto de la primera aparición ---")
    print(js[inicio:fin])

print("\n\n--- Búsqueda de .ashx / .asmx / url: en frameworkgbp.js ---")
for m in re.findall(r"[\"\x27][^\"\x27]{0,100}\.(?:ashx|asmx)[^\"\x27]{0,60}[\"\x27]", js):
    print(f"  {m}")
for m in re.findall(r"url\s*:\s*[\"\x27][^\"\x27]{0,150}[\"\x27]", js, re.IGNORECASE):
    print(f"  {m}")
