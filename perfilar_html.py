"""
Perfilador genérico de HTML: detecta la tarjeta de producto por repetición + precio.
Uso: python perfilar_html.py diagnostico_salida.html
"""
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

RE_PRECIO = re.compile(r"\$\s?\d{1,3}(?:\.\d{3})*(?:,\d+)?")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "diagnostico_salida.html"
    html = open(path, encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")

    contador = Counter()
    elementos_por_firma = {}
    for el in soup.find_all(True):
        clases = el.get("class")
        if not clases:
            continue
        firma = f"{el.name}." + ".".join(clases)
        contador[firma] += 1
        elementos_por_firma.setdefault(firma, el)

    candidatas = [(firma, n) for firma, n in contador.items() if 5 <= n <= 500]
    candidatas.sort(key=lambda x: -x[1])

    print(f"Total elementos con class: {sum(contador.values())}")
    print(f"Firmas candidatas (se repiten 5-500 veces): {len(candidatas)}\n")

    con_precio = []
    for firma, n in candidatas[:40]:
        el = elementos_por_firma[firma]
        texto = el.get_text(" ", strip=True)
        if RE_PRECIO.search(texto):
            con_precio.append((firma, n))

    print("Top candidatas CON precio adentro:")
    for firma, n in con_precio[:10]:
        print(f"  {firma}  (x{n})")

    if con_precio:
        firma_top = con_precio[0][0]
        el = elementos_por_firma[firma_top]
        print(f"\n--- HTML de muestra para \x27{firma_top}\x27 ---")
        print(el.prettify()[:3000])
    else:
        print("\nNinguna candidata con precio. Top 15 firmas más repetidas igual:")
        for firma, n in candidatas[:15]:
            print(f"  {firma}  (x{n})")


if __name__ == "__main__":
    main()
