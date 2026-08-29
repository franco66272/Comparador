"""Extractor HTML robusto para tiendas con catálogos paginados.

Se usa como segunda estrategia cuando el motor universal consume demasiado
presupuesto en sitemaps/fichas individuales. Prioriza las páginas de catálogo,
extrae las tarjetas directamente y sólo usa fichas individuales como respaldo.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .auto_generico import (
    HEADERS,
    HTTP_TIMEOUT,
    MAX_PRODUCTOS,
    DETAIL_WORKERS,
    Presupuesto,
    _es_fuente_excluida,
    _es_misma_tienda,
    _extraer_detalle,
    _imagen,
    _nombre_card,
    _normalizar_url,
    _precio_card,
    _siguiente_pagina,
    _url,
)
from .utils import session_con_reintentos

DEFAULT_PRODUCT_RE = re.compile(
    r"/(?:producto|productos|product|products|p|prod)/[^?#]+|"
    r"/catalogo/producto/[^?#]+|"
    r"/DETALLE/[^?#]+|"
    r"/[^/?#]+--det--\d+[^/?#]*|"
    r"/\d+-[^/?#]+\.html(?:$|\?)",
    re.I,
)


def _es_producto_robusto(url, patron):
    try:
        return bool(patron.search(url))
    except Exception:
        return bool(DEFAULT_PRODUCT_RE.search(url))


def _producto_card(card, href, tienda):
    nombre = _nombre_card(card)
    precio = _precio_card(card)
    if not nombre or not precio:
        return None
    texto = card.get_text(" ", strip=True).lower()
    stock = 0 if any(x in texto for x in ("sin stock", "agotado", "no disponible", "out of stock")) else 1
    return {
        "tienda": tienda,
        "nombre": nombre.strip(),
        "precio": precio,
        "stock": stock,
        "imagen": _imagen(card.select_one("img"), href),
        "url": href,
        "id_producto": str(card.get("data-product-id") or card.get("data-productid") or card.get("data-id") or href),
    }


def _extraer_pagina_catalogo(session, url, tienda, patron, presupuesto):
    if not presupuesto.puede_request():
        return [], None
    try:
        r = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        return [], None
    if r.status_code != 200:
        return [], None

    soup = BeautifulSoup(r.text, "html.parser")
    enlaces = []
    vistos = set()
    for a in soup.select("a[href]"):
        href = _normalizar_url(_url(r.url, a.get("href")))
        if not href or href in vistos or not _es_misma_tienda(href, r.url):
            continue
        if _es_fuente_excluida(href) or not _es_producto_robusto(href, patron):
            continue
        vistos.add(href)
        enlaces.append((href, a))

    productos = []
    usados = set()
    for href, enlace in enlaces:
        nodo = enlace
        tarjeta = None
        for _ in range(7):
            nodo = nodo.parent if nodo else None
            if not nodo:
                break
            if _precio_card(nodo):
                tarjeta = nodo
                break
        if tarjeta is None:
            continue
        producto = _producto_card(tarjeta, href, tienda)
        if producto and href not in usados:
            usados.add(href)
            productos.append(producto)

    siguiente = _siguiente_pagina(soup, r.url)
    return productos, siguiente


def extraer_desde_config_robusto(config):
    tienda = config["tienda"]
    base_url = _normalizar_url(config["url"])
    presupuesto = Presupuesto()
    session = session_con_reintentos(intentos=1)
    productos = []
    vistos = set()
    warnings = []
    fuentes = []

    patron = re.compile(config.get("producto_regex") or DEFAULT_PRODUCT_RE.pattern, re.I)
    catalog_urls = list(config.get("catalog_urls", []))
    if not catalog_urls:
        catalog_urls = [base_url]

    def agregar(lista):
        nuevos = 0
        for p in lista or []:
            if not p or not p.get("nombre") or not p.get("precio") or not p.get("url"):
                continue
            clave = _normalizar_url(p.get("url")) or p.get("id_producto")
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            productos.append(p)
            nuevos += 1
            if len(productos) >= MAX_PRODUCTOS:
                break
        presupuesto.productos = len(productos)
        return nuevos

    # Primero catálogo HTML. Esto evita gastar miles de requests en sitemaps
    # cuando una tienda ofrece 40-100 productos por página.
    for primera in catalog_urls[:120]:
        if presupuesto.vencido() or len(productos) >= MAX_PRODUCTOS:
            break
        url = _normalizar_url(primera)
        visitadas = set()
        pagina = 0
        while url and url not in visitadas and not presupuesto.vencido():
            visitadas.add(url)
            pagina += 1
            encontrados, siguiente = _extraer_pagina_catalogo(session, url, tienda, patron, presupuesto)
            nuevos = agregar(encontrados)
            if nuevos:
                fuentes.append({"tipo": "html", "url": url, "productos": nuevos})
            if not siguiente or siguiente in visitadas:
                break
            url = siguiente

    # Si las tarjetas no entregaron todos los datos, completar por fichas de
    # producto descubiertas en las mismas páginas ya visitadas.
    if productos == [] and not presupuesto.vencido():
        try:
            portada = session.get(base_url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            if portada.status_code == 200:
                soup = BeautifulSoup(portada.text, "html.parser")
                urls = []
                seen = set()
                for a in soup.select("a[href]"):
                    u = _normalizar_url(_url(portada.url, a.get("href")))
                    if u and u not in seen and _es_misma_tienda(u, base_url) and _es_producto_robusto(u, patron):
                        seen.add(u)
                        urls.append(u)
                workers = min(DETAIL_WORKERS, len(urls))
                with ThreadPoolExecutor(max_workers=workers or 1) as pool:
                    futuros = {pool.submit(_extraer_detalle, u, tienda): u for u in urls[:1000]}
                    for futuro in as_completed(futuros):
                        if presupuesto.vencido():
                            break
                        try:
                            p = futuro.result()
                        except Exception:
                            p = None
                        if p:
                            agregar([p])
        except requests.RequestException:
            pass

    return {
        "ok": bool(productos),
        "tienda": tienda,
        "productos": productos[:MAX_PRODUCTOS],
        "con_imagen": sum(1 for p in productos if p.get("imagen")),
        "warnings": warnings,
        "salud": "HEALTHY" if productos and not presupuesto.vencido() else ("PARTIAL" if productos else "NO_SOURCE"),
        "completitud": "alta" if productos and not presupuesto.vencido() else ("media" if productos else "baja"),
        "parcial": presupuesto.vencido(),
        "requests": presupuesto.requests,
        "paginas": presupuesto.paginas,
        "fuentes": fuentes,
        "expected_product_urls": 0,
        "discovered_product_urls": len(vistos),
        "extracted_product_urls": len(vistos),
        "coverage": 1.0 if productos else 0.0,
    }
