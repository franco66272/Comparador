"""Diagnóstico rápido de señales de catálogo por tienda."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "config" / "tiendas_auto.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}


def scan(url):
    out = {"url": url, "http": None, "product_links": 0, "jsonld_products": 0, "sitemap": False, "sitemap_product_urls": 0, "next": False}
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        out["http"] = r.status_code
        if r.status_code != 200:
            return out
    except Exception as exc:
        out["error"] = str(exc)
        return out
    soup = BeautifulSoup(r.text, "html.parser")
    seen = set()
    for a in soup.select("a[href]"):
        u = urljoin(r.url, a.get("href"))
        if u.startswith(r.url.split("//",1)[0] + "//") and u not in seen:
            if re.search(r"/(?:producto|productos|product|products|prod)/|/\d+-[^/?#]+\.html", u, re.I):
                seen.add(u)
    out["product_links"] = len(seen)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                typ = obj.get("@type")
                types = typ if isinstance(typ, list) else [typ]
                if any(str(x).lower() == "product" for x in types):
                    out["jsonld_products"] += 1
                for v in obj.values():
                    if isinstance(v, (dict, list)): stack.append(v)
    try:
        sm = requests.get(urljoin(url, "/sitemap.xml"), headers=HEADERS, timeout=20)
        out["sitemap"] = sm.status_code == 200
        if out["sitemap"]:
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", sm.text, re.I | re.S)
            out["sitemap_product_urls"] = sum(1 for x in locs if re.search(r"/(?:producto|productos|product|products|prod)/|/\d+-[^/?#]+\.html", x, re.I))
    except Exception:
        pass
    out["next"] = bool(soup.select_one('a[rel="next"], a.next, a.next.page-numbers, a.page-numbers.next'))
    return out


def main():
    tiendas = json.loads(REG.read_text(encoding="utf-8"))
    resultados = {}
    for nombre, cfg in tiendas.items():
        if cfg.get("estado") != "activo":
            continue
        print(f"[diag] {nombre} ...", flush=True)
        resultados[nombre] = scan(cfg["url"])
    out = ROOT / "config" / "diagnostico_fuentes.json"
    out.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado: {out}")

if __name__ == "__main__":
    main()
