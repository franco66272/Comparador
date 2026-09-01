"""Importa historial de precios de HardGamers usando IDs directos de Venex."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent
CATALOGO = RAIZ / "productos.json"
HISTORIAL = RAIZ / "historial_precios.json"
REPORTE = RAIZ / "logs_auto" / "hardgamers_historial.json"
DEBUG = RAIZ / "logs_auto" / "hardgamers_debug.json"
BASE = "https://www.hardgamers.com.ar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
TIMEOUT = 25
MAX_PRODUCTOS = 0
PAUSA = 0.8
MAX_REINTENTOS_429 = 5
DEBUG_MAX = 5
DATE_KEYS = ("fecha", "date", "datetime", "timestamp", "time", "created_at", "createdAt", "day", "x", "t")
PRICE_KEYS = ("precio", "price", "value", "amount", "valor", "cost", "y", "v")
HISTORY_WORDS = ("history", "historial", "historico", "pricehistory", "price_history", "prices", "precios", "series", "chart", "grafico", "graph", "variation", "variacion")


def clave_producto(p):
    estable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(estable.encode("utf-8")).hexdigest()[:20]


def url_hardgamers(producto):
    ident = str(producto.get("id_producto") or "").strip()
    if not ident.startswith("venex:"):
        return None
    return f"{BASE}/product/{quote(ident, safe=':')}"


def parse_precio(valor):
    if valor is None or isinstance(valor, bool):
        return None
    s = re.sub(r"[^0-9,.-]", "", str(valor).strip())
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    else:
        parts = s.split(".")
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]):
            s = "".join(parts)
    try:
        n = float(s)
    except ValueError:
        return None
    return int(round(n)) if 1 <= n <= 500_000_000 else None


def normalizar_fecha(fecha):
    if fecha is None:
        return ""
    if isinstance(fecha, (int, float)) and fecha > 1_000_000_000:
        try:
            ts = float(fecha) / (1000 if fecha > 10_000_000_000 else 1)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    f = str(fecha).strip()
    if f.isdigit() and len(f) >= 10:
        try:
            ts = int(f) / (1000 if len(f) >= 13 else 1)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    return f


def es_fecha(v):
    if isinstance(v, (int, float)):
        return v > 1_000_000_000
    s = str(v or "").strip()
    return bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s) or re.match(r"^\d{10,13}$", s) or re.search(r"\b20\d{2}[-/]\d{1,2}\b", s))


def convertir_serie(data):
    out = []
    if isinstance(data, dict):
        fecha = next((data[k] for k in DATE_KEYS if k in data and data[k] is not None), None)
        precio = next((data[k] for k in PRICE_KEYS if k in data and data[k] is not None), None)
        p = parse_precio(precio)
        if fecha is not None and p is not None:
            return [{"fecha": normalizar_fecha(fecha), "precio": p, "stock": None, "fuente": "HardGamers"}]
        if data and all(not isinstance(v, (dict, list)) for v in data.values()):
            for fecha, precio in data.items():
                p = parse_precio(precio)
                if p is not None and es_fecha(fecha):
                    out.append({"fecha": normalizar_fecha(fecha), "precio": p, "stock": None, "fuente": "HardGamers"})
            if len(out) >= 2:
                return sorted(out, key=lambda x: x["fecha"])
        return []
    if not isinstance(data, list):
        return []
    for x in data:
        fecha = precio = None
        if isinstance(x, dict):
            fecha = next((x[k] for k in DATE_KEYS if k in x and x[k] is not None), None)
            precio = next((x[k] for k in PRICE_KEYS if k in x and x[k] is not None), None)
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            a, b = x[0], x[1]
            if es_fecha(a):
                fecha, precio = a, b
            elif es_fecha(b):
                fecha, precio = b, a
        p = parse_precio(precio)
        if fecha is None or p is None or not es_fecha(fecha):
            continue
        out.append({"fecha": normalizar_fecha(fecha), "precio": p, "stock": None, "fuente": "HardGamers"})
    dedup, seen = [], set()
    for item in sorted(out, key=lambda x: x["fecha"]):
        sig = (item["fecha"], item["precio"])
        if sig not in seen:
            seen.add(sig)
            dedup.append(item)
    return dedup


def recorrer_series(obj, encontrados=None, profundidad=0):
    if encontrados is None:
        encontrados = []
    if profundidad > 12:
        return encontrados
    serie = convertir_serie(obj)
    if len(serie) >= 2:
        encontrados.append(serie)
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (dict, list)):
                recorrer_series(v, encontrados, profundidad + 1)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                recorrer_series(v, encontrados, profundidad + 1)
    return encontrados


def mejor_serie(series):
    validas = [s for s in series if 2 <= len(s) <= 10000]
    return max(validas, key=len, default=[])


def extraer_texto_embebido(texto):
    encontrados = []
    if not texto:
        return encontrados
    try:
        encontrados.extend(recorrer_series(json.loads(texto)))
    except Exception:
        pass
    patron = r"(?:priceHistory|price_history|historial|history|historico|precios|prices|series|dataPoints|points|chart|data)\s*[:=]\s*(\[[\s\S]{10,}?\])"
    for m in re.finditer(patron, texto, re.I):
        try:
            encontrados.extend(recorrer_series(json.loads(m.group(1))))
        except Exception:
            pass
    return encontrados


def request_get(url, session):
    for intento in range(MAX_REINTENTOS_429 + 1):
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        espera = min(90, 4 * (2 ** intento))
        retry_after = r.headers.get("Retry-After")
        try:
            if retry_after:
                espera = max(espera, float(retry_after))
        except ValueError:
            pass
        time.sleep(espera)
    r.raise_for_status()
    return r


def extraer_historial_http(url, session):
    r = request_get(url, session)
    series = extraer_texto_embebido(r.text)
    for script in BeautifulSoup(r.text, "lxml").select("script"):
        txt = script.string or script.get_text(" ", strip=False)
        if txt:
            series.extend(extraer_texto_embebido(txt))
    return mejor_serie(series)


def cargar_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def extraer_historial_browser(url, browser, debug_sink=None):
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="es-AR")
    page = context.new_page()
    candidatos, respuestas = [], []

    def inspeccionar_response(response):
        try:
            u = response.url
            low = u.lower()
            ct = (response.headers.get("content-type") or "").lower()
            interesante = "json" in ct or "javascript" in ct or any(w in low for w in ("/api/", "graphql", "ajax", "chart", "history", "historial", "price", "precio", "data"))
            if not interesante:
                return
            meta = {"url": u, "status": response.status, "content_type": ct}
            try:
                body = response.text()
            except Exception:
                body = ""
            meta["size"] = len(body)
            if body and len(body) <= 2_000_000:
                if any(w in body.lower() for w in HISTORY_WORDS):
                    meta["keywords"] = True
                try:
                    candidatos.extend(recorrer_series(json.loads(body)))
                    meta["json"] = True
                except Exception:
                    candidatos.extend(extraer_texto_embebido(body))
                    meta["json"] = False
            respuestas.append(meta)
        except Exception:
            pass

    page.on("response", inspeccionar_response)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2500)
        page.set_viewport_size({"width": 1440, "height": 1100})
        page.wait_for_timeout(800)
        html = page.content()
        candidatos.extend(extraer_texto_embebido(html))
        scripts = page.locator("script").all_text_contents()
        for txt in scripts:
            if txt and len(txt) < 5_000_000:
                candidatos.extend(extraer_texto_embebido(txt))
        if debug_sink is not None:
            debug_sink["responses"] = respuestas[-150:]
            debug_sink["resource_urls"] = page.evaluate("() => performance.getEntriesByType('resource').map(x => x.name).slice(-250)")
            debug_sink["script_keywords"] = [txt[:4000] for txt in scripts if txt and any(w in txt.lower() for w in HISTORY_WORDS)][:10]
            debug_sink["html_keywords"] = [html[max(0, m.start()-500):m.start()+3500] for m in re.finditer("|".join(HISTORY_WORDS), html, re.I)][:5]
    finally:
        page.close()
        context.close()
    return mejor_serie(candidatos)


def main():
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    historial = {}
    if HISTORIAL.exists():
        try:
            historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
        except Exception:
            historial = {}
    objetivos = [p for p in catalogo if str(p.get("tienda", "")).strip().lower() == "venex" and p.get("nombre") and url_hardgamers(p)]
    if MAX_PRODUCTOS:
        objetivos = objetivos[:MAX_PRODUCTOS]
    resultados = {"inicio": datetime.now().isoformat(), "objetivos": len(objetivos), "id_directo": 0, "match": 0, "series": 0, "puntos": 0, "fallback_browser": 0, "errores": [], "modo": "id_directo+http+playwright+generic_series"}
    debug = {"productos": []}
    sync_playwright = cargar_playwright()
    if sync_playwright is None:
        resultados["errores"].append({"error": "playwright_no_instalado", "detalle": "Instalar con: py -m pip install playwright && py -m playwright install chromium"})
        REPORTE.parent.mkdir(exist_ok=True)
        REPORTE.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
        return 2
    session = requests.Session()
    session.headers.update(HEADERS)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for i, producto in enumerate(objetivos, 1):
            key = clave_producto(producto)
            hg = url_hardgamers(producto)
            resultados["id_directo"] += 1
            resultados["match"] += 1
            try:
                serie = extraer_historial_http(hg, session)
                if len(serie) < 2:
                    resultados["fallback_browser"] += 1
                    sink = {} if len(debug["productos"]) < DEBUG_MAX else None
                    if sink is not None:
                        sink["producto"] = producto.get("nombre")
                        sink["url"] = hg
                        debug["productos"].append(sink)
                    serie = extraer_historial_browser(hg, browser, sink)
                if len(serie) >= 2:
                    historial[key] = serie
                    resultados["series"] += 1
                    resultados["puntos"] += len(serie)
                else:
                    resultados["errores"].append({"producto": producto.get("nombre"), "url": hg, "error": "sin_serie"})
            except Exception as exc:
                resultados["errores"].append({"producto": producto.get("nombre"), "url": hg, "error": f"{type(exc).__name__}: {exc}"})
            if i % 25 == 0 or i == len(objetivos):
                print(f"[{i}/{len(objetivos)}] id_directo={resultados['id_directo']} series={resultados['series']} puntos={resultados['puntos']} browser={resultados['fallback_browser']}")
            time.sleep(PAUSA)
        browser.close()
    HISTORIAL.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORTE.parent.mkdir(exist_ok=True)
    resultados["fin"] = datetime.now().isoformat()
    REPORTE.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultados, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
