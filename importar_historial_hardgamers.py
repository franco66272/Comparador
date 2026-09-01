"""Importa historial de precios de HardGamers usando IDs directos de producto."""
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
BASE = "https://www.hardgamers.com.ar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
TIMEOUT = 25
MAX_PRODUCTOS = 0
PAUSA = 0.8
MAX_REINTENTOS_429 = 5


def clave_producto(p):
    estable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(estable.encode("utf-8")).hexdigest()[:20]


def id_hardgamers(producto):
    ident = str(producto.get("id_producto") or "").strip()
    return ident if ident.startswith("venex:") else None


def url_hardgamers(producto):
    ident = id_hardgamers(producto)
    if not ident:
        return None
    return f"{BASE}/product/{quote(ident, safe=':')}"


def parse_precio(valor):
    if valor is None:
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
    f = str(fecha).strip()
    try:
        if f.isdigit() and len(f) >= 10:
            dt = datetime.fromtimestamp(int(f) / (1000 if len(f) >= 13 else 1))
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass
    return f


def convertir_serie(data):
    out = []
    if isinstance(data, dict):
        for key in ("data", "series", "points", "history", "priceHistory", "price_history", "historial", "prices", "datasets", "chart"):
            value = data.get(key)
            if isinstance(value, (dict, list)):
                nested = convertir_serie(value)
                if len(nested) > len(out):
                    out = nested
        if out:
            return out
        if data and all(not isinstance(v, (dict, list)) for v in data.values()):
            for fecha, precio in data.items():
                p = parse_precio(precio)
                if p is not None:
                    out.append({"fecha": normalizar_fecha(fecha), "precio": p, "stock": None, "fuente": "HardGamers"})
            return sorted(out, key=lambda x: x["fecha"])
        return out
    if not isinstance(data, list):
        return out
    for x in data:
        fecha = precio = None
        if isinstance(x, dict):
            fecha = x.get("fecha") or x.get("date") or x.get("datetime") or x.get("timestamp") or x.get("time") or x.get("x")
            precio = x.get("precio") or x.get("price") or x.get("value") or x.get("amount") or x.get("y")
            if fecha is None and isinstance(x.get("data"), dict):
                fecha = x["data"].get("date") or x["data"].get("x")
                precio = precio or x["data"].get("price") or x["data"].get("y")
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            fecha, precio = x[0], x[1]
        p = parse_precio(precio)
        if p is None or fecha is None:
            continue
        out.append({"fecha": normalizar_fecha(fecha), "precio": p, "stock": None, "fuente": "HardGamers"})
    out.sort(key=lambda x: x["fecha"])
    dedup = []
    for item in out:
        sig = (item["fecha"], item["precio"])
        if not dedup or (dedup[-1]["fecha"], dedup[-1]["precio"]) != sig:
            dedup.append(item)
    return dedup


def extraer_json_profundo(obj, encontrados=None):
    encontrados = encontrados if encontrados is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(w in kl for w in ("history", "historial", "pricehistory", "price_history", "prices", "series", "points", "chart", "historico")):
                serie = convertir_serie(v)
                if len(serie) >= 2:
                    encontrados.append(serie)
            if isinstance(v, (dict, list)):
                extraer_json_profundo(v, encontrados)
    elif isinstance(obj, list):
        serie = convertir_serie(obj)
        if len(serie) >= 2:
            encontrados.append(serie)
        for v in obj:
            if isinstance(v, (dict, list)):
                extraer_json_profundo(v, encontrados)
    return encontrados


def extraer_texto_embebido(texto):
    series = []
    patrones = [
        r"(?:priceHistory|price_history|historial|history|historico|precios|prices|series|dataPoints|points|chart)\s*[:=]\s*(\[[\s\S]{10,}?\])",
    ]
    for patron in patrones:
        for match in re.finditer(patron, texto, re.I):
            try:
                series.extend(extraer_json_profundo(json.loads(match.group(1))))
            except Exception:
                pass
    return series


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
    soup = BeautifulSoup(r.text, "lxml")
    series = extraer_texto_embebido(r.text)
    for script in soup.select("script"):
        txt = script.string or script.get_text(" ")
        if not txt:
            continue
        try:
            data = json.loads(txt)
            series.extend(extraer_json_profundo(data))
        except Exception:
            series.extend(extraer_texto_embebido(txt))
    return max(series, key=len, default=[])


def cargar_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def extraer_historial_browser(url, browser):
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="es-AR")
    page = context.new_page()
    candidatos = []

    def inspeccionar_response(response):
        try:
            ct = (response.headers.get("content-type") or "").lower()
            u = response.url.lower()
            if "json" not in ct and not any(k in u for k in ("history", "historial", "price", "precio", "product", "chart")):
                return
            texto = response.text()
            if len(texto) > 4_000_000:
                return
            try:
                candidatos.extend(extraer_json_profundo(json.loads(texto)))
            except Exception:
                candidatos.extend(extraer_texto_embebido(texto))
        except Exception:
            pass

    page.on("response", inspeccionar_response)
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(1200)
    try:
        html = page.content()
        candidatos.extend(extraer_texto_embebido(html))
    except Exception:
        pass
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1800)
    page.close()
    context.close()
    return max(candidatos, key=len, default=[])


def main():
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    historial = {}
    if HISTORIAL.exists():
        try:
            historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
        except Exception:
            historial = {}

    objetivos = [p for p in catalogo if str(p.get("tienda", "")).strip().lower() == "venex" and p.get("nombre")]
    if MAX_PRODUCTOS:
        objetivos = objetivos[:MAX_PRODUCTOS]

    resultados = {
        "inicio": datetime.now().isoformat(),
        "objetivos": len(objetivos),
        "id_directo": 0,
        "sin_id": 0,
        "match": 0,
        "series": 0,
        "puntos": 0,
        "fallback_browser": 0,
        "errores": [],
        "modo": "id_directo+http+playwright",
    }

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
            if not hg:
                resultados["sin_id"] += 1
                resultados["errores"].append({"producto": producto.get("nombre"), "error": "sin_id_hardgamers"})
                continue
            resultados["id_directo"] += 1
            resultados["match"] += 1
            try:
                serie = extraer_historial_http(hg, session)
                if len(serie) < 2:
                    resultados["fallback_browser"] += 1
                    serie = extraer_historial_browser(hg, browser)
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
    print(json.dumps(resultados, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
