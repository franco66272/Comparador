"""
Motor central del comparador de precios.

Ejecuta tiendas, valida resultados y genera productos.json. Los extractores
parciales no reemplazan catálogos sanos.
"""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from extractores import logg, maximus, quantum
from validacion.validar import validar_resultado

RAIZ = Path(__file__).parent
SPIDERS_SCRAPY = ["compragamer", "mexx", "venex", "puertominero"]
AUTO_TIMEOUT = 420
SCRAPY_TIMEOUT = 3600
AUTO_LOG_DIR = RAIZ / "logs_auto"
SCRAPY_DIR = RAIZ / "scraper"


def correr_spider_scrapy(nombre):
    salida_tmp = RAIZ / f"{nombre}_tmp.json"
    log_path = AUTO_LOG_DIR / f"{nombre}_scrapy.log"
    AUTO_LOG_DIR.mkdir(exist_ok=True)
    salida_tmp.unlink(missing_ok=True)
    cmd = [sys.executable, "-m", "scrapy", "crawl", nombre, "-O", str(salida_tmp)]
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(
                cmd,
                cwd=SCRAPY_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=SCRAPY_TIMEOUT,
            )
    except subprocess.TimeoutExpired:
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Timeout ejecutando spider ({SCRAPY_TIMEOUT}s). Log: logs_auto/{nombre}_scrapy.log"]}
    except FileNotFoundError:
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": ["Comando Scrapy no encontrado"]}
    if proc.returncode != 0 or not salida_tmp.exists():
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Spider falló (exit {proc.returncode}). Log: logs_auto/{nombre}_scrapy.log"]}
    try:
        productos = json.loads(salida_tmp.read_text(encoding="utf-8"))
    except Exception as exc:
        productos = []
        warnings = [f"JSON del spider inválido: {exc}", f"Log: logs_auto/{nombre}_scrapy.log"]
    else:
        warnings = [f"Log detallado: logs_auto/{nombre}_scrapy.log"]
    salida_tmp.unlink(missing_ok=True)
    return {"ok": bool(productos), "tienda": nombre, "productos": productos, "warnings": warnings}


def correr_extractor_auto(extractor, nombre):
    AUTO_LOG_DIR.mkdir(exist_ok=True)
    salida_tmp = RAIZ / f".auto_{nombre}_resultado.json"
    log_path = AUTO_LOG_DIR / f"{nombre}.log"
    salida_tmp.unlink(missing_ok=True)
    cmd = [sys.executable, "-m", "extractores.runner_auto", extractor, str(salida_tmp)]
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT, text=True, timeout=AUTO_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Extractor detenido por timeout ({AUTO_TIMEOUT}s)."]}
    except Exception as exc:
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"No se pudo ejecutar: {exc}"]}
    if not salida_tmp.exists():
        return {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Extractor terminó sin resultado (exit {proc.returncode})."]}
    try:
        resultado = json.loads(salida_tmp.read_text(encoding="utf-8"))
    except Exception as exc:
        resultado = {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Resultado inválido: {exc}"]}
    finally:
        salida_tmp.unlink(missing_ok=True)
    resultado.setdefault("warnings", [])
    resultado["warnings"].append(f"Log detallado: logs_auto/{nombre}.log")
    return resultado


def procesar_tienda(nombre_archivo, resultado, reportes, resultados):
    path_json = RAIZ / f"{nombre_archivo}.json"
    productos, reporte = validar_resultado(resultado, path_json)
    resultados[nombre_archivo] = productos
    reportes.append(reporte)
    path_json.write_text(json.dumps(productos, ensure_ascii=False, indent=2), encoding="utf-8")


def actualizar_historial(todos):
    path = RAIZ / "historial_precios.json"
    try:
        historial = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        historial = {}

    def clave(producto):
        estable = str(producto.get("id_producto") or producto.get("url") or "").strip() or f"{producto.get('tienda','')}|{producto.get('nombre','')}"
        import hashlib
        return hashlib.sha256(estable.encode("utf-8")).hexdigest()[:20]

    ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cambios = 0
    for producto in todos:
        precio = producto.get("precio")
        if not isinstance(precio, (int, float)) or precio <= 0:
            continue
        key = clave(producto)
        serie = historial.setdefault(key, [])
        if not serie or int(serie[-1].get("precio", 0)) != int(precio):
            serie.append({"fecha": ahora, "precio": int(precio), "stock": producto.get("stock"), "fuente": "actualización_automática"})
            historial[key] = serie[-180:]
            cambios += 1
    path.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")
    return cambios


def main():
    inicio = time.time()
    resultados = {}
    reportes = []

    for nombre in SPIDERS_SCRAPY:
        print(f"[{nombre}] extrayendo (scrapy)...")
        procesar_tienda(nombre, correr_spider_scrapy(nombre), reportes, resultados)

    print("[quantum] extrayendo...")
    procesar_tienda("quantum", quantum.extraer(), reportes, resultados)
    print("[logg] extrayendo...")
    procesar_tienda("logg", logg.extraer(), reportes, resultados)
    print("[maximus] extrayendo...")
    procesar_tienda("maximus", maximus.extraer(), reportes, resultados)

    registro_path = RAIZ / "config" / "tiendas_auto.json"
    if registro_path.exists():
        try:
            tiendas_auto = json.loads(registro_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[AUTO] No se pudo leer el registro: {exc}")
            tiendas_auto = {}
        pendientes = []
        for nombre, config in tiendas_auto.items():
            if config.get("estado") != "activo" or nombre in resultados:
                continue
            extractor = config.get("extractor")
            if extractor:
                pendientes.append((nombre, extractor))
        workers = min(8, max(1, len(pendientes)))
        futuros = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for nombre, extractor in pendientes:
                print(f"[auto:{nombre}] encolado...")
                futuros[pool.submit(correr_extractor_auto, extractor, nombre)] = nombre
            for futuro in as_completed(futuros):
                nombre = futuros[futuro]
                try:
                    resultado_auto = futuro.result()
                except Exception as exc:
                    resultado_auto = {"ok": False, "tienda": nombre, "productos": [], "warnings": [f"Error: {exc}"]}
                print(f"[auto:{nombre}] {len(resultado_auto.get('productos', []))} productos | cobertura={resultado_auto.get('coverage', 'n/a')}")
                procesar_tienda(nombre, resultado_auto, reportes, resultados)

    health_path = RAIZ / "config" / "salud_tiendas.json"
    salud = {}
    ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
    for reporte in reportes:
        salud[reporte["tienda"]] = {
            "salud": reporte.get("salud", "UNKNOWN"),
            "completitud": reporte.get("completitud", "baja"),
            "ultima_ejecucion": ahora,
            "productos": reporte.get("productos", 0),
            "productos_nuevos": reporte.get("productos_nuevos", 0),
            "productos_actualizados": reporte.get("productos_actualizados", 0),
            "productos_eliminados": reporte.get("productos_eliminados", 0),
            "expected_product_urls": reporte.get("expected_product_urls"),
            "extracted_product_urls": reporte.get("extracted_product_urls"),
            "coverage": reporte.get("coverage"),
            "fuente": reporte.get("fuente"),
            "warnings": reporte.get("warnings", []),
        }
    health_path.parent.mkdir(exist_ok=True)
    health_path.write_text(json.dumps(salud, ensure_ascii=False, indent=2), encoding="utf-8")

    todos = []
    for lista in resultados.values():
        todos.extend(lista)
    marca_actualizacion = time.strftime("%Y-%m-%dT%H:%M:%S")
    for producto in todos:
        producto["actualizado_en"] = marca_actualizacion
    (RAIZ / "productos.json").write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")

    cambios_historial = actualizar_historial(todos)
    tiempo = time.time() - inicio
    print("=" * 60)
    print(f"RESUMEN — {tiempo:.1f}s")
    print("=" * 60)
    for r in reportes:
        cobertura = r.get("coverage")
        cobertura_txt = f" | cobertura={cobertura:.1%}" if isinstance(cobertura, (int, float)) else ""
        print(f"[{r.get('salud', 'UNKNOWN')}] {r['tienda']}: {r.get('productos', 0)} productos | +{r.get('productos_nuevos', 0)} | ~{r.get('productos_actualizados', 0)} | -{r.get('productos_eliminados', 0)}{cobertura_txt}")
        for warning in r.get("warnings", []):
            print(f"    WARNING: {warning}")
    print("-" * 60)
    print(f"TOTAL: {len(todos)} productos -> productos.json")
    print(f"CAMBIOS DE HISTORIAL: {cambios_historial}")


if __name__ == "__main__":
    main()
