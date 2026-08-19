"""
Utilidades compartidas entre extractores.

parse_precio_ar()        -> convierte strings de precio argentino a int
session_con_reintentos() -> sesión requests con reintentos/backoff y User-Agent real
"""
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def parse_precio_ar(texto):
    """
    Convierte un precio en formato argentino a int (pesos enteros, sin decimales).

    Casos cubiertos (aprendidos del error de Logg: "$ 400.000" -> 400 estaba MAL,
    el punto es separador de miles, no decimal):

        "$ 400.000"        -> 400000
        "$730.999,99"       -> 730999
        "400000.0"          -> 400000   (viene de un onclick con float real)
        "  1234  "          -> 1234

    Devuelve None si no se puede interpretar (mejor None que un precio inventado).
    """
    if texto is None:
        return None
    texto = str(texto).strip()
    if not texto:
        return None

    # Caso "400000.0" (float con punto decimal real, típico de onclick/JSON) ->
    # SOLO si tiene un único punto seguido de 1-3 dígitos y NO tiene más de un punto
    # y no tiene el símbolo $ (para no confundir con "$ 400.000")
    if re.fullmatch(r"\d+\.\d{1,3}", texto):
        return int(float(texto))

    # Quitar todo lo que no sea dígito, punto o coma
    limpio = re.sub(r"[^\d.,]", "", texto)
    if not limpio:
        return None

    # Si hay coma, se asume separador decimal argentino: lo que sigue se descarta
    if "," in limpio:
        limpio = limpio.split(",")[0]

    # Los puntos restantes son separadores de miles: se eliminan
    limpio = limpio.replace(".", "")

    return int(limpio) if limpio.isdigit() else None


def session_con_reintentos(intentos=3, backoff=1.5):
    """
    Sesión requests con reintentos automáticos en errores 500/502/503/504
    (NO reintenta en 429 — eso se maneja explícitamente en cada extractor
    para no insistir contra un rate limit, como pasó con Quantum).
    """
    session = requests.Session()
    retry = Retry(
        total=intentos,
        backoff_factor=backoff,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "es-AR,es;q=0.9",
    })
    return session
