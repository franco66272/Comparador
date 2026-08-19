"""
Extractor de Logg (plataforma propia / Cygnus).
Paginación: PageSize solo en página 1, pageNumber a partir de la 2.
"""
import re

from bs4 import BeautifulSoup

from .utils import parse_precio_ar, session_con_reintentos

BASE_URL = "https://logg.com.ar"
PAGE_SIZE = 100
MAX_PAGINAS = 100

RE_ONCLICK = re.compile(
    r"callGtagFunction\(\s*'[^']*',\s*'(?P<id>\d+)',\s*'(?P<nombre>[^']*)'"
    r".*?,\s*(?P<precio>[\d.]+)\s*,\s*\d+\s*\)",
    re.DOTALL,
)


def _parsear_tarjeta(card):
    href = card.get("href")
    if not href:
        return None
    url = BASE_URL + href if href.startswith("/") else href

    onclick = card.get("onclick", "")
    m = RE_ONCLICK.search(onclick)
    id_producto = m.group("id") if m else None
    precio = parse_precio_ar(m.group("precio")) if m else None

    nombre_el = card.select_one(".card-text")
    nombre = nombre_el.get_text(strip=True) if nombre_el else (m.group("nombre").strip() if m else None)

    if precio is None:
        precio_el = card.select_one(".small-price")
        if precio_el:
            precio = parse_precio_ar(precio_el.get_text(strip=True))

    img = card.select_one(".card-img-top")
    imagen = img.get("src") if img else None

    if not nombre or not precio:
        return None

    return {
        "tienda": "Logg",
        "nombre": nombre,
        "precio": precio,
        "precio_anterior": None,
        "stock": 1,
        "imagen": imagen,
        "url": url,
        "id_producto": id_producto or url,
    }


def extraer():
    session = session_con_reintentos()
    productos = []
    urls_vistas = set()
    warnings = []
    pagina = 1

    while pagina <= MAX_PAGINAS:
        if pagina == 1:
            url = f"{BASE_URL}/Products?PageSize={PAGE_SIZE}"
        else:
            url = f"{BASE_URL}/Products?PageSize={PAGE_SIZE}&pageNumber={pagina}"
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            warnings.append(f"HTTP {resp.status_code} en página {pagina}, se corta acá")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tarjetas = soup.select("a.product-card")
        if not tarjetas:
            break

        nuevos = 0
        for tarjeta in tarjetas:
            p = _parsear_tarjeta(tarjeta)
            if p and p["url"] not in urls_vistas:
                urls_vistas.add(p["url"])
                productos.append(p)
                nuevos += 1

        if nuevos == 0:
            if pagina == 1:
                warnings.append("Página 1 sin productos — revisar selector 'a.product-card'")
            break

        pagina += 1

    paginas_recorridas = pagina - 1
    if paginas_recorridas <= 1 and len(productos) >= PAGE_SIZE:
        warnings.append(
            "pageNumber no está avanzando el catálogo (misma página repetida)."
        )

    con_imagen = sum(1 for p in productos if p.get("imagen"))
    return {
        "ok": len(productos) > 0,
        "tienda": "Logg",
        "productos": productos,
        "con_imagen": con_imagen,
        "paginas_recorridas": paginas_recorridas,
        "warnings": warnings,
    }


if __name__ == "__main__":
    resultado = extraer()
    print(f"OK: {resultado['ok']}")
    print(f"Productos: {len(resultado['productos'])}")
    print(f"Con imagen: {resultado['con_imagen']}")
    print(f"Páginas recorridas: {resultado['paginas_recorridas']}")
    for w in resultado["warnings"]:
        print(f"WARNING: {w}")
