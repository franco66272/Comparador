from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import json
import re
import time

from .utils import session_con_reintentos

API_URL = "https://www.maximus.com.ar/wfmWebSite2.aspx/wsNRW_Script"
PAGINA_SESION = "https://www.maximus.com.ar/Productos/Notebooks/maximus.aspx?/CAT=56/SCAT=-1/M=-1/OR=1/PAGE=1/"
BASE_URL = "https://www.maximus.com.ar"
GUID = "a632009a-7686-4fcb-a0b4-24b18caf5234"
HEADERS = {"Referer": PAGINA_SESION}
PAGE_DELAY = 0.5
MAX_PAGINAS = 60


def _precio(valor):
    if valor in (None, "", 0): return None
    try:
        n = float(valor)
        if 0 < n < 1000: n *= 1000
        return int(round(n))
    except (ValueError, TypeError): return None


def _precio_principal(item):
    precio = _precio(item.get("prli_price")); original = _precio(item.get("prli_price_original"))
    if original and precio and precio < original * 0.1: return original
    return precio if precio and precio > 0 else original


def _imagen(item):
    for campo in ("item_img", "item_image", "img", "image", "item_img1", "item_picture", "picture"):
        valor = item.get(campo)
        if not valor: continue
        valor = str(valor).strip()
        if valor.startswith("//"): return "https:" + valor
        if valor.startswith("/"): return BASE_URL + valor
        if valor.startswith(("http://", "https://")): return valor
    codigo = str(item.get("item_code4web") or "").strip()
    return f"{BASE_URL}/Temp/App_WebSite/App_PictureFiles/Items/{codigo}.jpg" if codigo else None


def _url_producto(item):
    item_id = item.get("item_id"); nombre = item.get("item_desc") or item.get("item_desc4link"); codigo = item.get("item_code4web")
    if not item_id or not nombre: return None
    url = f"{BASE_URL}/Producto/{str(nombre).strip().replace(' ', '-')}/ITEM={item_id}/maximus.aspx"
    return url + (f"?PN={codigo}" if codigo else "")


def _llamar_api(session, pagina):
    params = {"ws_id": GUID, "comp_id": 1, "prli_id": 17, "cust_id": -1, "page": pagina, "cat_id": -1, "subcat_id": -1, "brand_id": -1, "local": 0, "search": "", "order": 1, "price_min": "", "price_max": "", "wco_tV": []}
    body = {"guidWS_Id": GUID, "strScriptLabel": "web.MAX.GetItemList4Search_v3_V6", "JSonParameters": json.dumps(params, ensure_ascii=False)}
    headers = {"Content-Type": "application/json; charset=UTF-8", "Referer": PAGINA_SESION, "Origin": BASE_URL}
    response = session.post(API_URL, json=body, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json(); contenido = data.get("d")
    if isinstance(contenido, str):
        texto = contenido.strip()
        if texto.startswith("-2,") or "GlobalBluePoint" in texto or "GBPScripts" in texto or "NO ADQUIRIDO" in texto:
            raise RuntimeError(f"API Maximus rechazó la consulta: {texto}")
        try: contenido = json.loads(texto)
        except json.JSONDecodeError as exc: raise RuntimeError(f"Respuesta API Maximus no JSON: {texto[:300]}") from exc
    if not isinstance(contenido, dict): raise RuntimeError("Respuesta API Maximus inesperada")
    return contenido.get("data", {})


def _normalizar_nombre_imagen(texto):
    texto = re.sub(r"[^a-z0-9áéíóúüñ]+", " ", str(texto or "").lower())
    return " ".join(texto.split())


def _imagen_desde_catalogo_web(session, nombre, cache):
    clave = _normalizar_nombre_imagen(nombre)
    if not clave: return None
    if clave in cache: return cache[clave]
    try:
        url = BASE_URL + "/Productos/maximus.aspx?CAT=-1/SCAT=-1/M=-1/" + f"BUS={quote_plus(str(nombre))}/OR=1/PAGE=1/"
        response = session.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200: cache[clave] = None; return None
        soup = BeautifulSoup(response.text, "html.parser")
        for contenedor in soup.select("div, li, article"):
            if clave not in _normalizar_nombre_imagen(contenedor.get_text(" ", strip=True)): continue
            for img in contenedor.find_all("img"):
                for imagen in (img.get("src"), img.get("data-src"), img.get("data-lazy-src"), img.get("data-original"), img.get("data-image")):
                    if not imagen: continue
                    imagen = str(imagen).strip()
                    if imagen.startswith("//"): imagen = "https:" + imagen
                    elif imagen.startswith("/"): imagen = BASE_URL + imagen
                    if imagen.startswith(("http://", "https://")) and not any(x in imagen.lower() for x in ("logo", "favicon", "mercadopago", "whatsapp", "stock", "garantia", "envio")):
                        cache[clave] = imagen; return imagen
    except Exception:
        pass
    cache[clave] = None
    return None


def _parsear_item(item, session=None, imagen_cache=None):
    nombre = item.get("item_desc"); item_id = item.get("item_id"); codigo = item.get("item_code4web"); precio = _precio_principal(item); precio_original = _precio(item.get("prli_price_original"))
    if not nombre or not item_id or not precio or precio <= 0: return None
    if precio_original and precio_original <= precio: precio_original = None
    url = _url_producto(item)
    if not url: return None
    imagen = _imagen(item)
    if not imagen and session is not None:
        imagen = _imagen_desde_catalogo_web(session, nombre, imagen_cache if imagen_cache is not None else {})
    return {"tienda":"Maximus", "nombre":str(nombre).strip(), "precio":precio, "precio_anterior":precio_original, "stock":1, "imagen":imagen, "url":url, "id_producto":f"{item_id}_{codigo}" if codigo else url}


def extraer():
    imagen_cache = {}; session = session_con_reintentos(); warnings = []; productos = []; ids_vistos = set()
    # La página inicial solo sirve para calentar cookies/sesión. Un timeout aquí
    # no debe abortar toda la extracción: la API puede funcionar sin ese GET.
    try:
        session.get(PAGINA_SESION, headers=HEADERS, timeout=15)
    except Exception as exc:
        warnings.append(f"No se pudo calentar la sesión web: {exc}; se continúa con la API")

    try:
        primera = _llamar_api(session, 1)
    except Exception as exc:
        return {"ok": False, "tienda": "Maximus", "productos": [], "warnings": warnings + [f"API Maximus no disponible: {exc}"]}

    try: paginas_total = int(primera.get("pagesTotal") or 1)
    except (TypeError, ValueError): paginas_total = 1
    try: total_reportado = int(primera.get("itemsTotal") or 0)
    except (TypeError, ValueError): total_reportado = 0
    paginas_total = min(paginas_total, MAX_PAGINAS)
    print(f"[maximus] API: {total_reportado} productos, {paginas_total} páginas")

    def procesar(items):
        for item in items:
            producto = _parsear_item(item, session, imagen_cache)
            if not producto: continue
            clave = producto["id_producto"]
            if clave in ids_vistos: continue
            ids_vistos.add(clave); productos.append(producto)

    procesar(primera.get("items") or [])
    for pagina in range(2, paginas_total + 1):
        time.sleep(PAGE_DELAY)
        try: data = _llamar_api(session, pagina)
        except Exception as exc:
            warnings.append(f"Error página {pagina}: {exc}"); continue
        items = data.get("items") or []
        if not items: warnings.append(f"Página {pagina} sin productos"); continue
        procesar(items); print(f"[maximus] página {pagina}/{paginas_total}: {len(items)} items, {len(productos)} acumulados")
    if total_reportado and len(productos) != total_reportado:
        warnings.append(f"API informa {total_reportado}, se extrajeron {len(productos)}")
    con_imagen = sum(1 for p in productos if p.get("imagen"))
    return {"ok": bool(productos), "tienda":"Maximus", "productos":productos, "con_imagen":con_imagen, "paginas_recorridas":paginas_total, "expected_product_urls":total_reportado or None, "extracted_product_urls":len(productos), "coverage": (len(productos)/total_reportado if total_reportado else None), "warnings":warnings}


if __name__ == "__main__":
    resultado = extraer(); print("\n" + "=" * 50); print("MAXIMUS"); print("=" * 50); print(f"OK: {resultado['ok']}"); print(f"Productos: {len(resultado['productos'])}"); print(f"Con imagen: {resultado['con_imagen']}"); print(f"Páginas: {resultado['paginas_recorridas']}"); [print(f"WARNING: {w}") for w in resultado["warnings"]]; print(resultado["productos"][0] if resultado["productos"] else "Sin productos")
