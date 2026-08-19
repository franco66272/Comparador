"""
Diagnóstico rápido de una URL cuando un extractor da 0 productos o menos de
lo esperado. Pensado para pegar la salida acá y ajustar el selector en un
solo paso, en vez de ir probando a ciegas.

Uso:
    python diagnostico.py https://quantumhardstore.com/productos/
    python diagnostico.py https://logg.com.ar/Products
"""
import sys

from extractores.utils import session_con_reintentos


def main():
    if len(sys.argv) != 2:
        print("Uso: python diagnostico.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    session = session_con_reintentos()
    resp = session.get(url, timeout=20)

    print(f"URL: {url}")
    print(f"STATUS: {resp.status_code}")
    print(f"HTML length: {len(resp.text)}")
    print()

    html = resp.text
    pistas = {
        "tiendanube/mitiendanube": "mitiendanube" in html or "tiendanube" in html,
        "vtex": "vtex" in html.lower(),
        "cygnus": "cygnus" in html.lower(),
        "product-card": "product-card" in html,
        "js-item-product": "js-item-product" in html,
        "product-item": "product-item" in html,
        "JSON-LD Product": '"@type":"Product"' in html or '"@type": "Product"' in html,
    }
    print("Pistas de plataforma / estructura:")
    for nombre, presente in pistas.items():
        print(f"  {nombre}: {presente}")

    print()
    print("Guardando HTML completo en diagnostico_salida.html para inspección manual...")
    with open("diagnostico_salida.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Listo. Pegar acá el fragmento HTML de una tarjeta de producto (~30-50 líneas).")


if __name__ == "__main__":
    main()
