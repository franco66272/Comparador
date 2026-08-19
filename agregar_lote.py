import json
import subprocess
import sys
from pathlib import Path

TIENDAS = [
    "https://hypergaming.com.ar/",
    "https://wiztech.com.ar/",
    "https://www.gamingcity.com.ar/",
    "https://fullh4rd.com.ar/",
    "https://www.xt-pc.com.ar/",
    "https://www.vrx.com.ar/",
    "https://www.thegamershop.com.ar/",
    "https://spacegamer.com.ar/",
    "https://www.shopgamer.com.ar/",
    "https://www.scphardstore.com/",
    "https://portalstore.com.ar/",
    "https://noxiestore.com/",
    "https://www.megasoftargentina.com.ar/",
    "https://www.maxtecno.com.ar/",
    "https://katech.com.ar/",
    "https://www.integradosargentinos.com/",
    "https://www.goldentechstore.com.ar/",
    "https://dinobyte.ar/",
    "https://hardcorecomputacion.com.ar/",
    "https://www.compufanstore.com.ar/",
    "https://www.clickgaming.com.ar/",
    "https://backupcomputacion.com/",
    "https://insumosacuario.com.ar/",
    "https://37bytes.com.ar/",
    "https://mymcomputacion.com/",
    "https://710tech.com.ar/",
    "https://www.ngtechnologies.com.ar/",
    "https://www.gamerfactory.com.ar/",
    "https://www.slot-one.com.ar/",
    "https://universosgamers.com.ar/",
    "https://empeniogamer.com.ar/",
    "https://www.necxus.com.ar/",
    "http://www.silverhard.com/",
    "https://netgaming.ar/",
]

CONFIG = Path("config/tiendas_auto.json")
PENDIENTES_CONFIG = Path("config/tiendas_pendientes.json")


def cargar_registro():
    if not CONFIG.exists():
        return {}

    with CONFIG.open("r", encoding="utf-8") as f:
        return json.load(f)


def nombre_tienda(url):
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    return host.replace(".", "_").replace("-", "_")


def main():
    registro = cargar_registro()

    existentes = set(registro.keys())

    pendientes = []

    urls_lote = list(TIENDAS)
    if PENDIENTES_CONFIG.exists():
        try:
            datos_pendientes = json.loads(PENDIENTES_CONFIG.read_text(encoding="utf-8"))
            urls_lote = list(dict.fromkeys(urls_lote + datos_pendientes.get("tiendas", [])))
        except Exception as exc:
            print(f"[WARN] No se pudo leer tiendas_pendientes.json: {exc}")

    for url in urls_lote:
        nombre = nombre_tienda(url)

        if nombre in existentes:
            print(f"[YA EXISTE] {url}")
        else:
            pendientes.append(url)

    print()
    print("=" * 75)
    print(f"TIENDAS EN EL LOTE: {len(urls_lote)}")
    print(f"YA REGISTRADAS:     {len(urls_lote) - len(pendientes)}")
    print(f"PENDIENTES:         {len(pendientes)}")
    print("=" * 75)

    if not pendientes:
        print("[INFO] No hay tiendas nuevas para procesar.")
        return

    ok = []
    errores = []

    for i, url in enumerate(pendientes, 1):
        print()
        print("=" * 75)
        print(f"[{i}/{len(pendientes)}] PROCESANDO: {url}")
        print("=" * 75)

        try:
            resultado = subprocess.run(
                [
                    sys.executable,
                    "agregar_tienda.py",
                    url,
                ],
                cwd=".",
                timeout=120,
            )

            if resultado.returncode == 0:
                ok.append(url)
                print(f"[OK] {url}")
            else:
                errores.append(url)
                print(
                    f"[ERROR] {url} "
                    f"(exit {resultado.returncode})"
                )

        except subprocess.TimeoutExpired:
            errores.append(url)
            print(f"[TIMEOUT] {url} (60s)")
        except Exception as exc:
            errores.append(url)
            print(f"[ERROR] {url}: {exc}")

    print()
    print("=" * 75)
    print("LOTE TERMINADO")
    print("=" * 75)

    print(f"OK:           {len(ok)}")
    print(f"ERRORES:      {len(errores)}")
    print(f"YA EXISTÍAN:  {len(urls_lote) - len(pendientes)}")

    if errores:
        print()
        print("TIENDAS CON ERROR:")
        for url in errores:
            print(f" - {url}")


if __name__ == "__main__":
    main()
