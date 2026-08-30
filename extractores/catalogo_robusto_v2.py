"""Motor robusto V2 para catálogos HTML paginados.

Prioridad: descubrir fichas desde listados, seguir paginación real y medir
cobertura sólo cuando existe una señal objetiva (total de resultados, sitemap
completo o repetición/fin de paginación). Nunca inventa cobertura 100%.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .auto_generico import (
    HEADERS,
    HTTP_TIMEOUT,
    MAX_PRODUCTOS,
    Presupuesto,
    _es_fuente_excluida,
    _es_misma_tienda,
    _extraer_detalle,
    _imagen,
    _nombre_card,
    _normalizar_url,
    _precio_card,
    _url,
)
from .utils import session_con_reintentos

DEFAULT_PRODUCT_RE = re.compile(
    r"/(?:producto|productos|product|products|p|prod)/[^?#]+|"
    r"/catalogo/producto/[^?#]+|/DETALLE/[^?#]+|"
    r"/\d+-[^/?#]+\.html(?:$|\?)",
    re.I,
)


def _next_url(soup, current):
    for a in soup.select('a[rel="next"], link[rel="next"]'):
        href = a.get("href")
        if href:
            u = _normalizar_url(_url(current, href))
            if u and u != _normalizar_url(current):
                return u
    for a in soup.select("a[href]"):
        text = " ".join(a.stripped_strings).lower()
        aria = str(a.get("aria-label") or "").lower()
        title = str(a.get("title") or "").lower()
        if text in {"next", "siguiente", "siguiente página", "next page", "›", "»", ">"} or aria in {"next", "siguiente", "next page"} or title in {"next", "siguiente", "next page"}:
            u = _normalizar_url(_url(current, a.get("href")))
            if u and u != _normalizar_url(current):
                return u
    return None


def _total_from_page(soup):
    text = soup.get_text(" ", strip=True)
    patterns = (
        r"(?:de|of)\s+([0-9][0-9\.\,]*)\s*(?:productos|resultados|items|artículos)",
        r"([0-9][0-9\.\,]*)\s*(?:productos|resultados|items|artículos)",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            try:
                n = int(raw)
                if n > 0:
                    return n
            except ValueError:
                pass
    for el in soup.select("[data-total], [data-total-products], [data-product-count], .count, .woocommerce-result-count"):
        raw = el.get("data-total") or el.get("data-total-products") or el.get("data-product-count") or el.get_text(" ", strip=True)
        nums = re.findall(r"\d[\d\.\,]*", raw or "")
        if nums:
            try:
                n = int(nums[-1].replace(".", "").replace(",", ""))
                if n > 0:
                    return n
            except ValueError:
                pass
    return None


def extraer_desde_config_robusto(config):
    tienda = config["tienda"]
    base_url = _normalizar_url(config["url"])
    patron = re.compile(config.get("producto_regex") or DEFAULT_PRODUCT_RE.pattern, re.I)
    session = session_con_reintentos(intentos=1)
    productos = []
    vistos = set()
    warnings = []
    fuentes = []
    budget = Presupuesto()
    total_objetivo = None
    urls_descubiertas = set()
    paginas = 0

    def add_products(lista):
        nuevos = 0
        for p in lista or []:
            if not p or not p.get("nombre") or not p.get("precio") or not p.get("url"):
                continue
            p["url"] = _normalizar_url(p["url"])
            key = p["url"] or p.get("id_producto")
            if key and key not in vistos:
                vistos.add(key)
                productos.append(p)
                nuevos += 1
        budget.productos = len(productos)
        return nuevos

    for primera in config.get("catalog_urls", [])[:120]:
        url = _normalizar_url(primera)
        visitadas = set()
        while url and url not in visitadas and not budget.vencido():
            visitadas.add(url)
            if not budget.puede_request():
                break
            paginas += 1
            try:
                r = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            except requests.RequestException as exc:
                warnings.append(f"HTTP {url}: {exc}")
                break
            if r.status_code != 200:
                warnings.append(f"HTTP {r.status_code}: {url}")
                break
            soup = BeautifulSoup(r.text, "html.parser")
            page_total = _total_from_page(soup)
            if page_total:
                total_objetivo = max(total_objetivo or 0, page_total)

            enlaces = []
            for a in soup.select("a[href]"):
                href = _normalizar_url(_url(r.url, a.get("href")))
                if href and _es_misma_tienda(href, r.url) and not _es_fuente_excluida(href) and patron.search(href) and href not in urls_descubiertas:
                    urls_descubiertas.add(href)
                    enlaces.append((href, a))

            pagina_productos = []
            for href, a in enlaces:
                node = a
                card = None
                for _ in range(8):
                    node = node.parent if node else None
                    if not node:
                        break
                    if _precio_card(node):
                        card = node
                        break
                if card:
                    nombre = _nombre_card(card) or a.get("title") or a.get_text(" ", strip=True)
                    precio = _precio_card(card)
                    if nombre and precio:
                        texto = card.get_text(" ", strip=True).lower()
                        pagina_productos.append({
                            "tienda": tienda,
                            "nombre": nombre.strip(),
                            "precio": precio,
                            "stock": 0 if any(x in texto for x in ("sin stock", "agotado", "out of stock", "no disponible")) else 1,
                            "imagen": _imagen(card.select_one("img"), r.url),
                            "url": href,
                            "id_producto": href,
                        })
            nuevos = add_products(pagina_productos)
            if nuevos:
                fuentes.append({"tipo": "html", "url": url, "productos": nuevos})

            if total_objetivo and len(productos) >= total_objetivo:
                break
            siguiente = _next_url(soup, r.url)
            if not siguiente or siguiente in visitadas:
                break
            url = siguiente

    # Respaldo puntual: si el listado reveló URLs pero las tarjetas no tenían precio,
    # se consultan las fichas sólo para completar las faltantes y no para todo el sitio.
    faltantes = [u for u in sorted(urls_descubiertas) if u not in vistos]
    if faltantes and not budget.vencido() and not productos:
        for u in faltantes[:200]:
            if budget.vencido() or not budget.puede_request():
                break
            p = _extraer_detalle(u, tienda)
            if p:
                add_products([p])

    if total_objetivo:
        cobertura = min(1.0, len(productos) / total_objetivo)
        if len(productos) >= total_objetivo:
            salud = "HEALTHY"
            completitud = "alta"
        elif paginas > 1 or productos:
            salud = "PARTIAL"
            completitud = "media"
        else:
            salud = "NO_SOURCE"
            completitud = "baja"
        if cobertura < 0.98:
            warnings.append(f"Cobertura insuficiente: {cobertura:.1%} ({len(productos)} / {total_objetivo})")
    else:
        # Sin denominador objetivo, sólo podemos considerar sana la extracción
        # cuando recorrimos paginación hasta su fin y obtuvimos productos.
        if productos and paginas > 1 and not budget.vencido():
            salud = "HEALTHY"
            completitud = "alta"
            cobertura = None
        elif productos:
            salud = "PARTIAL"
            completitud = "media"
            cobertura = None
            warnings.append("No existe total objetivo; extracción no puede demostrar catálogo completo")
        else:
            salud = "NO_SOURCE"
            completitud = "baja"
            cobertura = 0.0

    if budget.vencido():
        salud = "PARTIAL" if productos else "TIMEOUT"
        completitud = "media" if productos else "baja"
        warnings.append(f"Presupuesto agotado: {budget.requests} requests, {paginas} páginas")

    return {
        "ok": bool(productos),
        "tienda": tienda,
        "productos": productos[:MAX_PRODUCTOS],
        "con_imagen": sum(1 for p in productos if p.get("imagen")),
        "warnings": warnings,
        "salud": salud,
        "completitud": completitud,
        "parcial": salud != "HEALTHY",
        "requests": budget.requests,
        "paginas": paginas,
        "fuentes": fuentes,
        "expected_product_urls": total_objetivo or 0,
        "discovered_product_urls": len(urls_descubiertas),
        "extracted_product_urls": len(productos),
        "coverage": round(cobertura, 4) if isinstance(cobertura, (int, float)) else None,
    }
