"""Aplicación web de TecnoRadar.

La capa pública sólo muestra tiendas cuyo catálogo automático fue verificado
como completo. Los extractores antiguos sin métrica de cobertura mantienen su
comportamiento anterior.
"""
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from hashlib import sha256
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
DATA_BASE_URL = os.environ.get("TECNORADAR_DATA_BASE_URL", "").rstrip("/")
DATA_CACHE_TTL = int(os.environ.get("TECNORADAR_DATA_CACHE_TTL", "300"))
COBERTURA_PUBLICABLE = 0.98
_data_cache = {}
_data_cache_lock = threading.Lock()
IMAGEN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
PLACEHOLDER_IMAGEN_PATTERNS = ("a12.svg", "a13.svg", "a14.svg", "fuego.png", "placeholder", "no-image", "no_image", "default-image", "copito.png")
_CACHE_IMAGENES = {}

NOMBRES_TIENDAS = {
    "rockethard_com_ar":"Rocket Hard", "liontech_gaming_com":"Liontech Gaming", "armytech_com_ar":"Armytech",
    "fullh4rd_com_ar":"Fullh4rd", "katech_com_ar":"Katech", "mymcomputacion_com":"MYM Computación",
    "slot_one_com_ar":"Slot One", "hypergaming_com_ar":"Hypergaming", "gezatek_com_ar":"Gezatek",
    "insumosacuario_com_ar":"Insumos Acuario", "gamingcity_com_ar":"Gaming City", "xt_pc_com_ar":"XT-PC",
    "vrx_com_ar":"VRX", "spacegamer_com_ar":"Space Gamer", "shopgamer_com_ar":"Shop Gamer",
    "portalstore_com_ar":"Portal Store", "noxiestore_com":"Noxie Store", "megasoftargentina_com_ar":"Megasoft Argentina",
    "integradosargentinos_com":"Integrados Argentinos", "hardcorecomputacion_com_ar":"Hardcore Computación",
    "compufanstore_com_ar":"Compufan Store", "backupcomputacion_com":"Backup Computación", "37bytes_com_ar":"37Bytes",
    "710tech_com_ar":"710 Tech", "ngtechnologies_com_ar":"NG Technologies", "gamerfactory_com_ar":"Gamer Factory",
    "necxus_com_ar":"Necxus", "netgaming_ar":"Netgaming", "compragamer_com":"CompraGamer", "mexx_com_ar":"Mexx",
    "venex_com_ar":"Venex", "puertominero_com_ar":"Puerto Minero", "quantum_com":"Quantum", "logg_com_ar":"Logg",
    "maximus_com_ar":"Maximus", "wiztech_com_ar":"WIZ TECH", "thegamershop_com_ar":"The Gamer Shop",
    "scphardstore_com":"SCP Hardstore", "maxtecno_com_ar":"Max Tecno", "goldentechstore_com_ar":"GoldenTech Store",
    "dinobyte_ar":"Dinobyte", "clickgaming_com_ar":"Click Gaming", "universosgamers_com_ar":"Universos Gamers",
    "empeniogamer_com_ar":"Empeño Gamer", "silverhard_com":"Silver Hard",
}
DOMINIOS_TIENDAS = {k: v for k, v in {
    "katech_com_ar":"katech.com.ar", "shopgamer_com_ar":"shopgamer.com.ar", "gamingcity_com_ar":"gamingcity.com.ar",
    "insumosacuario_com_ar":"insumosacuario.com.ar", "fullh4rd_com_ar":"fullh4rd.com.ar", "gezatek_com_ar":"gezatek.com.ar",
    "mymcomputacion_com":"mymcomputacion.com", "xt_pc_com_ar":"xt-pc.com.ar", "hardcorecomputacion_com_ar":"hardcorecomputacion.com.ar",
    "integradosargentinos_com":"integradosargentinos.com", "rockethard_com_ar":"rockethard.com.ar", "hypergaming_com_ar":"hypergaming.com.ar",
    "liontech_gaming_com":"liontech-gaming.com", "710tech_com_ar":"710tech.com.ar", "noxiestore_com":"noxiestore.com",
    "compufanstore_com_ar":"compufanstore.com.ar", "armytech_com_ar":"armytech.com.ar", "ngtechnologies_com_ar":"ngtechnologies.com.ar",
    "megasoftargentina_com_ar":"megasoftargentina.com.ar", "backupcomputacion_com":"backupcomputacion.com", "spacegamer_com_ar":"spacegamer.com.ar",
    "portalstore_com_ar":"portalstore.com.ar", "slot_one_com_ar":"slot-one.com.ar", "gamerfactory_com_ar":"gamerfactory.com.ar",
    "netgaming_ar":"netgaming.ar", "necxus_com_ar":"necxus.com.ar", "compragamer_com":"compragamer.com", "mexx_com_ar":"mexx.com.ar",
    "venex_com_ar":"venex.com.ar", "puertominero_com_ar":"puertominero.com.ar", "quantum_com":"quantumhardstore.com", "logg_com_ar":"logg.com.ar",
    "maximus_com_ar":"maximus.com.ar", "wiztech_com_ar":"wiztech.com.ar", "thegamershop_com_ar":"thegamershop.com.ar",
    "scphardstore_com":"scphardstore.com", "maxtecno_com_ar":"maxtecno.com.ar", "goldentechstore_com_ar":"goldentechstore.com.ar",
    "dinobyte_ar":"dinobyte.ar", "clickgaming_com_ar":"clickgaming.com.ar", "universosgamers_com_ar":"universosgamers.com.ar",
    "empeniogamer_com_ar":"empeniogamer.com.ar", "silverhard_com":"silverhard.com",
}.items()}

CATEGORIAS = [
    ("Placas de video", ("rtx", "gtx", "rx ", "radeon", "geforce", "placa de video", "gpu", "vga ")),
    ("Procesadores", ("procesador", "cpu", "ryzen", "core i3", "core i5", "core i7", "core i9", "threadripper", "athlon", "pentium", "celeron")),
    ("Motherboards", ("motherboard", "mother", "placa madre", "mainboard", "a520", "a620", "b450", "b550", "b650", "x570", "x670", "x870", "z690", "z790", "z890", "h610", "h770", "h810")),
    ("Memorias RAM", ("memoria ram", "ram ddr", "ddr3", "ddr4", "ddr5", "sodimm", "dimm ")),
    ("Almacenamiento", ("ssd", "nvme", "m.2", "disco rigido", "disco duro", "hdd", "sata", "pendrive", "memoria usb")),
    ("Fuentes", ("fuente de alimentacion", "fuente atx", "fuente modular", "fuente 80", "psu ", "power supply")),
    ("Gabinetes", ("gabinete", "case pc", "chasis pc", "mid tower", "full tower")),
    ("Refrigeración", ("watercooler", "water cooling", "watercooling", "cooler cpu", "disipador", "refrigeracion", "fan ", "pasta termica")),
    ("Monitores", ("monitor", "display ", "pantalla ", "ultrawide")),
    ("Notebooks", ("notebook", "laptop", "ultrabook")),
    ("PC armadas", ("pc armada", "computadora gamer", "pc gamer", "desktop gamer", "pc de escritorio", "all in one")),
    ("Teclados", ("teclado", "keyboard")), ("Mouse", ("mouse", "raton")),
    ("Auriculares", ("auricular", "headset", "headphone", "earbuds")), ("Micrófonos", ("microfono", "microphone")),
    ("Webcams", ("webcam", "camara web", "camara usb")), ("Joysticks y controles", ("joystick", "gamepad", "control xbox", "control ps5", "dualshock", "dualsense")),
    ("Impresoras", ("impresora", "multifuncion", "laserjet", "inkjet")),
    ("Redes y WiFi", ("router", "wifi", "wi-fi", "access point", "switch de red", "switch gigabit", "repetidor", "mesh", "adaptador wifi")),
    ("Accesorios", ("hub usb", "adaptador", "cable hdmi", "cable displayport", "cable usb", "lector de tarjetas", "dock ", "soporte de monitor", "soporte notebook")),
]


def imagen_utilizable(imagen):
    v = str(imagen or "").strip().lower()
    return bool(v and v.startswith(("http://", "https://")) and not any(x in v for x in PLACEHOLDER_IMAGEN_PATTERNS))


def _imagen_candidata(valor, base_url):
    if not valor:
        return None
    v = str(valor).strip().strip('"\'')
    if not v or v.startswith("data:"):
        return None
    if v.startswith("//"):
        v = "https:" + v
    v = urljoin(base_url, v)
    return v if imagen_utilizable(v) else None


def logo_tienda_url(tienda):
    dominio = DOMINIOS_TIENDAS.get(str(tienda or "").strip())
    return f"https://www.google.com/s2/favicons?domain={dominio}&sz=128" if dominio else ""


def nombre_tienda_visible(tienda):
    clave = str(tienda or "").strip()
    if clave in NOMBRES_TIENDAS:
        return NOMBRES_TIENDAS[clave]
    texto = clave
    for sufijo in ("_com_ar", "_com", "_ar", ".com.ar", ".com"):
        if texto.endswith(sufijo):
            texto = texto[:-len(sufijo)]
            break
    return " ".join(x.capitalize() for x in texto.replace("_", " ").replace("-", " ").split())


def normalizar_texto(texto):
    texto = str(texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def categoria_producto(producto):
    explicita = str(producto.get("categoria") or "").strip()
    if explicita:
        return explicita
    nombre = normalizar_texto(producto.get("nombre", ""))
    for categoria, tokens in CATEGORIAS:
        for token in tokens:
            if token in nombre:
                return categoria
    return "Otros"


def construir_categorias(productos):
    conteo = {}
    for producto in productos:
        c = categoria_producto(producto)
        conteo[c] = conteo.get(c, 0) + 1
    orden = [x[0] for x in CATEGORIAS] + ["Otros"]
    return [{"nombre": c, "productos": conteo[c]} for c in orden if conteo.get(c)]


def _cargar_datos(path, default):
    ahora = time.time()
    with _data_cache_lock:
        cached = _data_cache.get(path)
        if cached and ahora - cached[0] < DATA_CACHE_TTL:
            return cached[1]
    data = default
    if DATA_BASE_URL:
        try:
            r = requests.get(f"{DATA_BASE_URL}/{path}", timeout=20, headers={"User-Agent": "TecnoRadar/1.0"})
            r.raise_for_status()
            data = r.json()
        except Exception:
            pass
    if data is default:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = default
    with _data_cache_lock:
        _data_cache[path] = (ahora, data)
    return data


def cargar_productos():
    return _cargar_datos("productos.json", [])


def cargar_salud_tiendas():
    return _cargar_datos("config/salud_tiendas.json", {})


def filtrar_tiendas_publicables(productos):
    salud = cargar_salud_tiendas()
    permitidas = set()
    for tienda in {p.get("tienda") for p in productos if p.get("tienda")}:
        info = salud.get(tienda)
        if not info:
            permitidas.add(tienda)
            continue
        cobertura = info.get("coverage")
        estado = str(info.get("salud") or "").upper()
        if cobertura is None:
            if estado in {"", "HEALTHY"}:
                permitidas.add(tienda)
            continue
        try:
            if estado == "HEALTHY" and float(cobertura) >= COBERTURA_PUBLICABLE:
                permitidas.add(tienda)
        except (TypeError, ValueError):
            pass
    return [p for p in productos if p.get("tienda") in permitidas]


def clave_producto(producto):
    estable = str(producto.get("id_producto") or producto.get("url") or "").strip() or f"{producto.get('tienda','')}|{producto.get('nombre','')}"
    return sha256(estable.encode("utf-8")).hexdigest()[:20]


def cargar_json_seguro(path, default):
    return _cargar_datos(path, default)


def guardar_json_seguro(path, data):
    if os.environ.get("TECNORADAR_READ_ONLY", "0") == "1":
        return
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    with _data_cache_lock:
        _data_cache[path] = (time.time(), data)


def extraer_detalle_en_vivo(url):
    resultado = {"ok": False, "precio": None, "descripcion": "", "imagen": None, "verificado_en": None, "error": None}
    if not url:
        resultado["error"] = "Producto sin URL"
        return resultado
    try:
        r = requests.get(url, headers=IMAGEN_HEADERS, timeout=10, allow_redirects=True)
        resultado["verificado_en"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except requests.RequestException as exc:
        resultado["error"] = str(exc)
        return resultado
    if r.status_code != 200:
        resultado["error"] = f"HTTP {r.status_code}"
        return resultado
    soup = BeautifulSoup(r.text, "html.parser")
    precios, descripciones, imagenes = [], [], []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        pila = data if isinstance(data, list) else [data]
        while pila:
            obj = pila.pop()
            if isinstance(obj, dict):
                tipo = obj.get("@type")
                tipos = tipo if isinstance(tipo, list) else [tipo]
                if "Product" in tipos:
                    if obj.get("description"):
                        descripciones.append(str(obj["description"]))
                    image = obj.get("image") or obj.get("thumbnailUrl")
                    imagenes.extend(image if isinstance(image, list) else [image])
                    offers = obj.get("offers")
                    offers = offers if isinstance(offers, list) else [offers]
                    for offer in offers:
                        if isinstance(offer, dict) and offer.get("price") is not None:
                            precios.append(offer["price"])
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        pila.append(value)
            elif isinstance(obj, list):
                pila.extend(obj)
    for selector in ('meta[property="product:price:amount"]', 'meta[itemprop="price"]'):
        for node in soup.select(selector):
            if node.get("content") is not None:
                precios.append(node.get("content"))
    for selector in (".price", ".precio", '[itemprop="price"]', ".product-price", ".special-price", ".current-price"):
        for node in soup.select(selector)[:5]:
            precios.append(node.get("content") or node.get_text(" ", strip=True))
    for candidato in precios:
        try:
            from extractores.utils import parse_precio_ar
            valor = parse_precio_ar(candidato)
            if valor and 100 <= valor <= 500_000_000:
                resultado["precio"] = valor
                break
        except Exception:
            pass
    for selector in (".description", ".product-description", "#description", '[itemprop="description"]', ".descripcion", 'meta[name="description"]', 'meta[property="og:description"]'):
        node = soup.select_one(selector)
        if node:
            texto = node.get("content") or node.get_text(" ", strip=True)
            if len(texto) >= 20:
                descripciones.append(texto)
    if descripciones:
        resultado["descripcion"] = re.sub(r"\s+", " ", max((d.strip() for d in descripciones if d and d.strip()), key=len, default=""))
    for selector in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        node = soup.select_one(selector)
        if node:
            imagenes.append(node.get("content"))
    for img in imagenes:
        imagen = _imagen_candidata(img, r.url)
        if imagen:
            resultado["imagen"] = imagen
            break
    resultado["ok"] = bool(resultado["precio"] or resultado["descripcion"] or resultado["imagen"])
    return resultado


def cargar_historial():
    return cargar_json_seguro("historial_precios.json", {})


def cargar_detalles():
    return cargar_json_seguro("detalles_productos.json", {})


def formatear_fecha_verificacion(fecha):
    return "Sin verificación" if not fecha else str(fecha).replace("T", " ")[:16]


def registrar_verificacion(producto, precio, stock=None, fuente="web"):
    if not precio or precio <= 0:
        return
    historial = cargar_historial()
    key = clave_producto(producto)
    serie = historial.setdefault(key, [])
    ahora = datetime.now()
    entrada = {"fecha": ahora.strftime("%Y-%m-%dT%H:%M:%S"), "precio": int(precio), "stock": int(stock) if isinstance(stock, (int, float)) else stock, "fuente": fuente}
    if not serie or serie[-1].get("precio") != int(precio):
        serie.append(entrada)
        historial[key] = serie[-180:]
        guardar_json_seguro("historial_precios.json", historial)


@app.route("/")
def inicio():
    productos = filtrar_tiendas_publicables(cargar_productos())
    busqueda = request.args.get("q", "").strip()
    precio_min = request.args.get("precio_min", "").strip()
    precio_max = request.args.get("precio_max", "").strip()
    solo_stock = request.args.get("solo_stock") == "1"
    tienda_filtro = request.args.get("tienda", "").strip()
    categoria_filtro = request.args.get("categoria", "").strip()
    orden = request.args.get("orden", "menor")

    if busqueda:
        consulta = normalizar_texto(busqueda)
        tokens = [t for t in consulta.split() if len(t) >= 2]
        resultados = [p for p in productos if consulta in normalizar_texto(p.get("nombre", "")) or all(t in normalizar_texto(p.get("nombre", "")) for t in tokens)]
    elif tienda_filtro or categoria_filtro:
        resultados = list(productos)
    else:
        resultados = []
    if tienda_filtro:
        resultados = [p for p in resultados if p.get("tienda") == tienda_filtro]
    if categoria_filtro:
        resultados = [p for p in resultados if categoria_producto(p) == categoria_filtro]
    if precio_min:
        try: resultados = [p for p in resultados if p.get("precio", 0) >= float(precio_min)]
        except ValueError: pass
    if precio_max:
        try: resultados = [p for p in resultados if p.get("precio", 0) <= float(precio_max)]
        except ValueError: pass
    if solo_stock:
        resultados = [p for p in resultados if p.get("stock", 0) > 0]
    resultados.sort(key=lambda p: p.get("precio", 999999999), reverse=orden == "mayor")

    tiendas = sorted(set(p.get("tienda") for p in productos if p.get("tienda")))
    conteo_tiendas = {}
    for p in productos:
        tienda = p.get("tienda")
        if tienda: conteo_tiendas[tienda] = conteo_tiendas.get(tienda, 0) + 1
    tiendas_info = [{"clave": t, "nombre": nombre_tienda_visible(t), "productos": conteo_tiendas[t]} for t in tiendas]
    tiendas_info.sort(key=lambda x: (-x["productos"], x["nombre"].lower()))
    tiendas_principales, tiendas_restantes = tiendas_info[:8], tiendas_info[8:]
    categorias = construir_categorias(productos)

    candidatas = []
    for p in productos:
        if not p.get("nombre") or not p.get("precio"): continue
        score = (40 if p.get("stock") else 0) + (30 if imagen_utilizable(p.get("imagen")) else 0) + (10 if p.get("url") else 0) + (5 if len(str(p.get("nombre"))) <= 100 else 0)
        candidatas.append((score, nombre_tienda_visible(p.get("tienda")), str(p.get("nombre")).lower(), p))
    candidatas.sort(key=lambda x: (-x[0], x[1].lower(), x[2]))
    destacados, tiendas_destacadas = [], set()
    for _, _, _, p in candidatas:
        if p.get("tienda") in tiendas_destacadas: continue
        destacados.append(p); tiendas_destacadas.add(p.get("tienda"))
        if len(destacados) >= 12: break
    if len(destacados) < 12:
        for _, _, _, p in candidatas:
            if p not in destacados: destacados.append(p)
            if len(destacados) >= 12: break

    try: ultima_actualizacion = datetime.fromtimestamp(os.path.getmtime("productos.json")).strftime("%d/%m/%Y %H:%M")
    except OSError: ultima_actualizacion = "Sin información"
    ofertas = [p for p in productos if p.get("precio_anterior") and p.get("precio") and p["precio_anterior"] > p["precio"]]
    for p in ofertas:
        p["descuento_pct"] = round((1 - float(p["precio"]) / float(p["precio_anterior"])) * 100)
    ofertas.sort(key=lambda p: (-p.get("descuento_pct", 0), p.get("precio", 999999999)))
    historial = cargar_historial()
    ultima_verificacion = {clave_producto(p): formatear_fecha_verificacion(historial.get(clave_producto(p), [{}])[-1].get("fecha")) for p in productos}

    return render_template("index.html", productos=resultados, busqueda=busqueda, precio_min=precio_min, precio_max=precio_max, solo_stock=solo_stock, tienda_filtro=tienda_filtro, categoria_filtro=categoria_filtro, orden=orden, tiendas=tiendas, categorias=categorias, tiendas_info=tiendas_info, tiendas_principales=tiendas_principales, tiendas_restantes=tiendas_restantes, logo_tienda_url=logo_tienda_url, destacados=destacados, destacado_principal=(destacados[0] if destacados else None), nombre_tienda_visible=nombre_tienda_visible, imagen_utilizable=imagen_utilizable, ultima_actualizacion=ultima_actualizacion, total_productos=len(productos), total_tiendas=len(tiendas), ofertas=ofertas[:12], categorias_populares=sorted(categorias, key=lambda x:x["productos"], reverse=True)[:8], clave_producto=clave_producto, historial=historial, ultima_verificacion=ultima_verificacion)


@app.route("/producto/<codigo>")
def producto_detalle(codigo):
    productos = filtrar_tiendas_publicables(cargar_productos())
    producto = next((p for p in productos if clave_producto(p) == codigo), None)
    if not producto:
        return ("Producto no encontrado", 404)
    detalles = cargar_detalles()
    key = clave_producto(producto)
    detalle = detalles.get(key, {})
    vivo = extraer_detalle_en_vivo(producto.get("url"))
    if vivo.get("ok"):
        if vivo.get("descripcion"): detalle["descripcion"] = vivo["descripcion"]
        if vivo.get("imagen"): detalle["imagen"] = vivo["imagen"]; producto["imagen"] = vivo["imagen"]
        if vivo.get("precio"): detalle["precio_verificado"] = vivo["precio"]; detalle["verificado_en"] = vivo.get("verificado_en"); registrar_verificacion(producto, vivo["precio"], producto.get("stock"), "detalle_web")
        detalles[key] = detalle
        guardar_json_seguro("detalles_productos.json", detalles)
    historial = cargar_historial().get(key, [])
    return render_template("producto.html", producto=producto, detalle=detalle, historial=historial, categorias=construir_categorias(productos), categoria_filtro="", nombre_tienda_visible=nombre_tienda_visible, imagen_utilizable=imagen_utilizable, clave_producto=clave_producto)


@app.route("/health")
def health():
    return {"ok": True, "servicio": "TecnoRadar", "productos": len(filtrar_tiendas_publicables(cargar_productos()))}


@app.route("/resolver-imagen")
def resolver_imagen():
    imagen = request.args.get("imagen", "").strip()
    producto_url = request.args.get("producto", "").strip()
    if imagen_utilizable(imagen):
        return redirect(imagen, code=302)
    if producto_url:
        clave = producto_url
        if clave in _CACHE_IMAGENES:
            encontrada = _CACHE_IMAGENES[clave]
        else:
            encontrada = None
            try:
                r = requests.get(producto_url, headers=IMAGEN_HEADERS, timeout=7)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    meta = soup.select_one('meta[property="og:image"]')
                    encontrada = _imagen_candidata(meta.get("content") if meta else None, r.url)
                    _CACHE_IMAGENES[clave] = encontrada
            except requests.RequestException:
                encontrada = None
        if encontrada:
            return redirect(encontrada, code=302)
    return ("", 404)


@app.route("/salud")
def salud():
    data = cargar_salud_tiendas()
    return {"estado": "OK", "tiendas": data}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
