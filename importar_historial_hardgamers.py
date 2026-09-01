"""Importa historial de precios de HardGamers para productos de TecnoRadar.

HardGamers carga parte de la información del producto mediante JavaScript. Por
eso este importador usa dos capas:
  1) requests para resolver el producto en el buscador sin bombardear el sitio;
  2) Playwright/Chromium para abrir la ficha como un navegador real e interceptar
     respuestas JSON/XHR que contengan la serie histórica.

Si Playwright no está disponible, el script termina con una instrucción clara
para instalarlo. Nunca reemplaza un historial local existente por una serie
vacía.
"""
from __future__ import annotations

import json
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent
CATALOGO = RAIZ / "productos.json"
HISTORIAL = RAIZ / "historial_precios.json"
REPORTE = RAIZ / "logs_auto" / "hardgamers_historial.json"
BASE = "https://www.hardgamers.com.ar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
TIMEOUT = 25
MAX_PRODUCTOS = 0  # 0 = todos
PAUSA = 0.8
MAX_REINTENTOS_429 = 5


def clave_producto(p):
    estable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(estable.encode("utf-8")).hexdigest()[:20]


def normalizar(texto):
    import unicodedata
    texto = str(texto or "").lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def tokens_relevantes(texto):
    stop = {"disco", "solido", "ssd", "memoria", "ram", "para", "con", "sin", "incluye", "pc", "gamer", "gaming", "negro", "blanco"}
    return [t for t in normalizar(texto).split() if len(t) >= 3 and t not in stop]


def parse_precio(valor):
    if valor is None:
        return None
    s = str(valor).strip()
    s = re.sub(r"[^0-9,.-]", "", s)
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


def convertir_serie(data):
    """Convierte listas/diccionarios de puntos en nuestro formato."""
    out = []
    if isinstance(data, dict):
        # Variantes frecuentes: {date: price}, {timestamp: price}, {data:[...]}
        for key in ("data", "series", "points", "history", "priceHistory", "price_history", "historial", "prices"):
            if isinstance(data.get(key), list):
                nested = convertir_serie(data[key])
                if len(nested) > len(out):
                    out = nested
        if out:
            return out
        items = list(data.items())
        if items and all(not isinstance(v, (dict, list)) for _, v in items):
            for fecha, precio in items:
                p = parse_precio(precio)
                if p is not None:
                    out.append({"fecha": str(fecha), "precio": p, "stock": None, "fuente": "HardGamers"})
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
        f = str(fecha)
        try:
            if f.isdigit() and len(f) >= 10:
                dt = datetime.fromtimestamp(int(f) / (1000 if len(f) >= 13 else 1))
                f = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
        out.append({"fecha": f, "precio": p, "stock": None, "fuente": "HardGamers"})
    out.sort(key=lambda x: x["fecha"])
    dedup = []
    for item in out:
        if not dedup or (dedup[-1]["fecha"], dedup[-1]["precio"]) != (item["fecha"], item["precio"]):
            dedup.append(item)
    return dedup


def extraer_json_profundo(obj, encontrados=None):
    """Busca recursivamente listas que parezcan series de precio."""
    encontrados = encontrados if encontrados is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(w in kl for w in ("history", "historial", "pricehistory", "price_history", "prices", "series", "points")):
                serie = convertir_serie(v)
                if len(serie) >= 2:
                    encontrados.append(serie)
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
    """Extrae JSON/objetos JavaScript incrustados sin depender de un nombre fijo."""
    series = []
    # Primero intenta arrays JSON asociados a nombres conocidos.
    patrones = [
        r"(?:priceHistory|price_history|historial|history|historico|precios|prices|series|dataPoints|points)\s*[:=]\s*(\[[\s\S]{10,}?\])",
    ]
    for patron in patrones:
        for m in re.finditer(patron, texto, re.I):
            bruto = m.group(1)
            try:
                series.extend(extraer_json_profundo(json.loads(bruto)))
            except Exception:
                pass
    return series


def request_get(url, session):
    """GET con backoff para no disparar el 429 de HardGamers."""
    for intento in range(MAX_REINTENTOS_429 + 1):
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        espera = min(60, 3 * (2 ** intento))
        retry_after = r.headers.get("Retry-After")
        try:
            espera = max(espera, float(retry_after)) if retry_after else espera
        except ValueError:
            pass
        time.sleep(espera)
    r.raise_for_status()
    return r


def buscar_hardgamers(nombre, session):
    # La interfaz actual usa ?text=; ?q= produce resultados inconsistentes.
    url = f"{BASE}/search?text={quote(nombre)}&limit=39&page=1"
    r = request_get(url, session)
    soup = BeautifulSoup(r.text, "lxml")
    objetivo = normalizar(nombre)
    objetivo_tokens = set(tokens_relevantes(nombre))
    candidatos = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        # Las fichas actuales son /product/... (no /producto/...)
        if "/product/" not in href:
            continue
        texto = normalizar(a.get_text(" ", strip=True))
        if not texto:
            continue
        score = 0
        if objetivo == texto:
            score += 1000
        tokens = set(tokens_relevantes(texto))
        comunes = len(objetivo_tokens & tokens)
        score += comunes * 10
        # Evita falsos positivos por nombres apenas relacionados.
        if objetivo_tokens and comunes / max(1, len(objetivo_tokens)) < 0.35:
            continue
        candidatos.append((score, urljoin(BASE, href)))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][1] if candidatos else None


def extraer_historial_http(url, session):
    r = request_get(url, session)
    series = extraer_texto_embebido(r.text)
    for script in BeautifulSoup(r.text, "lxml").select("script"):
        txt = script.string or script.get_text(" ")
        if txt:
            series.extend(extraer_texto_embebido(txt))
    mejor = []
    for serie in series:
        if len(serie) > len(mejor):
            mejor = serie
    return mejor


def cargar_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def extraer_historial_browser(url, browser):
    """Abre la ficha con Chromium e inspecciona JSON/XHR y estado JS."""
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="es-AR")
    page = context.new_page()
    candidatos = []

    def inspeccionar_response(response):
        try:
            ct = (response.headers.get("content-type") or "").lower()
            u = response.url.lower()
            if "json" not in ct and not any(k in u for k in ("history", "historial", "price", "precio", "product")):
                return
            texto = response.text()
            if len(texto) > 3_000_000:
                return
            try:
                obj = json.loads(texto)
                candidatos.extend(extraer_json_profundo(obj))
            except Exception:
                candidatos.extend(extraer_texto_embebido(texto))
        except Exception:
            pass

    page.on("response", inspeccionar_response)
    page.goto(url, wait_until="networkidle", timeout=45_000)
    # Algunas gráficas se solicitan al entrar en viewport o después de unos ms.
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(2500)
    try:
        html = page.content()
        candidatos.extend(extraer_texto_embebido(html))
    except Exception:
        pass
    page.close()
    context.close()
    mejor = []
    for serie in candidatos:
        if len(serie) > len(mejor):
            mejor = serie
    return mejor


def main():
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    historial = {}
    if HISTORIAL.exists():
        try:
            historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
        except Exception:
            historial = {}

    objetivos = [p for p in catalogo if normalizar(p.get("tienda")) == "venex" and p.get("nombre")]
    if MAX_PRODUCTOS:
        objetivos = objetivos[:MAX_PRODUCTOS]

    resultados = {"inicio": datetime.now().isoformat(), "objetivos": len(objetivos), "match": 0, "series": 0, "puntos": 0, "errores": [], "modo": "http+playwright"}
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
            try:
                hg = buscar_hardgamers(producto["nombre"], session)
                if not hg:
                    resultados["errores"].append({"producto": producto["nombre"], "error": "sin_match"})
                    continue
                resultados["match"] += 1
                serie = extraer_historial_http(hg, session)
                if len(serie) < 2:
                    serie = extraer_historial_browser(hg, browser)
                if serie:
                    # Solo reemplaza si realmente recuperamos puntos.
                    historial[key] = serie
                    resultados["series"] += 1
                    resultados["puntos"] += len(serie)
                else:
                    resultados["errores"].append({"producto": producto["nombre"], "url": hg, "error": "sin_serie"})
            except Exception as exc:
                resultados["errores"].append({"producto": producto["nombre"], "error": f"{type(exc).__name__}: {exc}"})
            if i % 25 == 0 or i == len(objetivos):
                print(f"[{i}/{len(objetivos)}] match={resultados['match']} series={resultados['series']} puntos={resultados['puntos']}")
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
