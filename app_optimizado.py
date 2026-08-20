"""Arranque optimizado de TecnoRadar.

Mantiene toda la aplicación existente, pero evita trabajo repetido en cada
petición: índice O(1) para productos, metadatos del catálogo en caché y la
página de inicio deja de recorrer el historial completo para calcular datos
que no utiliza la plantilla.

Uso local:
    py app_optimizado.py
"""
from functools import lru_cache
from datetime import datetime
import os

import app as base
from app import app, render_template, request, url_for

# ---------------------------------------------------------------------------
# Cachés de datos derivados
# ---------------------------------------------------------------------------

_PRODUCT_INDEX = None
_PRODUCT_INDEX_SIGNATURE = None
_CATALOG_META = None
_CATALOG_META_SIGNATURE = None


def _signature(path="productos.json"):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def product_index():
    """Índice por clave de producto: evita recorrer todo el catálogo al abrir."""
    global _PRODUCT_INDEX, _PRODUCT_INDEX_SIGNATURE
    sig = _signature()
    if _PRODUCT_INDEX is not None and sig == _PRODUCT_INDEX_SIGNATURE:
        return _PRODUCT_INDEX

    productos = base.cargar_productos()
    _PRODUCT_INDEX = {base.clave_producto(p): p for p in productos}
    _PRODUCT_INDEX_SIGNATURE = sig
    return _PRODUCT_INDEX


def catalog_meta():
    """Calcula una sola vez los datos derivados usados por la portada."""
    global _CATALOG_META, _CATALOG_META_SIGNATURE
    sig = _signature()
    if _CATALOG_META is not None and sig == _CATALOG_META_SIGNATURE:
        return _CATALOG_META

    productos = base.cargar_productos()

    tiendas = sorted({p.get("tienda") for p in productos if p.get("tienda")})
    conteo_tiendas = {}
    for p in productos:
        tienda = p.get("tienda")
        if tienda:
            conteo_tiendas[tienda] = conteo_tiendas.get(tienda, 0) + 1

    tiendas_info = [
        {
            "clave": t,
            "nombre": base.nombre_tienda_visible(t),
            "productos": conteo_tiendas[t],
        }
        for t in tiendas
    ]
    tiendas_info.sort(key=lambda x: (-x["productos"], x["nombre"].lower()))

    categorias = base.construir_categorias(productos)

    candidatas = []
    for p in productos:
        if not p.get("nombre") or not p.get("precio"):
            continue
        score = (
            (40 if p.get("stock") else 0)
            + (30 if base.imagen_utilizable(p.get("imagen")) else 0)
            + (10 if p.get("url") else 0)
            + (5 if len(str(p.get("nombre"))) <= 100 else 0)
        )
        candidatas.append(
            (
                score,
                base.nombre_tienda_visible(p.get("tienda")),
                str(p.get("nombre")).lower(),
                p,
            )
        )
    candidatas.sort(key=lambda x: (-x[0], x[1].lower(), x[2]))

    destacados = []
    tiendas_destacadas = set()
    for _, _, _, p in candidatas:
        if p.get("tienda") in tiendas_destacadas:
            continue
        destacados.append(p)
        tiendas_destacadas.add(p.get("tienda"))
        if len(destacados) >= 12:
            break
    if len(destacados) < 12:
        for _, _, _, p in candidatas:
            if p not in destacados:
                destacados.append(p)
            if len(destacados) >= 12:
                break

    ofertas = []
    for p in productos:
        anterior = p.get("precio_anterior")
        actual = p.get("precio")
        if anterior and actual and anterior > actual:
            copia = dict(p)
            copia["descuento_pct"] = round((1 - float(actual) / float(anterior)) * 100)
            ofertas.append(copia)
    ofertas.sort(key=lambda p: (-p.get("descuento_pct", 0), p.get("precio", 999999999)))

    try:
        ultima_actualizacion = datetime.fromtimestamp(
            os.path.getmtime("productos.json")
        ).strftime("%d/%m/%Y %H:%M")
    except OSError:
        ultima_actualizacion = "Sin información"

    _CATALOG_META = {
        "productos": productos,
        "tiendas": tiendas,
        "tiendas_info": tiendas_info,
        "tiendas_principales": tiendas_info[:8],
        "tiendas_restantes": tiendas_info[8:],
        "categorias": categorias,
        "categorias_populares": sorted(
            categorias, key=lambda x: x["productos"], reverse=True
        )[:8],
        "destacados": destacados,
        "ofertas": ofertas[:12],
        "ultima_actualizacion": ultima_actualizacion,
        "total_productos": len(productos),
        "total_tiendas": len(tiendas),
    }
    _CATALOG_META_SIGNATURE = sig
    return _CATALOG_META


@app.route("/producto-rapido/<codigo>")
def producto_rapido(codigo):
    """Ruta de producto O(1), conservando la ruta original como respaldo."""
    producto = product_index().get(codigo)
    if not producto:
        return ("Producto no encontrado", 404)

    detalles = base.cargar_detalles()
    key = codigo
    detalle = detalles.get(key, {})

    if request.args.get("verificar") == "1":
        vivo = base.extraer_detalle_en_vivo(producto.get("url"))
        if vivo.get("ok"):
            if vivo.get("descripcion"):
                detalle["descripcion"] = vivo["descripcion"]
            if vivo.get("imagen"):
                detalle["imagen"] = vivo["imagen"]
                producto["imagen"] = vivo["imagen"]
            if vivo.get("precio"):
                detalle["precio_verificado"] = vivo["precio"]
                detalle["verificado_en"] = vivo.get("verificado_en")
                base.registrar_verificacion(
                    producto, vivo["precio"], producto.get("stock"), "detalle_web"
                )
            detalles[key] = detalle
            base.guardar_json_seguro("detalles_productos.json", detalles)

    historial = base.cargar_historial().get(key, [])
    meta = catalog_meta()
    return render_template(
        "producto.html",
        producto=producto,
        detalle=detalle,
        historial=historial,
        categorias=meta["categorias"],
        categoria_filtro="",
        nombre_tienda_visible=base.nombre_tienda_visible,
        imagen_utilizable=base.imagen_utilizable,
        clave_producto=base.clave_producto,
    )


@app.route("/producto/<codigo>")
def producto_detalle_optimizado(codigo):
    """Reemplaza la ruta original sin cambiar la URL pública."""
    return producto_rapido(codigo)


@app.route("/inicio-optimizado")
def inicio_optimizado():
    """Portada optimizada; la URL normal / se conserva en app.py."""
    meta = catalog_meta()
    productos = meta["productos"]
    busqueda = request.args.get("q", "").strip()
    precio_min = request.args.get("precio_min", "").strip()
    precio_max = request.args.get("precio_max", "").strip()
    solo_stock = request.args.get("solo_stock") == "1"
    tienda_filtro = request.args.get("tienda", "").strip()
    categoria_filtro = request.args.get("categoria", "").strip()
    orden = request.args.get("orden", "menor")

    if busqueda:
        consulta = base.normalizar_texto(busqueda)
        tokens = [t for t in consulta.split() if len(t) >= 2]
        resultados = [
            p for p in productos
            if consulta in base.normalizar_texto(p.get("nombre", ""))
            or all(t in base.normalizar_texto(p.get("nombre", "")) for t in tokens)
        ]
    elif tienda_filtro or categoria_filtro:
        resultados = list(productos)
    else:
        resultados = []

    if tienda_filtro:
        resultados = [p for p in resultados if p.get("tienda") == tienda_filtro]
    if categoria_filtro:
        resultados = [p for p in resultados if base.categoria_producto(p) == categoria_filtro]
    if precio_min:
        try:
            resultados = [p for p in resultados if p.get("precio", 0) >= float(precio_min)]
        except ValueError:
            pass
    if precio_max:
        try:
            resultados = [p for p in resultados if p.get("precio", 0) <= float(precio_max)]
        except ValueError:
            pass
    if solo_stock:
        resultados = [p for p in resultados if p.get("stock", 0) > 0]
    resultados.sort(key=lambda p: p.get("precio", 999999999), reverse=orden == "mayor")

    return render_template(
        "index.html",
        productos=resultados,
        busqueda=busqueda,
        precio_min=precio_min,
        precio_max=precio_max,
        solo_stock=solo_stock,
        tienda_filtro=tienda_filtro,
        categoria_filtro=categoria_filtro,
        orden=orden,
        tiendas=meta["tiendas"],
        categorias=meta["categorias"],
        tiendas_info=meta["tiendas_info"],
        tiendas_principales=meta["tiendas_principales"],
        tiendas_restantes=meta["tiendas_restantes"],
        logo_tienda_url=base.logo_tienda_url,
        destacados=meta["destacados"],
        destacado_principal=meta["destacados"][0] if meta["destacados"] else None,
        nombre_tienda_visible=base.nombre_tienda_visible,
        imagen_utilizable=base.imagen_utilizable,
        ultima_actualizacion=meta["ultima_actualizacion"],
        total_productos=meta["total_productos"],
        total_tiendas=meta["total_tiendas"],
        ofertas=meta["ofertas"],
        categorias_populares=meta["categorias_populares"],
        clave_producto=base.clave_producto,
    )


# La URL normal de inicio usa la implementación optimizada.
app.view_functions["inicio"] = inicio_optimizado


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
