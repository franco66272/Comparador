"""Validador de catálogos con control de cobertura."""
import json
import os

# Una caída grande de productos es mucho más probable que sea una extracción
# parcial que una reducción real del catálogo. En ese caso se conserva/fusiona.
CAIDA_MAXIMA_PERMITIDA = 0.20
COBERTURA_MINIMA_PUBLICABLE = 0.98
PRECIO_MINIMO_RAZONABLE = 100


def cargar_json_anterior(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []
    return []


def _clave(p):
    return str(p.get("id_producto") or p.get("url") or "").strip()


def _limpiar(productos):
    vistos = set()
    limpios = []
    duplicados = 0
    descartados = 0
    for p in productos or []:
        if not isinstance(p, dict):
            continue
        clave = _clave(p)
        try:
            precio = int(float(p.get("precio")))
        except (TypeError, ValueError):
            precio = 0
        if not clave or precio < PRECIO_MINIMO_RAZONABLE:
            descartados += 1
            continue
        if clave in vistos:
            duplicados += 1
            continue
        vistos.add(clave)
        p["precio"] = precio
        p.setdefault("stock", 0)
        limpios.append(p)
    return limpios, duplicados, descartados


def _merge(anterior, nuevos):
    index = {}
    orden = []
    for p in anterior:
        clave = _clave(p)
        if clave and clave not in index:
            index[clave] = p
            orden.append(clave)
    for p in nuevos:
        clave = _clave(p)
        if not clave:
            continue
        if clave not in index:
            orden.append(clave)
        index[clave] = p
    return [index[k] for k in orden]


def _estadisticas(anterior, nuevos, finales):
    old = {_clave(p): p for p in anterior if _clave(p)}
    new = {_clave(p): p for p in nuevos if _clave(p)}
    nuevos_ids = set(new) - set(old)
    eliminados_ids = set(old) - set(new)
    actualizados_ids = {
        k for k in set(old) & set(new)
        if old[k].get("precio") != new[k].get("precio")
        or old[k].get("stock") != new[k].get("stock")
        or old[k].get("imagen") != new[k].get("imagen")
    }
    return {
        "productos_nuevos": len(nuevos_ids),
        "productos_actualizados": len(actualizados_ids),
        "productos_eliminados": len(eliminados_ids),
        "productos_finales": len(finales),
    }


def _metricas_cobertura(resultado, cantidad_nuevos):
    expected = resultado.get("expected_product_urls")
    extracted = resultado.get("extracted_product_urls")
    coverage = resultado.get("coverage")
    try:
        expected = int(expected) if expected is not None else None
    except (TypeError, ValueError):
        expected = None
    try:
        extracted = int(extracted) if extracted is not None else None
    except (TypeError, ValueError):
        extracted = None
    try:
        coverage = float(coverage) if coverage is not None else None
    except (TypeError, ValueError):
        coverage = None
    if coverage is not None:
        return expected, extracted, max(0.0, min(1.0, coverage))
    if expected and expected > 0 and extracted is not None:
        return expected, extracted, max(0.0, min(1.0, extracted / expected))
    return expected, extracted, None


def validar_resultado(resultado, path_json):
    tienda = resultado.get("tienda") or path_json.stem
    warnings = list(resultado.get("warnings") or [])
    anterior = cargar_json_anterior(path_json)
    cantidad_anterior = len(anterior)
    nuevos, duplicados, descartados = _limpiar(resultado.get("productos") or [])
    if duplicados:
        warnings.append(f"{duplicados} duplicados eliminados")
    if descartados:
        warnings.append(f"{descartados} productos inválidos descartados")

    salud = str(resultado.get("salud") or "").upper()
    completitud = str(resultado.get("completitud") or "").lower()
    expected, extracted, coverage = _metricas_cobertura(resultado, len(nuevos))

    if not resultado.get("ok", False) or not nuevos:
        salud_final = salud or "FAILED"
        if cantidad_anterior:
            warnings.append(f"Extracción no utilizable; se conserva el catálogo anterior ({cantidad_anterior})")
            stats = _estadisticas(anterior, [], anterior)
            return anterior, {
                "ok": False, "tienda": tienda, "productos": cantidad_anterior,
                "salud": salud_final, "completitud": "baja", "fuente": "catalogo_anterior",
                "warnings": warnings, "expected_product_urls": expected,
                "extracted_product_urls": extracted, "coverage": coverage, **stats,
            }
        warnings.append("No existe catálogo anterior para usar como fallback")
        return [], {
            "ok": False, "tienda": tienda, "productos": 0, "salud": salud_final,
            "completitud": "baja", "fuente": "sin_catalogo", "warnings": warnings,
            "expected_product_urls": expected, "extracted_product_urls": extracted,
            "coverage": coverage, "productos_nuevos": 0, "productos_actualizados": 0,
            "productos_eliminados": 0, "productos_finales": 0,
        }

    porcentaje_vs_anterior = (len(nuevos) / cantidad_anterior) if cantidad_anterior else 1.0
    cobertura_insuficiente = coverage is not None and coverage < COBERTURA_MINIMA_PUBLICABLE
    caida_sospechosa = bool(cantidad_anterior and porcentaje_vs_anterior < CAIDA_MAXIMA_PERMITIDA)
    parcial = (
        cobertura_insuficiente
        or caida_sospechosa
        or completitud in {"baja", "media"}
        or salud in {"PARTIAL", "TIMEOUT", "BLOCKED", "DISCOVERY_FAILED", "NO_SOURCE"}
    )

    if cobertura_insuficiente:
        warnings.append(f"Cobertura insuficiente: {coverage:.1%} ({extracted if extracted is not None else '?'} / {expected if expected is not None else '?'})")
    if caida_sospechosa:
        warnings.append(f"Caída sospechosa de catálogo: {len(nuevos)} vs {cantidad_anterior} anteriores ({porcentaje_vs_anterior:.1%})")

    if parcial and cantidad_anterior:
        finales = _merge(anterior, nuevos)
        warnings.append(f"No se reemplaza el catálogo: extracción parcial ({len(nuevos)} nuevos vs {cantidad_anterior} anteriores).")
        stats = _estadisticas(anterior, nuevos, finales)
        stats["productos_eliminados"] = 0
        return finales, {
            "ok": True, "tienda": tienda, "productos": len(finales),
            "salud": salud or "PARTIAL", "completitud": completitud or "media",
            "fuente": "fusion_parcial", "warnings": warnings,
            "expected_product_urls": expected, "extracted_product_urls": extracted,
            "coverage": coverage, **stats,
        }

    sin_imagen = sum(1 for p in nuevos if not p.get("imagen"))
    if nuevos and sin_imagen > len(nuevos) * 0.30:
        warnings.append(f"{sin_imagen}/{len(nuevos)} productos sin imagen (>30%)")
    stats = _estadisticas(anterior, nuevos, nuevos)
    return nuevos, {
        "ok": True, "tienda": tienda, "productos": len(nuevos), "salud": "HEALTHY",
        "completitud": "alta", "fuente": "extraccion_nueva", "warnings": warnings,
        "expected_product_urls": expected, "extracted_product_urls": extracted,
        "coverage": coverage if coverage is not None else 1.0, **stats,
    }
