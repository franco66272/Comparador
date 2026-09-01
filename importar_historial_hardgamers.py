"""Importa historial de precios de HardGamers usando IDs directos de Venex."""
from __future__ import annotations

import hashlib
import json
import os
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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}
TIMEOUT = 30
PAUSA = 0.15
MAX_REINTENTOS_429 = 4
MAX_DEBUG = 3
DATE_KEYS = ("fecha", "date", "datetime", "timestamp", "time", "created_at", "createdAt", "day", "x", "t")
PRICE_KEYS = ("precio", "price", "value", "amount", "valor", "cost", "y", "v")


def clave_producto(p):
    stable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def url_hardgamers(p):
    ident = str(p.get("id_producto") or "").strip()
    if not ident.startswith("venex:"):
        return None
    return f"{BASE}/product/{quote(ident, safe=':')}"


def parse_precio(v):
    if v is None or isinstance(v, bool): return None
    s = re.sub(r"[^0-9,.-]", "", str(v).strip())
    if not s: return None
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    else:
        parts = s.split(".")
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]): s = "".join(parts)
    try: n = float(s)
    except ValueError: return None
    return int(round(n)) if 1 <= n <= 500_000_000 else None


def es_fecha(v):
    if isinstance(v, (int, float)): return v > 1_000_000_000
    s = str(v or "").strip()
    return bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s) or re.match(r"^\d{10,13}$", s) or re.search(r"\b20\d{2}[-/]\d{1,2}\b", s))


def normalizar_fecha(v):
    if isinstance(v, (int, float)) and v > 1_000_000_000:
        try: return datetime.fromtimestamp(float(v) / (1000 if v > 10_000_000_000 else 1)).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception: pass
    s = str(v).strip()
    if s.isdigit() and len(s) >= 10:
        try: return datetime.fromtimestamp(int(s) / (1000 if len(s) >= 13 else 1)).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception: pass
    return s


def convertir_serie(obj):
    if isinstance(obj, dict):
        date = next((obj[k] for k in DATE_KEYS if k in obj and obj[k] is not None), None)
        price = next((obj[k] for k in PRICE_KEYS if k in obj and obj[k] is not None), None)
        parsed = parse_precio(price)
        if date is not None and parsed is not None and es_fecha(date):
            return [{"fecha": normalizar_fecha(date), "precio": parsed, "stock": None, "fuente": "HardGamers"}]
        best = []
        for value in obj.values():
            if isinstance(value, (dict, list)):
                current = convertir_serie(value)
                if len(current) > len(best): best = current
        if best: return best
        if obj and all(not isinstance(v, (dict, list)) for v in obj.values()):
            out = []
            for date, price in obj.items():
                parsed = parse_precio(price)
                if parsed is not None and es_fecha(date):
                    out.append({"fecha": normalizar_fecha(date), "precio": parsed, "stock": None, "fuente": "HardGamers"})
            return sorted(out, key=lambda x: x["fecha"])
        return []
    if not isinstance(obj, list): return []
    out = []
    for item in obj:
        if isinstance(item, dict):
            date = next((item[k] for k in DATE_KEYS if k in item and item[k] is not None), None)
            price = next((item[k] for k in PRICE_KEYS if k in item and item[k] is not None), None)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            a, b = item[0], item[1]
            date, price = (a, b) if es_fecha(a) else ((b, a) if es_fecha(b) else (None, None))
        else: continue
        parsed = parse_precio(price)
        if date is not None and parsed is not None and es_fecha(date):
            out.append({"fecha": normalizar_fecha(date), "precio": parsed, "stock": None, "fuente": "HardGamers"})
    out.sort(key=lambda x: x["fecha"])
    seen, dedup = set(), []
    for item in out:
        sig = (item["fecha"], item["precio"])
        if sig not in seen: seen.add(sig); dedup.append(item)
    return dedup


def recorrer(obj, encontrados=None, depth=0):
    encontrados = encontrados if encontrados is not None else []
    if depth > 15: return encontrados
    s = convertir_serie(obj)
    if len(s) >= 2: encontrados.append(s)
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (dict, list)): recorrer(v, encontrados, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)): recorrer(v, encontrados, depth + 1)
    return encontrados


def extraer_texto(texto):
    encontrados = []
    if not texto: return encontrados
    try: encontrados.extend(recorrer(json.loads(texto)))
    except Exception: pass
    return encontrados


def get(session, url):
    for attempt in range(MAX_REINTENTOS_429 + 1):
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 429:
            r.raise_for_status(); return r
        wait = min(90, 5 * (2 ** attempt))
        ra = r.headers.get("Retry-After")
        if ra:
            try: wait = max(wait, float(ra))
            except ValueError: pass
        time.sleep(wait)
    r.raise_for_status(); return r


def extract_http(url, session):
    r = get(session, url)
    soup = BeautifulSoup(r.text, "lxml")
    candidates = extraer_texto(r.text)
    for script in soup.find_all("script"):
        txt = script.string or script.get_text(" ", strip=False)
        if txt and len(txt) < 12_000_000: candidates.extend(extraer_texto(txt))
    return max(candidates, key=len, default=[]), {"status": r.status_code, "url": url, "content_type": r.headers.get("Content-Type", ""), "size": len(r.text)}


def extraer_historial_browser(url, browser, sink):
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="es-AR")
    page = context.new_page(); candidates=[]; responses=[]
    def on_response(resp):
        try:
            ct=(resp.headers.get("content-type") or "").lower()
            interesting="json" in ct or "javascript" in ct or any(k in resp.url.lower() for k in ("api","graphql","ajax","chart","price","history","historial","data","product"))
            if not interesting: return
            body=resp.text()
            if len(body)>8_000_000: return
            responses.append({"url":resp.url,"status":resp.status,"content_type":ct,"size":len(body)})
            candidates.extend(extraer_texto(body))
        except Exception: pass
    page.on("response", on_response)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1200)
        candidates.extend(extraer_texto(page.content()))
        for txt in page.locator("script").all_text_contents():
            if txt and len(txt)<12_000_000: candidates.extend(extraer_texto(txt))
        try: sink["storage"]=page.evaluate("() => ({local:{...localStorage},session:{...sessionStorage}})")
        except Exception: pass
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2200)
        sink["responses"]=responses[-250:]
        sink["resources"]=page.evaluate("() => performance.getEntriesByType('resource').map(x => x.name).slice(-400)")
        sink["html_sample"]=page.content()[:200000]
    finally:
        page.close(); context.close()
    return max(candidates, key=len, default=[])


def main():
    catalog=json.loads(CATALOGO.read_text(encoding="utf-8"))
    try: history=json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else {}
    except Exception: history={}
    objectives=[p for p in catalog if str(p.get("tienda","")).strip().lower()=="venex" and url_hardgamers(p)]
    try: limit=int(os.environ.get("HG_MAX_PRODUCTOS","0") or "0")
    except ValueError: limit=0
    if limit>0: objectives=objectives[:limit]
    results={"inicio":datetime.now().isoformat(),"objetivos":len(objectives),"id_directo":len(objectives),"match":len(objectives),"series":0,"puntos":0,"fallback_browser":0,"errores":[],"modo":"direct-id-http-playwright-v5"}
    debug={"productos":[]}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        results["errores"].append({"error":"playwright_no_instalado"})
        REPORTE.parent.mkdir(exist_ok=True); REPORTE.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8"); return 2
    session=requests.Session(); session.headers.update(HEADERS)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for i,p in enumerate(objectives,1):
            url=url_hardgamers(p); key=clave_producto(p); sink={"producto":p.get("nombre"),"url":url}
            try:
                series,http=extract_http(url,session); sink["http"]=http
                if len(series)<2:
                    results["fallback_browser"]+=1
                    series=extraer_historial_browser(url,browser,sink)
                if len(series)>=2:
                    history[key]=series; results["series"]+=1; results["puntos"]+=len(series); sink["serie_puntos"]=len(series)
                else:
                    results["errores"].append({"producto":p.get("nombre"),"url":url,"error":"sin_serie"})
            except Exception as exc:
                results["errores"].append({"producto":p.get("nombre"),"url":url,"error":f"{type(exc).__name__}: {exc}"})
            debug["productos"].append(sink)
            if i%25==0 or i==len(objectives): print(f"[{i}/{len(objectives)}] ids={results['id_directo']} series={results['series']} puntos={results['puntos']} browser={results['fallback_browser']}")
            time.sleep(PAUSA)
        browser.close()
    HISTORIAL.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    REPORTE.parent.mkdir(exist_ok=True)
    results["fin"]=datetime.now().isoformat()
    REPORTE.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    DEBUG.write_text(json.dumps(debug,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
