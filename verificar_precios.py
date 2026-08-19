"""Verificador incremental de precios oficiales.

Ejecutar periódicamente (por ejemplo cada hora). En cada corrida revisa un lote
limitado de productos para no martillar las tiendas. Registra cambios y conserva
el historial para la gráfica del producto.
"""
import json, os, time, argparse, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from hashlib import sha256
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from extractores.utils import parse_precio_ar

BASE = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS = os.path.join(BASE, "productos.json")
HISTORIAL = os.path.join(BASE, "historial_precios.json")
DETALLES = os.path.join(BASE, "detalles_productos.json")
UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36", "Accept-Language":"es-AR,es;q=0.9"}


def key(p):
    stable=str(p.get('id_producto') or p.get('url') or f"{p.get('tienda','')}|{p.get('nombre','')}")
    return sha256(stable.encode()).hexdigest()[:20]


def load(path, default):
    try:
        with open(path,encoding='utf8') as f:return json.load(f)
    except Exception:return default


def save(path,data):
    tmp=path+'.tmp'
    with open(tmp,'w',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    os.replace(tmp,path)


def read_live(url):
    try:
        r=requests.get(url,headers=UA,timeout=12,allow_redirects=True)
        if r.status_code!=200:return None
    except requests.RequestException:return None
    soup=BeautifulSoup(r.text,'html.parser')

    # Fuente 1: JSON-LD Product -> offers.price
    jsonld_prices=[]
    for s in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(s.string or s.get_text())
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            x=stack.pop()
            if isinstance(x,dict):
                typ=x.get('@type'); typ=typ if isinstance(typ,list) else [typ]
                if 'Product' in typ:
                    offers=x.get('offers'); offers=offers if isinstance(offers,list) else [offers]
                    for off in offers:
                        if isinstance(off,dict) and off.get('price') is not None:
                            jsonld_prices.append(off['price'])
                for v in x.values():
                    if isinstance(v,(dict,list)):stack.append(v)
            elif isinstance(x,list):stack.extend(x)
    for raw in jsonld_prices:
        v=parse_precio_ar(raw)
        if v and 100<=v<=500_000_000:return v

    # Fuente 2: metadatos explícitos del producto.
    for n in soup.select('meta[property="product:price:amount"],meta[itemprop="price"]'):
        v=parse_precio_ar(n.get('content') or '')
        if v and 100<=v<=500_000_000:return v

    # Fuente 3: etiquetas que explícitamente identifican el precio principal.
    texto=soup.get_text(' ',strip=True)
    for patron in (
        r'Precio\s+(?:especial|oferta|actual|promocional)\s*[:：]?\s*\$\s*([\d.]+(?:,\d+)?)',
        r'Precio\s*[:：]?\s*\$\s*([\d.]+(?:,\d+)?)',
    ):
        m=re.search(patron,texto,re.I)
        if m:
            v=parse_precio_ar(m.group(1))
            if v and 100<=v<=500_000_000:return v

    # Fuente 4: selectores dentro del contenedor principal.
    for contenedor in soup.select('main,#content,.product-detail,.product-detail-page,.product,.producto')[:6]:
        for n in contenedor.select('[itemprop=price],.price,.precio,.product-price,.special-price,.current-price,.sale-price')[:15]:
            v=parse_precio_ar(n.get('content') or n.get('data-price') or n.get_text(' ',strip=True))
            if v and 100<=v<=500_000_000:return v
    return None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--lote',type=int,default=40)
    ap.add_argument('--horas',type=float,default=6)
    ap.add_argument('--workers',type=int,default=8)
    args=ap.parse_args()
    productos=load(PRODUCTOS,[]); historial=load(HISTORIAL,{}); detalles=load(DETALLES,{})
    ahora=datetime.now()
    claves=[]
    for p in productos:
        h=historial.get(key(p),[]) if isinstance(historial,dict) else []
        ultimo=None
        if h:
            try:ultimo=datetime.fromisoformat(h[-1].get('fecha',''))
            except Exception:pass
        nombre=str(p.get('nombre') or '')
        precio_actual=int(p.get('precio') or 0)
        monto_en_nombre=None
        m=re.search(r'\$\s*([\d.]+(?:,\d+)?)',nombre)
        if m:
            monto_en_nombre=parse_precio_ar(m.group(1))
        sospechoso=bool(monto_en_nombre and precio_actual==int(monto_en_nombre))
        if sospechoso or ultimo is None or ahora-ultimo>=timedelta(hours=args.horas):
            claves.append(p)
    # Mezclar el lote para evitar favorecer siempre las primeras tiendas.
    claves=claves[:args.lote]
    print(f'Verificando {len(claves)} productos de {len(productos)} pendientes...')
    cambios=0; verificados=0
    with ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
        fut={pool.submit(read_live,p.get('url')):p for p in claves if p.get('url')}
        for f in as_completed(fut):
            p=fut[f]
            precio=f.result()
            if not precio:continue
            verificados+=1
            k=key(p); serie=historial.setdefault(k,[])
            ultimo=serie[-1] if serie else None
            nuevo={'fecha':ahora.strftime('%Y-%m-%dT%H:%M:%S'),'precio':int(precio),'stock':p.get('stock'),'fuente':'verificador'}
            if not ultimo or ultimo.get('precio')!=int(precio) or ahora-datetime.fromisoformat(ultimo['fecha'])>=timedelta(hours=24):
                serie.append(nuevo); historial[k]=serie[-180:]
            if int(precio)!=int(p.get('precio') or 0):
                viejo=int(p.get('precio') or 0)
                p['precio_anterior']=viejo if viejo>0 else p.get('precio_anterior')
                p['precio']=int(precio)
                p['precio_verificado']=int(precio)
                p['verificado_en']=ahora.strftime('%Y-%m-%d %H:%M:%S')
                cambios+=1
                print(f"CAMBIO | {p.get('tienda')} | {p.get('nombre')[:70]} | {viejo} -> {precio}")
    save(HISTORIAL,historial)
    save(PRODUCTOS,productos)
    print(f'Verificados: {verificados} | Diferencias detectadas: {cambios} | productos.json actualizado')

if __name__=='__main__':main()
