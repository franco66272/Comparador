"""Auditoría automática de extractores basados en CONFIG.

No reemplaza catálogos: mide fuentes públicas del sitio y produce un informe.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .utils import parse_precio_ar

TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
SITEMAP_CANDIDATES = (
    "/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml",
    "/product-sitemap.xml", "/products-sitemap.xml", "/sitemap_products.xml",
)

def _same_host(a: str, base: str) -> bool:
    try:
        return urlparse(a).netloc.lower().lstrip("www.") == urlparse(base).netloc.lower().lstrip("www.")
    except Exception:
        return False

def _price_text(text: str):
    m = re.search(r"(?:\$|ARS)\s*[\d.]+(?:,[\d]+)?", text, re.I)
    return parse_precio_ar(m.group(0)) if m else None

def _count_productish_links(soup: BeautifulSoup, base: str) -> int:
    n = 0
    seen = set()
    for a in soup.select("a[href]"):
        u = urljoin(base, a.get("href", "")).split("#", 1)[0]
        if u in seen or not _same_host(u, base):
            continue
        seen.add(u)
        path = urlparse(u).path.lower()
        text = (a.get_text(" ", strip=True) + " " + path).lower()
        if path.endswith(('.html', '.php')) and _price_text(a.parent.get_text(" ", strip=True) if a.parent else ""):
            n += 1
        elif any(x in text for x in ("producto", "product", "sku")) and _price_text(a.parent.get_text(" ", strip=True) if a.parent else ""):
            n += 1
    return n

def _sitemap_count(session: requests.Session, base: str):
    queue = [urljoin(base, p) for p in SITEMAP_CANDIDATES]
    seen = set()
    product_urls = set()
    for _ in range(100):
        if not queue:
            break
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            r = session.get(u, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code != 200 or not r.text:
            continue
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.I | re.S)
        for loc in locs:
            loc = loc.strip()
            if not _same_host(loc, base):
                continue
            if loc.lower().endswith(".xml"):
                queue.append(loc)
            else:
                product_urls.add(loc)
    return len(product_urls)

def auditar_tienda(nombre, config):
    base = config.get("url")
    result = {"tienda": nombre, "url": base, "ok": False, "http": None, "sitemap_products": None, "html_productish": None, "warnings": []}
    if not base:
        result["warnings"].append("Sin URL")
        return result
    session = requests.Session()
    try:
        r = session.get(base, headers=HEADERS, timeout=TIMEOUT)
        result["http"] = r.status_code
    except requests.RequestException as exc:
        result["warnings"].append(f"Portada inaccesible: {exc}")
        return result
    if r.status_code != 200:
        result["warnings"].append(f"Portada HTTP {r.status_code}")
        return result
    soup = BeautifulSoup(r.text, "html.parser")
    result["html_productish"] = _count_productish_links(soup, r.url)
    result["sitemap_products"] = _sitemap_count(session, r.url)
    result["ok"] = True
    if result["sitemap_products"] == 0 and result["html_productish"] == 0:
        result["warnings"].append("No se detectó catálogo en portada/sitemap; requiere extractor específico o JS")
    return result

def main():
    config_path = Path(__file__).resolve().parent.parent / "config" / "tiendas_auto.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    report = []
    for nombre, config in data.items():
        print(f"[audit] {nombre}")
        report.append(auditar_tienda(nombre, config))
    out = Path(__file__).resolve().parent.parent / "logs_auto" / "auditoria_tiendas.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
