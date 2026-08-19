import json

import requests

URL = "https://www.maximus.com.ar/wfmWebSite2.aspx/wsNRW_Script"
PAGINA_INICIAL = "https://www.maximus.com.ar/Productos/Notebooks/maximus.aspx?/CAT=56/SCAT=-1/M=-1/OR=1/PAGE=1/"
GUID = "a632009a-7686-4fcb-a0b4-24b18caf5234"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"})

print("Estableciendo sesión (GET a la página de categoría)...")
r0 = session.get(PAGINA_INICIAL, timeout=20)
print(f"GET status: {r0.status_code}, cookies obtenidas: {list(session.cookies.keys())}\n")


def call(cat_id=-1, page=1, subcat_id=-1, brand_id=-1):
    params = {
        "ws_id": GUID, "comp_id": 1, "prli_id": 17, "cust_id": -1,
        "page": page, "cat_id": cat_id, "subcat_id": subcat_id, "brand_id": brand_id,
        "local": 0, "search": "", "order": 1, "price_min": "", "price_max": "", "wco_tV": [],
    }
    body = {
        "guidWS_Id": GUID,
        "strScriptLabel": "web.MAX.GetItemList4Search_v3_V6",
        "JSonParameters": json.dumps(params, ensure_ascii=False),
    }
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Referer": PAGINA_INICIAL,
        "Origin": "https://www.maximus.com.ar",
    }
    return session.post(URL, json=body, headers=headers, timeout=20)


resp = call(cat_id=-1, page=1)
print(f"STATUS: {resp.status_code}")

data = resp.json()
d = data.get("d") if isinstance(data, dict) else data
print(f"tipo de d: {type(d)}")
print(f"primeros 300 chars de d: {str(d)[:300]}\n")
if isinstance(d, str):
    d = json.loads(d)

claves = list(d.keys()) if isinstance(d, dict) else type(d)
print(f"Claves del objeto d: {claves}\n")

if isinstance(d, dict):
    items = d.get("items")
    cantidad = len(items) if items else 0
    print(f"items: {type(items)}, cantidad en esta página: {cantidad}")
    if items:
        print("\n--- Primer item completo ---")
        print(json.dumps(items[0], indent=2, ensure_ascii=False))

    for campo in ["total", "totalItems", "total_items", "totalCount", "count", "match"]:
        if campo in d:
            print(f"\n{campo}: {d[campo]}")

    if d.get("categories"):
        cantidad_cat = len(d["categories"])
        print(f"\n--- Categorías ({cantidad_cat}) ---")
        for c in d["categories"][:40]:
            print(f"  {c}")
