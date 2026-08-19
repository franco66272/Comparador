import json
from pathlib import Path

BASE = Path(__file__).parent
REGISTRO = BASE / "config" / "tiendas_auto.json"
SALIDA = BASE / "config" / "fuentes_prioritarias.json"

EXCLUIR = (
    "cocina", "living", "comedor", "mueble", "muebles", "placard",
    "cama", "colchon", "colchón", "despensero", "tocador", "biblioteca",
    "pileta", "piscina", "jardin", "jardín", "hogar", "bazar", "limpieza",
    "electrodomestico", "electrodoméstico", "freidora", "pava", "lavarropas",
    "heladera", "vestidor", "sofa", "sofá", "sillon", "sillón", "juguete",
    "mascota", "alimento", "contacto", "privacidad", "login", "carrito",
    "checkout", "wishlist", "nosotros", "garantia", "devolucion",
)

TECNO = (
    "mother", "motherboard", "procesador", "cpu", "ryzen", "core i",
    "placa", "vga", "gpu", "geforce", "radeon", "rtx", "gtx",
    "memoria", "ram", "ddr", "ssd", "nvme", "hdd", "disco",
    "fuente", "psu", "gabinete", "cooler", "watercooler", "monitor",
    "teclado", "mouse", "auricular", "headset", "webcam", "joystick",
    "notebook", "laptop", "router", "switch", "wifi", "ethernet",
    "red", "periferico", "microfono", "hardware", "componentes", "computacion",
)


def score(url):
    s = str(url).lower()
    if any(x in s for x in EXCLUIR):
        return -1000
    value = 0
    if any(x in s for x in TECNO):
        value += 10
    if any(x in s for x in ("/categor", "/category", "/tienda/", "/componentes", "/hardware")):
        value += 8
    if "/producto" in s or "/product" in s:
        value += 2
    return value


def priorizar(urls, limite=100):
    unicos = []
    vistos = set()
    for url in urls:
        if not url:
            continue
        url = url.split("#",1)[0]
        if url in vistos:
            continue
        vistos.add(url)
        sc = score(url)
        if sc > 0:
            unicos.append((sc,url))
    unicos.sort(key=lambda x:(-x[0],x[1]))
    return [u for _,u in unicos[:limite]]


def main():
    if not REGISTRO.exists():
        print("No existe config/tiendas_auto.json")
        return
    data = json.loads(REGISTRO.read_text(encoding="utf-8"))
    prioridades = {
        nombre: priorizar(config.get("catalog_urls", []), 100)
        for nombre, config in data.items()
    }
    SALIDA.write_text(
        json.dumps(prioridades, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] Fuentes prioritarias generadas: {SALIDA}")
    print("[OK] tiendas_auto.json NO fue modificado.")


if __name__ == "__main__":
    main()
