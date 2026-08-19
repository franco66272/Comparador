import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "diagnostico_salida.html"
html = open(path, encoding="utf-8").read()

patrones = [
    r"fetch\([\"\x27]([^\"\x27]+)",
    r"\.ajax\(\s*\{[^}]*url\s*:\s*[\"\x27]([^\"\x27]+)",
    r"url\s*:\s*[\"\x27]([^\"\x27]*(?:api|json|producto|search)[^\"\x27]*)[\"\x27]",
    r"[\"\x27]([^\"\x27]*/api/[^\"\x27]*)[\"\x27]",
    r"[\"\x27]([^\"\x27]*\.asmx/[^\"\x27]*)[\"\x27]",
    r"[\"\x27]([^\"\x27]*\.ashx[^\"\x27]*)[\"\x27]",
    r"PageMethods\.\w+",
]

encontrados = set()
for p in patrones:
    for m in re.findall(p, html):
        encontrados.add(m)

print(f"{len(encontrados)} candidatos encontrados:\n")
for e in sorted(encontrados):
    print(f"  {e}")
