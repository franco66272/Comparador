from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for
import json
import os
import time
import re
import unicodedata
from datetime import datetime, timedelta
import threading
from hashlib import sha256
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# En Render Free el sistema web es de solo lectura: los datos persistentes
# se actualizan fuera del proceso y el servidor los vuelve a cargar desde GitHub.
DATA_BASE_URL = os.environ.get("TECNORADAR_DATA_BASE_URL", "").rstrip("/")
DATA_CACHE_TTL = int(os.environ.get("TECNORADAR_DATA_CACHE_TTL", "300"))
_data_cache = {}
_data_cache_lock = threading.Lock()

PLACEHOLDER_IMAGEN_PATTERNS = ("a12.svg", "a13.svg", "a14.svg", "fuego.png", "placeholder", "no-image", "no_image", "default-image", "copito.png")
IMAGEN_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}
_CACHE_IMAGENES = {}

def imagen_utilizable(imagen):
    valor = str(imagen or "").strip().lower()
    if not valor or not (valor.startswith("http://") or valor.startswith("https://")):
        return False
    return not any(patron in valor for patron in PLACEHOLDER_IMAGEN_PATTERNS)

def _imagen_candidata(valor, base_url):
    if not valor: return None
    valor = str(valor).strip().strip('"\'')
    if not valor or valor.startswith("data:"): return None
    if valor.startswith("//"): valor = "https:" + valor
    valor = urljoin(base_url, valor)
    return valor if imagen_utilizable(valor) else None

def _extraer_imagen_producto(url):
    if not url: return None
    clave = str(url).strip()
    if clave in _CACHE_IMAGENES: return _CACHE_IMAGENES[clave]
    try:
        parsed = urlparse(clave)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: return None
        respuesta = requests.get(clave, headers=IMAGEN_HEADERS, timeout=7, allow_redirects=True)
        if respuesta.status_code != 200 or "text/html" not in respuesta.headers.get("Content-Type", "").lower(): return None
    except requests.RequestException: return None
    soup = BeautifulSoup(respuesta.text, "html.parser")
    candidatos = []
    for selector in ('meta[property="og:image"]','meta[name="twitter:image"]','meta[property="twitter:image"]'):
        for meta in soup.select(selector): candidatos.append(meta.get("content"))
    for script in soup.select('script[type="application/ld+json"]'):
        try: data = json.loads(script.string or script.get_text())
        except Exception: continue
        pila = data if isinstance(data, list) else [data]
        while pila:
            obj = pila.pop()
            if isinstance(obj, dict):
                tipo = obj.get("@type"); tipos = tipo if isinstance(tipo, list) else [tipo]
                if "Product" in tipos or "image" in obj:
                    imagen = obj.get("image") or obj.get("thumbnailUrl")
                    candidatos.extend(imagen if isinstance(imagen, list) else [imagen])
                for valor in obj.values():
                    if isinstance(valor, (dict, list)): pila.append(valor)
            elif isinstance(obj, list): pila.extend(obj)
    for img in soup.select("img"):
        for atributo in ("data-zoom-image","data-large-image","data-full","data-original","data-image","data-lazy-src","data-srcset","data-src","srcset","src"):
            valor = img.get(atributo)
            if atributo in ("srcset", "data-srcset") and valor: valor = str(valor).split(",")[0].strip().split(" ")[0]
            candidata = _imagen_candidata(valor, respuesta.url)
            if candidata: candidatos.append(candidata)
    for candidata in candidatos:
        imagen = _imagen_candidata(candidata, respuesta.url)
        if imagen:
            _CACHE_IMAGENES[clave] = imagen
            return imagen
    _CACHE_IMAGENES[clave] = None
    return None

# Todas las tiendas conocidas por el proyecto. Esta lista es independiente de
# los productos cargados: una tienda configurada no desaparece de la UI sólo
# porque temporalmente tenga 0 productos.
NOMBRES_TIENDAS = {
    "rockethard_com_ar":"Rocket Hard", "liontech_gaming_com":"Liontech Gaming", "armytech_com_ar":"Armytech", "fullh4rd_com_ar":"Fullh4rd", "katech_com_ar":"Katech", "mymcomputacion_com":"MYM Computación", "slot_one_com_ar":"Slot One", "hypergaming_com_ar":"Hypergaming", "gezatek_com_ar":"Gezatek", "insumosacuario_com_ar":"Insumos Acuario", "gamingcity_com_ar":"Gaming City", "xt_pc_com_ar":"XT-PC", "vrx_com_ar":"VRX", "spacegamer_com_ar":"Space Gamer", "shopgamer_com_ar":"Shop Gamer", "portalstore_com_ar":"Portal Store", "noxiestore_com":"Noxie Store", "megasoftargentina_com_ar":"Megasoft Argentina", "integradosargentinos_com":"Integrados Argentinos", "hardcorecomputacion_com_ar":"Hardcore Computación", "compufanstore_com_ar":"Compufan Store", "backupcomputacion_com":"Backup Computación", "37bytes_com_ar":"37Bytes", "710tech_com_ar":"710 Tech", "ngtechnologies_com_ar":"NG Technologies", "gamerfactory_com_ar":"Gamer Factory", "necxus_com_ar":"Necxus", "netgaming_ar":"Netgaming", "compragamer_com":"CompraGamer", "mexx_com_ar":"Mexx", "venex_com_ar":"Venex", "puertominero_com_ar":"Puerto Minero", "quantum_com":"Quantum", "logg_com_ar":"Logg", "maximus_com_ar":"Maximus", "goldentechstore_com_ar":"GoldenTech Store",
}
DOMINIOS_TIENDAS = {
    "katech_com_ar":"katech.com.ar","shopgamer_com_ar":"shopgamer.com.ar","gamingcity_com_ar":"gamingcity.com.ar","insumosacuario_com_ar":"insumosacuario.com.ar","fullh4rd_com_ar":"fullh4rd.com.ar","gezatek_com_ar":"gezatek.com.ar","mymcomputacion_com":"mymcomputacion.com","xt_pc_com_ar":"xt-pc.com.ar","hardcorecomputacion_com_ar":"hardcorecomputacion.com.ar","integradosargentinos_com":"integradosargentinos.com","rockethard_com_ar":"rockethard.com.ar","hypergaming_com_ar":"hypergaming.com.ar","liontech_gaming_com":"liontech-gaming.com","710tech_com_ar":"710tech.com.ar","noxiestore_com":"noxiestore.com","compufanstore_com_ar":"compufanstore.com.ar","armytech_com_ar":"armytech.com.ar","ngtechnologies_com_ar":"ngtechnologies.com.ar","megasoftargentina_com_ar":"megasoftargentina.com.ar","backupcomputacion_com":"backupcomputacion.com","spacegamer_com_ar":"spacegamer.com.ar","portalstore_com_ar":"portalstore.com.ar","slot_one_com_ar":"slot-one.com.ar","gamerfactory_com_ar":"gamerfactory.com.ar","netgaming_ar":"netgaming.ar","necxus_com_ar":"necxus.com.ar","compragamer_com":"compragamer.com","mexx_com_ar":"mexx.com.ar","venex_com_ar":"venex.com.ar","puertominero_com_ar":"puertominero.com.ar","quantum_com":"quantumhardstore.com","logg_com_ar":"logg.com.ar","maximus_com_ar":"maximus.com.ar","goldentechstore_com_ar":"goldentechstore.com.ar",
}

def logo_tienda_url(tienda):
    dominio = DOMINIOS_TIENDAS.get(str(tienda or '').strip())
    return f"https://www.google.com/s2/favicons?domain={quote(dominio)}&sz=128" if dominio else ''

def nombre_tienda_visible(tienda):
    clave = str(tienda or "").strip()
    if clave in NOMBRES_TIENDAS: return NOMBRES_TIENDAS[clave]
    texto = clave
    for sufijo in ("_com_ar", "_com", "_ar", ".com.ar", ".com"):
        if texto.endswith(sufijo): texto = texto[:-len(sufijo)]; break
    return " ".join(p.capitalize() for p in texto.replace("_", " ").replace("-", " ").split())

def normalizar_texto(texto):
    texto = str(texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")

CATEGORIAS = [("Placas de video",("rtx","gtx","rx ","radeon","geforce","arc ","placa de video","tarjeta grafica","gpu","vga ")), ("Procesadores",("procesador","cpu","ryzen","core i3","core i5","core i7","core i9","core ultra","intel xeon","threadripper","athlon","pentium","celeron")), ("Motherboards",("motherboard","mother","placa madre","mainboard","a520","a620","b450","b550","b650","b750","b850","x570","x670","x870","z690","z790","z890","h610","h670","h770","h810")), ("Memorias RAM",("memoria ram","ram ddr","ddr3","ddr4","ddr5","sodimm","dimm ")), ("Almacenamiento",("ssd","nvme","m.2","disco rigido","disco duro","hdd","sata","hard disk","pendrive","memoria usb")), ("Fuentes",("fuente de alimentacion","fuente atx","fuente modular","fuente 80","psu ","power supply")), ("Gabinetes",("gabinete","case pc","chasis pc","tower ","mid tower","full tower")), ("Refrigeración",("watercooler","water cooling","watercooling","cooler cpu","disipador","refrigeracion","fan ","ventilador pc","pasta termica")), ("Monitores",("monitor","monitores","display ","pantalla ","ultrawide")), ("Notebooks",("notebook","laptop","ultrabook")), ("PC armadas",("pc armada","computadora gamer","pc gamer","desktop gamer","pc de escritorio","all in one","aio ")), ("Teclados",("teclado","keyboard")), ("Mouse",("mouse","raton","mause")), ("Auriculares",("auricular","headset","headphone","earbuds")), ("Micrófonos",("microfono","mic ","microphone")), ("Webcams",("webcam","camara web","camara usb")), ("Joysticks y controles",("joystick","gamepad","control xbox","control ps5","dualshock","dualsense","game controller")), ("Impresoras",("impresora","multifuncion","laserjet","inkjet")), ("Redes y WiFi",("router","wifi","wi-fi","access point","switch de red","switch gigabit","repetidor","mesh","placa de red","adaptador wifi")), ("Accesorios",("hub usb","adaptador","cable hdmi","cable displayport","cable usb","lector de tarjetas","dock ","soporte de monitor","soporte notebook"))]

def categoria_producto(producto):
    explicita = str(producto.get("categoria") or "").strip()
    if explicita: return explicita
    nombre = normalizar_texto(producto.get("nombre", "")); reglas = dict(CATEGORIAS)
    for categoria in ["PC armadas"] + [n for n,_ in CATEGORIAS if n != "PC armadas"]:
        if any(token in nombre for token in reglas.get(categoria, ())): return categoria
    return "Otros"

def construir_categorias(productos):
    conteo = {}
    for p in productos: conteo[categoria_producto(p)] = conteo.get(categoria_producto(p),0)+1
    orden = [n for n,_ in CATEGORIAS]+["Otros"]
    return [{"nombre":n,"productos":conteo[n]} for n in orden if conteo.get(n)]

def _cargar_datos(path, default):
    ahora = time.time(); cache_key = path
    with _data_cache_lock:
        cached = _data_cache.get(cache_key)
        if cached and ahora-cached[0] < DATA_CACHE_TTL: return cached[1]
    data = default
    if DATA_BASE_URL:
        try:
            r=requests.get(f"{DATA_BASE_URL}/{path}",timeout=20,headers={"User-Agent":"TecnoRadar/1.0"}); r.raise_for_status(); data=r.json()
        except Exception: data=default
    if data is default:
        try:
            with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        except Exception: data=default
    with _data_cache_lock: _data_cache[cache_key]=(ahora,data)
    return data

def cargar_productos(): return _cargar_datos("productos.json",[])
def clave_producto(producto):
    estable=str(producto.get("id_producto") or producto.get("url") or "").strip() or f"{producto.get('tienda','')}|{producto.get('nombre','')}"
    return sha256(estable.encode("utf-8")).hexdigest()[:20]
def cargar_json_seguro(path,default): return _cargar_datos(path,default)
def guardar_json_seguro(path,data):
    if os.environ.get("TECNORADAR_READ_ONLY","0")=="1": return
    tmp=f"{path}.tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
    os.replace(tmp,path)
    with _data_cache_lock: _data_cache[path]=(time.time(),data)

def extraer_detalle_en_vivo(url):
    resultado={"ok":False,"precio":None,"descripcion":"","imagen":None,"verificado_en":None,"error":None}
    if not url: resultado["error"]="Producto sin URL"; return resultado
    try:
        r=requests.get(url,headers=IMAGEN_HEADERS,timeout=10,allow_redirects=True); resultado["verificado_en"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if r.status_code!=200: resultado["error"]=f"HTTP {r.status_code}"; return resultado
    except requests.RequestException as exc: resultado["error"]=str(exc); return resultado
    soup=BeautifulSoup(r.text,"html.parser"); precios=[]; descripciones=[]; imagenes=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(script.string or script.get_text())
        except Exception: continue
        pila=data if isinstance(data,list) else [data]
        while pila:
            obj=pila.pop()
            if isinstance(obj,dict):
                tipo=obj.get("@type"); tipos=tipo if isinstance(tipo,list) else [tipo]
                if "Product" in tipos:
                    if obj.get("description"): descripciones.append(str(obj["description"]))
                    image=obj.get("image") or obj.get("thumbnailUrl"); imagenes.extend(image if isinstance(image,list) else [image])
                    offers=obj.get("offers"); offs=offers if isinstance(offers,list) else [offers]
                    for offer in offs:
                        if isinstance(offer,dict) and offer.get("price") is not None: precios.append(offer.get("price"))
                for value in obj.values():
                    if isinstance(value,(dict,list)): pila.append(value)
            elif isinstance(obj,list): pila.extend(obj)
    for selector in ('meta[property="product:price:amount"]','meta[itemprop="price"]'):
        for node in soup.select(selector):
            if node.get("content") is not None: precios.append(node.get("content"))
    for selector in ('.price','.precio','[itemprop="price"]','.product-price','.special-price','.current-price'):
        for node in soup.select(selector)[:5]: precios.append(node.get("content") or node.get_text(" ",strip=True))
    for selector in ('meta[name="description"]','meta[property="og:description"]'):
        node=soup.select_one(selector)
        if node and node.get("content"): descripciones.append(node["content"])
    for selector in (".description",".product-description","#description",'[itemprop="description"]',".descripcion"):
        node=soup.select_one(selector)
        if node:
            texto=node.get_text(" ",strip=True)
            if len(texto)>=20: descripciones.append(texto)
    for selector in ('meta[property="og:image"]','meta[name="twitter:image"]'):
        node=soup.select_one(selector)
        if node and node.get("content"): imagenes.append(node["content"])
    try:
        from extractores.utils import parse_precio_ar
        for candidato in precios:
            valor=parse_precio_ar(candidato)
            if valor and 100<=valor<=500_000_000: resultado["precio"]=valor; break
    except Exception: pass
    if descripciones: resultado["descripcion"]=re.sub(r"\s+"," ",max((d.strip() for d in descripciones if d and d.strip()),key=len,default=""))
    for img in imagenes:
        img=_imagen_candidata(img,r.url)
        if img: resultado["imagen"]=img; break
    resultado["ok"]=True; return resultado

def cargar_historial(): return cargar_json_seguro("historial_precios.json",{})
def cargar_detalles(): return cargar_json_seguro("detalles_productos.json",{})
def formatear_fecha_verificacion(fecha): return "Sin verificación" if not fecha else str(fecha).replace("T"," ")[:16]
def registrar_verificacion(producto,precio,stock=None,fuente="web"):
    if not precio or precio<=0:return
    historial=cargar_historial(); key=clave_producto(producto); serie=historial.setdefault(key,[]); ahora=datetime.now()
    entrada={"fecha":ahora.strftime("%Y-%m-%dT%H:%M:%S"),"precio":int(precio),"stock":int(stock) if isinstance(stock,(int,float)) else stock,"fuente":fuente}
    guardar=False
    if not serie: guardar=True
    else:
        ultimo=serie[-1]; ultima_fecha=None
        try: ultima_fecha=datetime.fromisoformat(ultimo.get("fecha",""))
        except Exception: pass
        if ultimo.get("precio")!=int(precio) or (ultima_fecha and ahora-ultima_fecha>=timedelta(hours=24)): guardar=True
    if guardar: serie.append(entrada); historial[key]=serie[-180:]; guardar_json_seguro("historial_precios.json",historial)

@app.route("/")
def inicio():
    productos=cargar_productos(); busqueda=request.args.get("q","").strip(); precio_min=request.args.get("precio_min","").strip(); precio_max=request.args.get("precio_max","").strip(); solo_stock=request.args.get("solo_stock")=="1"; tienda_filtro=request.args.get("tienda","").strip(); categoria_filtro=request.args.get("categoria","").strip(); orden=request.args.get("orden","menor")
    if busqueda:
        consulta=normalizar_texto(busqueda); tokens=[t for t in consulta.split() if len(t)>=2]; resultados=[p for p in productos if consulta in normalizar_texto(p.get("nombre","")) or all(token in normalizar_texto(p.get("nombre","")) for token in tokens)]
    elif tienda_filtro or categoria_filtro: resultados=list(productos)
    else: resultados=[]
    if tienda_filtro: resultados=[p for p in resultados if p.get("tienda")==tienda_filtro]
    if categoria_filtro: resultados=[p for p in resultados if categoria_producto(p)==categoria_filtro]
    if precio_min:
        try: resultados=[p for p in resultados if p.get("precio",0)>=float(precio_min)]
        except ValueError: pass
    if precio_max:
        try: resultados=[p for p in resultados if p.get("precio",0)<=float(precio_max)]
        except ValueError: pass
    if solo_stock: resultados=[p for p in resultados if p.get("stock",0)>0]
    resultados.sort(key=lambda p:p.get("precio",999999999),reverse=orden=="mayor")

    tiendas=set(p.get("tienda") for p in productos if p.get("tienda"))
    # La UI muestra tanto tiendas con datos como tiendas configuradas/activas.
    # Para estas últimas el contador es 0 hasta que el extractor cargue productos.
    tiendas |= set(NOMBRES_TIENDAS)
    conteo_tiendas={t:0 for t in tiendas}
    for p in productos:
        t=p.get("tienda")
        if t: conteo_tiendas[t]=conteo_tiendas.get(t,0)+1
    tiendas_info=[{"clave":t,"nombre":nombre_tienda_visible(t),"productos":conteo_tiendas.get(t,0)} for t in tiendas]
    tiendas_info.sort(key=lambda x:(-x["productos"],x["nombre"].lower()))
    tiendas_principales=tiendas_info[:8]; tiendas_restantes=tiendas_info[8:]
    categorias=construir_categorias(productos)
    candidatas=[]
    for p in productos:
        precio=p.get("precio") or 0; nombre=str(p.get("nombre") or "").strip()
        if not nombre or not precio or precio<=0: continue
        score=(40 if p.get("stock") else 0)+(30 if imagen_utilizable(p.get("imagen")) else 0)+(10 if p.get("url") else 0)+(5 if len(nombre)<=100 else 0)
        candidatas.append((score,nombre_tienda_visible(p.get("tienda")),nombre.lower(),p))
    candidatas.sort(key=lambda x:(-x[0],x[1].lower(),x[2])); destacados=[]; tiendas_destacadas=set()
    for _,_,_,p in candidatas:
        t=p.get("tienda")
        if t and t in tiendas_destacadas: continue
        destacados.append(p)
        if t: tiendas_destacadas.add(t)
        if len(destacados)>=12: break
    if len(destacados)<12:
        usados={id(p) for p in destacados}
        for _,_,_,p in candidatas:
            if id(p) not in usados: destacados.append(p)
            if len(destacados)>=12: break
    try: ultima_actualizacion=datetime.fromtimestamp(os.path.getmtime("productos.json")).strftime("%d/%m/%Y %H:%M")
    except OSError: ultima_actualizacion="Sin información"
    total_productos=len(productos); total_tiendas=len(tiendas)
    ofertas=[p for p in productos if p.get("precio_anterior") and p.get("precio") and p.get("precio_anterior")>p.get("precio")]
    for p in ofertas:
        try:p["descuento_pct"]=round((1-float(p["precio"])/float(p["precio_anterior"]))*100)
        except Exception:p["descuento_pct"]=0
    ofertas.sort(key=lambda p:(-p.get("descuento_pct",0),p.get("precio",999999999))); ofertas=ofertas[:12]
    categorias_populares=sorted(categorias,key=lambda x:x["productos"],reverse=True)[:8]
    historial=cargar_historial(); ultima_verificacion={}
    for p in productos:
        serie=historial.get(clave_producto(p),[]); ultima_verificacion[clave_producto(p)]=formatear_fecha_verificacion(serie[-1].get("fecha")) if serie else "Sin verificación"
    return render_template("index.html",productos=resultados,busqueda=busqueda,precio_min=precio_min,precio_max=precio_max,solo_stock=solo_stock,tienda_filtro=tienda_filtro,categoria_filtro=categoria_filtro,orden=orden,tiendas=sorted(tiendas),categorias=categorias,tiendas_info=tiendas_info,tiendas_principales=tiendas_principales,tiendas_restantes=tiendas_restantes,logo_tienda_url=logo_tienda_url,destacados=destacados,destacado_principal=(destacados[0] if destacados else None),nombre_tienda_visible=nombre_tienda_visible,imagen_utilizable=imagen_utilizable,ultima_actualizacion=ultima_actualizacion,total_productos=total_productos,total_tiendas=total_tiendas,ofertas=ofertas,categorias_populares=categorias_populares,clave_producto=clave_producto,historial=historial,ultima_verificacion=ultima_verificacion)

@app.route("/producto/<codigo>")
def producto_detalle(codigo):
    productos=cargar_productos(); producto=next((p for p in productos if clave_producto(p)==codigo),None)
    if not producto:return ("Producto no encontrado",404)
    detalles=cargar_detalles(); key=clave_producto(producto); detalle=detalles.get(key,{})
    vivo=extraer_detalle_en_vivo(producto.get("url"))
    if vivo.get("ok"):
        if vivo.get("descripcion"): detalle["descripcion"]=vivo["descripcion"]
        if vivo.get("imagen"): detalle["imagen"]=vivo["imagen"]; producto["imagen"]=vivo["imagen"]
        if vivo.get("precio"): detalle["precio_verificado"]=vivo["precio"]; detalle["verificado_en"]=vivo.get("verificado_en"); registrar_verificacion(producto,vivo["precio"],producto.get("stock"),"detalle_web")
        detalles[key]=detalle; guardar_json_seguro("detalles_productos.json",detalles)
    historial=cargar_historial().get(key,[])
    return render_template("producto.html",producto=producto,detalle=detalle,historial=historial,categorias=construir_categorias(productos),categoria_filtro="",nombre_tienda_visible=nombre_tienda_visible,imagen_utilizable=imagen_utilizable,clave_producto=clave_producto)

@app.route("/health")
def health(): return {"ok":True,"servicio":"TecnoRadar","productos":len(cargar_productos())}
@app.route("/resolver-imagen")
def resolver_imagen():
    imagen=request.args.get("imagen","").strip(); producto_url=request.args.get("producto","").strip()
    if imagen_utilizable(imagen): return redirect(imagen,code=302)
    encontrada=_extraer_imagen_producto(producto_url)
    if encontrada:return redirect(encontrada,code=302)
    return ("",404)
@app.route("/salud")
def salud():
    path="config/salud_tiendas.json"
    if not os.path.exists(path):return {"estado":"SIN_EJECUCION","tiendas":{}}
    try:
        with open(path,"r",encoding="utf-8") as f:return {"estado":"OK","tiendas":json.load(f)}
    except Exception as exc:return {"estado":"ERROR","error":str(exc)}
if __name__=="__main__": app.run(host="127.0.0.1",port=5000,debug=False)
