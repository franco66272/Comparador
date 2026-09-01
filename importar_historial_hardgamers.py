"""Importa historial de precios de HardGamers para productos de TecnoRadar.

La fuente pública de HardGamers muestra que cada producto dispone de historial
de variación de precio. Este importador intenta localizar la publicación
correspondiente y extraer una serie histórica desde el HTML/JSON embebido.
Si una página no expone la serie de forma estructurada, se conserva el
historial local y se registra el motivo en el reporte.
"""
from __future__ import annotations

import json
import re
import time
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
TIMEOUT = 20
MAX_PRODUCTOS = 0  # 0 = todos
PAUSA = 0.15


def clave_producto(p):
    import hashlib
    estable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(estable.encode("utf-8")).hexdigest()[:20]


def normalizar(texto):
    import unicodedata
    texto = str(texto or "").lower()
    return " ".join("".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").split())


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


def extraer_json_embebido(texto):
    series = []
    patrones = [
        r"(?:priceHistory|price_history|historial|history|historico|precios|prices)\s*[:=]\s*(\[[^\]]{10,}\])",
        r"(?:series|dataPoints|data)\s*[:=]\s*(\[[^\]]{10,}\])",
    ]
    for patron in patrones:
        for match in re.finditer(patron, texto, re.I | re.S):
            bruto = match.group(1)
            try:
                data = json.loads(bruto)
            except Exception:
                continue
            if isinstance(data, list):
                series.append(data)
    return series


def convertir_serie(data):
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        fecha = precio = None
        if isinstance(x, dict):
            fecha = x.get("fecha") or x.get("date") or x.get("datetime") or x.get("time") or x.get("x")
            precio = x.get("precio") or x.get("price") or x.get("value") or x.get("y")
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


def buscar_hardgamers(nombre):
    url = f"{BASE}/search?q={quote(nombre)}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    objetivo = normalizar(nombre)
    candidatos = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        texto = normalizar(a.get_text(" ", strip=True))
        if "detalleproducto" not in href and "producto" not in href:
            continue
        if texto:
            score = 0
            if objetivo == texto:
                score += 100
            for token in objetivo.split()[:8]:
                if len(token) >= 4 and token in texto:
                    score += 3
            candidatos.append((score, urljoin(BASE, href)))
    candidatos.sort(reverse=True)
    return candidatos[0][1] if candidatos else None


def extraer_historial_url(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    series = extraer_json_embebido(r.text)
    for script in soup.select("script"):
        txt = script.string or script.get_text(" ")
        if txt and ("priceHistory" in txt or "historial" in txt.lower() or "history" in txt.lower()):
            series.extend(extraer_json_embebido(txt))
    mejor = []
    for serie in series:
        normalizada = convertir_serie(serie)
        if len(normalizada) > len(mejor):
            mejor = normalizada
    return mejor


def main():
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    historial = {}
    if HISTORIAL.exists():
        try:
            historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
        except Exception:
            historial = {}
    objetivos = [p for p in catalogo if p.get("tienda") == "Venex" and p.get("nombre")]
    if MAX_PRODUCTOS:
        objetivos = objetivos[:MAX_PRODUCTOS]
    resultados = {"inicio": datetime.now().isoformat(), "objetivos": len(objetivos), "match": 0, "series": 0, "puntos": 0, "errores": []}
    for i, producto in enumerate(objetivos, 1):
        key = clave_producto(producto)
        try:
            hg = buscar_hardgamers(producto["nombre"])
            if not hg:
                resultados["errores"].append({"producto": producto["nombre"], "error": "sin_match"})
                continue
            resultados["match"] += 1
            serie = extraer_historial_url(hg)
            if serie:
                historial[key] = serie
                resultados["series"] += 1
                resultados["puntos"] += len(serie)
            else:
                resultados["errores"].append({"producto": producto["nombre"], "url": hg, "error": "sin_serie"})
        except Exception as exc:
            resultados["errores"].append({"producto": producto["nombre"], "error": f"{type(exc).__name__}: {exc}"})
        if i % 25 == 0:
            print(f"[{i}/{len(objetivos)}] series={resultados['series']} puntos={resultados['puntos']}")
        time.sleep(PAUSA)
    HISTORIAL.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORTE.parent.mkdir(exist_ok=True)
    resultados["fin"] = datetime.now().isoformat()
    REPORTE.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
