"""
Motor central del comparador de precios.

Ejecuta todas las tiendas, valida cada resultado (sin destruir catálogos
buenos si una tienda falla o cae de forma sospechosa), y genera productos.json.

Uso:
    python actualizar.py

Reglas respetadas:
    - CompraGamer / Mexx / Venex / Puerto Minero: NO se tocan, siguen
      corriendo por sus spiders de Scrapy existentes (`scrapy crawl <nombre>`).
    - Quantum: extractor catalog-based (extractores/quantum.py).
    - Logg: extractor propio (extractores/logg.py).
    - Maximus: extractor mediante API interna (extractores/maximus.py).
    - Si una tienda falla, se usa su último JSON válido; no tira abajo
      todo el proceso.
"""

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from extractores import logg, maximus, quantum
from validacion.validar import validar_resultado

RAIZ = Path(__file__).parent

# Nombres de spiders tal como aparecen en `scrapy list`
SPIDERS_SCRAPY = ["compragamer", "mexx", "venex", "puertominero"]


def correr_spider_scrapy(nombre):
    """
    Corre un spider de Scrapy ya existente y devuelve el resultado en el
    mismo formato estándar que usan los extractores nuevos, para poder
    pasarlo por el mismo validador.
    """
    salida_tmp = RAIZ / f"{nombre}_tmp.json"

    if salida_tmp.exists():
        salida_tmp.unlink()

    cmd = [sys.executable, "-m", "scrapy", "crawl", nombre, "-o", str(salida_tmp)]

    try:
        proc = subprocess.run(
            cmd,
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=240,
        )

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": ["Timeout ejecutando spider"],
        }

    except FileNotFoundError:
        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [
                "Comando 'scrapy' no encontrado (¿venv activado?)"
            ],
        }

    if proc.returncode != 0 or not salida_tmp.exists():
        error = proc.stderr[-500:] if proc.stderr else "sin detalle"

        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [
                f"Spider falló (exit {proc.returncode}): {error}"
            ],
        }

    with open(salida_tmp, "r", encoding="utf-8") as f:
        try:
            productos = json.load(f)
        except json.JSONDecodeError:
            productos = []

    salida_tmp.unlink()

    return {
        "ok": len(productos) > 0,
        "tienda": nombre,
        "productos": productos,
        "warnings": [],
    }



AUTO_TIMEOUT = 150
AUTO_LOG_DIR = RAIZ / "logs_auto"


def correr_extractor_auto(extractor, nombre):
    """
    Ejecuta cada extractor automático en un proceso separado.
    Un extractor colgado puede ser terminado sin bloquear el comparador.
    """
    AUTO_LOG_DIR.mkdir(exist_ok=True)
    salida_tmp = RAIZ / f".auto_{nombre}_resultado.json"
    log_path = AUTO_LOG_DIR / f"{nombre}.log"

    if salida_tmp.exists():
        salida_tmp.unlink()

    cmd = [
        sys.executable,
        "-m",
        "extractores.runner_auto",
        extractor,
        str(salida_tmp),
    ]

    try:
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(
                cmd,
                cwd=RAIZ,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=AUTO_TIMEOUT,
            )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [
                f"Extractor detenido por timeout ({AUTO_TIMEOUT}s)."
            ],
        }
    except Exception as exc:
        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [f"No se pudo ejecutar el extractor: {exc}"],
        }

    if not salida_tmp.exists():
        return {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [
                f"El extractor terminó sin devolver resultado (exit {proc.returncode})."
            ],
        }

    try:
        resultado = json.loads(
            salida_tmp.read_text(encoding="utf-8")
        )
    except Exception as exc:
        resultado = {
            "ok": False,
            "tienda": nombre,
            "productos": [],
            "warnings": [f"Resultado inválido: {exc}"],
        }
    finally:
        salida_tmp.unlink(missing_ok=True)

    resultado.setdefault("warnings", [])
    resultado["warnings"].append(
        f"Log detallado: logs_auto/{nombre}.log"
    )
    return resultado


def procesar_tienda(
    nombre_archivo,
    resultado,
    reportes,
    resultados,
):
    """
    Valida el catálogo nuevo contra el catálogo anterior.

    Si la extracción falla o devuelve una cantidad sospechosa,
    validar_resultado puede conservar el catálogo anterior.
    """

    path_json = RAIZ / f"{nombre_archivo}.json"

    productos, reporte = validar_resultado(
        resultado,
        path_json,
    )

    resultados[nombre_archivo] = productos
    reportes.append(reporte)

    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(
            productos,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():

    inicio = time.time()

    resultados = {}
    reportes = []

    # --------------------------------------------------
    # SCRAPY
    # --------------------------------------------------

    for nombre in SPIDERS_SCRAPY:

        print(f"[{nombre}] extrayendo (scrapy)...")

        resultado = correr_spider_scrapy(nombre)

        procesar_tienda(
            nombre,
            resultado,
            reportes,
            resultados,
        )

    # --------------------------------------------------
    # QUANTUM
    # --------------------------------------------------

    print("[quantum] extrayendo (catalog-based)...")

    procesar_tienda(
        "quantum",
        quantum.extraer(),
        reportes,
        resultados,
    )

    # --------------------------------------------------
    # LOGG
    # --------------------------------------------------

    print("[logg] extrayendo (requests + paginación real)...")

    procesar_tienda(
        "logg",
        logg.extraer(),
        reportes,
        resultados,
    )

    # --------------------------------------------------
    # MAXIMUS
    # --------------------------------------------------

    print("[maximus] extrayendo (API interna + paginación)...")

    procesar_tienda(
        "maximus",
        maximus.extraer(),
        reportes,
        resultados,
    )

    # --------------------------------------------------
    # TIENDAS DESCUBIERTAS AUTOMÁTICAMENTE
    # --------------------------------------------------

    registro_path = RAIZ / "config" / "tiendas_auto.json"

    if registro_path.exists():

        try:
            with open(registro_path, "r", encoding="utf-8") as f:
                tiendas_auto = json.load(f)
        except Exception as exc:
            print(
                f"[AUTO] No se pudo leer el registro: {exc}"
            )
            tiendas_auto = {}

        pendientes = []
        for nombre, config in tiendas_auto.items():
            if config.get("estado") != "activo":
                continue
            if nombre in resultados:
                continue
            extractor = config.get("extractor")
            if extractor:
                pendientes.append((nombre, extractor))

        # Los extractores automáticos están aislados en procesos propios.
        # Ejecutarlos en paralelo evita que una actualización de 25-30 tiendas
        # tarde horas de forma secuencial.
        workers = min(5, max(1, len(pendientes)))
        futuros = {}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for nombre, extractor in pendientes:
                print(f"[auto:{nombre}] encolado...")
                futuros[pool.submit(
                    correr_extractor_auto, extractor, nombre
                )] = nombre

            for futuro in as_completed(futuros):
                nombre = futuros[futuro]
                try:
                    resultado_auto = futuro.result()
                except Exception as exc:
                    resultado_auto = {
                        "ok": False,
                        "tienda": nombre,
                        "productos": [],
                        "warnings": [f"Error ejecutando extractor: {exc}"],
                    }

                print(
                    f"[auto:{nombre}] resultado: "
                    f"{len(resultado_auto.get('productos', []))} productos"
                )

                procesar_tienda(
                    nombre,
                    resultado_auto,
                    reportes,
                    resultados,
                )

    # --------------------------------------------------
    # ESTADO DE SALUD
    # --------------------------------------------------

    health_path = RAIZ / "config" / "salud_tiendas.json"
    health_path.parent.mkdir(exist_ok=True)
    salud = {}
    for reporte in reportes:
        salud[reporte["tienda"]] = {
            "salud": reporte.get("salud", "UNKNOWN"),
            "completitud": reporte.get("completitud", "baja"),
            "ultima_ejecucion": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "productos": reporte.get("productos", 0),
            "productos_nuevos": reporte.get("productos_nuevos", 0),
            "productos_actualizados": reporte.get("productos_actualizados", 0),
            "productos_eliminados": reporte.get("productos_eliminados", 0),
            "fuente": reporte.get("fuente"),
            "warnings": reporte.get("warnings", []),
        }
    health_path.write_text(
        json.dumps(salud, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --------------------------------------------------
    # UNIFICAR
    # --------------------------------------------------

    todos = []

    for lista in resultados.values():
        todos.extend(lista)

    with open(
        RAIZ / "productos.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            todos,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------
    # RESUMEN
    # --------------------------------------------------

    tiempo = time.time() - inicio

    print()
    print("=" * 50)
    print(f"RESUMEN — {tiempo:.1f}s")
    print("=" * 50)

    for r in reportes:

        estado = r.get("salud") or ("HEALTHY" if r["ok"] else "FAILED")

        print(
            f"[{estado}] {r['tienda']}: "
            f"{r['productos']} productos | "
            f"+{r.get('productos_nuevos', 0)} nuevos | "
            f"~{r.get('productos_actualizados', 0)} actualizados | "
            f"-{r.get('productos_eliminados', 0)} eliminados"
        )

        for w in r["warnings"]:
            print(f"    WARNING: {w}")

    print("-" * 50)

    print(
        f"TOTAL: {len(todos)} productos "
        f"-> productos.json"
    )


if __name__ == "__main__":
    main()