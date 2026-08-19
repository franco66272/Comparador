"""Repara precios claramente sospechosos ya almacenados en productos.json.
Solo verifica productos cuyo precio coincide exactamente con un monto incluido en su propio nombre.
"""
import json, re, os
from datetime import datetime
from verificar_precios import read_live, key, load, save, HISTORIAL, PRODUCTOS

BASE=os.path.dirname(os.path.abspath(__file__))
HIST=os.path.join(BASE,"historial_precios.json")
productos=load(PRODUCTOS,[])
historial=load(HIST,{})
ahora=datetime.now()
reparados=0
revisados=0
for p in productos:
    nombre=str(p.get("nombre") or "")
    m=re.search(r"\$\s*([\d.]+(?:,\d+)?)",nombre)
    if not m:
        continue
    try:
        titulo=int(float(m.group(1).replace(".","").replace(",",".")))
    except Exception:
        continue
    if int(p.get("precio") or 0)!=titulo:
        continue
    revisados+=1
    live=read_live(p.get("url")) if p.get("url") else None
    if not live or live==titulo:
        continue
    viejo=int(p.get("precio") or 0)
    p["precio_anterior"]=viejo
    p["precio"]=int(live)
    p["precio_verificado"]=int(live)
    p["verificado_en"]=ahora.strftime("%Y-%m-%d %H:%M:%S")
    k=key(p)
    serie=historial.setdefault(k,[])
    serie.append({"fecha":ahora.strftime("%Y-%m-%dT%H:%M:%S"),"precio":int(live),"stock":p.get("stock"),"fuente":"reparador_sospechosos"})
    historial[k]=serie[-180:]
    reparados+=1
    print(f"REPARADO | {p.get('tienda')} | {nombre[:80]} | {viejo} -> {live}")
save(PRODUCTOS,productos)
save(HIST,historial)
print(f"Revisados: {revisados} | Reparados: {reparados}")
