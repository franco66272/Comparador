"""HardGamers historical-price import and local history management."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "productos.json"
HISTORY = ROOT / "historial_precios.json"
REPORT = ROOT / "logs_auto" / "hardgamers_historial.json"
DEBUG = ROOT / "logs_auto" / "hardgamers_debug.json"
BASE = "https://www.hardgamers.com.ar"
HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36", "Accept-Language":"es-AR,es;q=0.9"}
TIMEOUT = 30
PAUSE = 0.2
MAX_429 = 4
DATE_KEYS = ("fecha","date","datetime","timestamp","time","created_at","createdAt","day","x","t")
PRICE_KEYS = ("precio","price","value","amount","valor","cost","y","v")
CHART_CONFIG_RE = re.compile(r"\b(?:var|let|const)\s+chartConfig\s*=\s*", re.I)


def product_key(p):
    stable = str(p.get("id_producto") or p.get("url") or "").strip() or f"{p.get('tienda','')}|{p.get('nombre','')}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def hg_url(p):
    ident = str(p.get("id_producto") or "").strip()
    if not ident.startswith("venex:"):
        return None
    return f"{BASE}/product/{quote(ident, safe=':')}"


def parse_price(v):
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


def is_date(v):
    if isinstance(v, (int,float)): return v > 1_000_000_000
    s = str(v or "").strip()
    return bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s) or re.match(r"^\d{10,13}$", s) or re.search(r"\b20\d{2}[-/]\d{1,2}\b", s))


def norm_date(v):
    if isinstance(v,(int,float)) and v > 1_000_000_000:
        try: return datetime.fromtimestamp(float(v)/(1000 if v > 10_000_000_000 else 1)).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception: pass
    s=str(v).strip()
    if s.isdigit() and len(s)>=10:
        try: return datetime.fromtimestamp(int(s)/(1000 if len(s)>=13 else 1)).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception: pass
    return s


def parse_points(obj):
    out=[]
    if isinstance(obj, dict):
        d=next((obj[k] for k in DATE_KEYS if k in obj and obj[k] is not None), None)
        p=next((obj[k] for k in PRICE_KEYS if k in obj and obj[k] is not None), None)
        pv=parse_price(p)
        if d is not None and pv is not None and is_date(d):
            return [{"fecha":norm_date(d),"precio":pv,"stock":None,"fuente":"HardGamers"}]
        for k,v in obj.items():
            if isinstance(v,(dict,list)):
                cand=parse_points(v)
                if len(cand)>len(out): out=cand
        if out: return out
        if obj and all(not isinstance(v,(dict,list)) for v in obj.values()):
            for d,p in obj.items():
                pv=parse_price(p)
                if pv is not None and is_date(d): out.append({"fecha":norm_date(d),"precio":pv,"stock":None,"fuente":"HardGamers"})
            return sorted(out,key=lambda x:x["fecha"])
        return []
    if not isinstance(obj,list): return []
    for item in obj:
        if isinstance(item,dict):
            d=next((item[k] for k in DATE_KEYS if k in item and item[k] is not None),None)
            p=next((item[k] for k in PRICE_KEYS if k in item and item[k] is not None),None)
        elif isinstance(item,(list,tuple)) and len(item)>=2:
            a,b=item[0],item[1]
            d,p=(a,b) if is_date(a) else ((b,a) if is_date(b) else (None,None))
        else: continue
        pv=parse_price(p)
        if d is not None and pv is not None and is_date(d): out.append({"fecha":norm_date(d),"precio":pv,"stock":None,"fuente":"HardGamers"})
    out.sort(key=lambda x:x["fecha"])
    seen=set(); ded=[]
    for x in out:
        sig=(x["fecha"],x["precio"])
        if sig not in seen: seen.add(sig); ded.append(x)
    return ded


def walk(obj, found=None, depth=0):
    found=found if found is not None else []
    if depth>18: return found
    s=parse_points(obj)
    if len(s)>=2: found.append(s)
    if isinstance(obj,dict):
        for v in obj.values():
            if isinstance(v,(dict,list)): walk(v,found,depth+1)
    elif isinstance(obj,list):
        for v in obj:
            if isinstance(v,(dict,list)): walk(v,found,depth+1)
    return found


def extract_text(text):
    if not text: return []
    found=[]
    try: found.extend(walk(json.loads(text)))
    except Exception: pass
    return found


def json_object_after(text, match):
    """Return the JSON object beginning at *match*, without executing page JS."""
    start = text.find("{", match.end())
    if start < 0:
        return None
    depth = 0; quoted = False; escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
            continue
        if char == '"': quoted = True
        elif char == "{": depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:pos + 1])
                except json.JSONDecodeError: return None
    return None


def chart_dates(labels):
    """Chart labels are DD-MM; infer the year from their chronological order."""
    parsed = []
    for label in labels:
        match = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", str(label))
        if not match:
            return []
        parsed.append((int(match.group(1)), int(match.group(2))))
    if not parsed:
        return []
    today = date.today(); year = today.year
    # The final label is the site's current observation.  A year rollover is
    # visible when the chronological sequence goes from December to January.
    try:
        last_this_year = date(year, parsed[-1][1], parsed[-1][0])
    except ValueError:
        return []
    # Allow a small server/time-zone skew; a chart ending tomorrow still
    # belongs to the current year, while a December chart seen in January does not.
    if last_this_year > today + timedelta(days=2): year -= 1
    dates = []
    previous = None
    for day, month in parsed:
        if previous and (month, day) < (previous[1], previous[0]): year += 1
        try: dates.append(date(year, month, day).isoformat())
        except ValueError: return []
        previous = (day, month)
    return dates


def extract_chart_config(text):
    """Extract HardGamers' public inline Chart.js history configuration."""
    for match in CHART_CONFIG_RE.finditer(text or ""):
        config = json_object_after(text, match)
        if not isinstance(config, dict):
            continue
        data = config.get("data")
        if not isinstance(data, dict):
            continue
        labels = data.get("labels"); datasets = data.get("datasets")
        if not isinstance(labels, list) or not isinstance(datasets, list) or not datasets:
            continue
        values = datasets[0].get("data") if isinstance(datasets[0], dict) else None
        dates = chart_dates(labels)
        if not dates or not isinstance(values, list):
            continue
        points = []
        for day, value in zip(dates, values):
            price = parse_price(value)
            if price is not None:
                points.append({"fecha": day, "precio": price, "stock": None, "fuente": "HardGamers (historial público)"})
        if len(points) >= 2:
            return points
    return []


def extract_current_price(soup):
    node = soup.select_one('[itemprop="price"]')
    return parse_price(node.get("content") if node else None)


def merge_points(existing, incoming):
    """Union points safely; never discard a prior history after a failed fetch."""
    valid = [x for x in (existing if isinstance(existing, list) else []) if isinstance(x, dict) and parse_price(x.get("precio"))]
    valid.extend(incoming)
    seen = set(); merged = []
    for point in sorted(valid, key=lambda x: str(x.get("fecha", ""))):
        normalized = dict(point); normalized["precio"] = parse_price(point.get("precio"))
        signature = (str(normalized.get("fecha", "")), normalized["precio"], str(normalized.get("fuente", "")))
        if signature not in seen:
            seen.add(signature); merged.append(normalized)
    return merged[-180:]


def get(session,url):
    for attempt in range(MAX_429+1):
        r=session.get(url,headers=HEADERS,timeout=TIMEOUT)
        if r.status_code!=429:
            r.raise_for_status(); return r
        wait=min(90,5*(2**attempt))
        try: wait=max(wait,float(r.headers.get("Retry-After",0)))
        except ValueError: pass
        time.sleep(wait)
    r.raise_for_status(); return r


def extract_http(url,session):
    r=get(session,url)
    soup=BeautifulSoup(r.text,"lxml")
    candidates=extract_text(r.text)
    chart=extract_chart_config(r.text)
    if chart: candidates.append(chart)
    for sc in soup.find_all("script"):
        txt=sc.string or sc.get_text(" ",strip=False)
        if txt and len(txt)<12_000_000: candidates.extend(extract_text(txt))
    return max(candidates,key=len,default=[]), extract_current_price(soup), {"status":r.status_code,"url":url,"size":len(r.text),"content_type":r.headers.get("Content-Type","")}


def extract_browser(url,browser,debug):
    ctx=browser.new_context(user_agent=HEADERS["User-Agent"],locale="es-AR")
    page=ctx.new_page(); candidates=[]; responses=[]
    def on_response(resp):
        try:
            body=resp.text(); ct=(resp.headers.get("content-type") or "").lower(); low=resp.url.lower()
            interesting="json" in ct or "javascript" in ct or any(x in low for x in ("api","graphql","chart","history","historial","price","precio","data","product"))
            if interesting and len(body)<=10_000_000:
                responses.append({"url":resp.url,"status":resp.status,"content_type":ct,"size":len(body)})
                candidates.extend(extract_text(body))
        except Exception: pass
    page.on("response",on_response)
    try:
        page.goto(url,wait_until="networkidle",timeout=60_000)
        page.wait_for_timeout(2500)
        for txt in page.locator("script").all_text_contents():
            if txt and len(txt)<12_000_000: candidates.extend(extract_text(txt))
        html=page.content(); candidates.extend(extract_text(html))
        debug["responses"]=responses[-300:]
        debug["resources"]=page.evaluate("() => performance.getEntriesByType('resource').map(x=>x.name)")[-500:]
        debug["html_keywords"]=[html[max(0,m.start()-300):m.start()+1500] for m in re.finditer(r"history|historial|price|precio|chart|graph",html,re.I)][:10]
        try: debug["storage"]=page.evaluate("() => ({local:{...localStorage},session:{...sessionStorage}})")
        except Exception: pass
    finally:
        page.close(); ctx.close()
    return max(candidates,key=len,default=[])


def main():
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    try: history=json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    except Exception: history={}
    objectives=[p for p in catalog if str(p.get("tienda","")).strip().lower()=="venex" and hg_url(p)]
    try: limit=int(os.environ.get("HG_MAX_PRODUCTOS","0") or "0")
    except ValueError: limit=0
    if limit>0: objectives=objectives[:limit]
    results={"inicio":datetime.now().isoformat(),"objetivos":len(objectives),"id_directo":len(objectives),"match":len(objectives),"series":0,"series_historicas":0,"puntos":0,"puntos_actuales":0,"fallback_browser":0,"sin_serie":0,"errores":[],"modo":"direct-id-inline-chartconfig-http-playwright-v9"}
    debug={"productos":[]}
    from playwright.sync_api import sync_playwright
    session=requests.Session(); session.headers.update(HEADERS)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for i,p in enumerate(objectives,1):
            url=hg_url(p); key=product_key(p); d={"producto":p.get("nombre"),"url":url}
            try:
                serie,current_price,http=extract_http(url,session); d["http"]=http
                if len(serie)<2:
                    results["fallback_browser"]+=1; serie=extract_browser(url,browser,d)
                if len(serie)>=2:
                    history[key]=merge_points(history.get(key, []), serie)
                    results["series"]+=1; results["series_historicas"]+=1; results["puntos"]+=len(serie); d["serie_puntos"]=len(serie)
                else:
                    results["sin_serie"]+=1; results["errores"].append({"producto":p.get("nombre"),"url":url,"error":"sin_serie"})
                    if current_price is not None:
                        point={"fecha":datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),"precio":current_price,"stock":p.get("stock"),"fuente":"HardGamers (precio actual)"}
                        history[key]=merge_points(history.get(key, []), [point])
                        results["puntos_actuales"]+=1; d["precio_actual"]=current_price
            except Exception as exc:
                results["errores"].append({"producto":p.get("nombre"),"url":url,"error":f"{type(exc).__name__}: {exc}"})
            if len(debug["productos"])<3: debug["productos"].append(d)
            if i%25==0 or i==len(objectives): print(f"[{i}/{len(objectives)}] ids={results['id_directo']} series={results['series']} puntos={results['puntos']} browser={results['fallback_browser']}")
            time.sleep(PAUSE)
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
    REPORT.parent.mkdir(exist_ok=True)
    results["fin"]=datetime.now().isoformat()
    REPORT.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    DEBUG.write_text(json.dumps(debug,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False,indent=2))
    # Distinct result codes let the batch describe the actual outcome.
    if results["series_historicas"] == len(objectives) and not results["errores"]:
        return 0
    if not results["series_historicas"] and results["puntos_actuales"]:
        return 3
    if results["series_historicas"] or results["puntos_actuales"]:
        return 4
    # Completed without usable data: keep prior history and report a warning.
    return 2

if __name__=="__main__": raise SystemExit(main())
