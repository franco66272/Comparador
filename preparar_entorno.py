import importlib.util
import subprocess
import sys

REQUERIDOS = {
    "requests": "requests>=2.31",
    "bs4": "beautifulsoup4>=4.12",
    "soupsieve": "soupsieve>=2.5",
    "scrapy": "scrapy>=2.11",
    "lxml": "lxml>=5.0",
}

faltantes = [paquete for modulo, paquete in REQUERIDOS.items()
             if importlib.util.find_spec(modulo) is None]

if faltantes:
    print("[SETUP] Instalando dependencias faltantes:")
    for paquete in faltantes:
        print(f"  - {paquete}")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", *faltantes
    ])
else:
    print("[OK] Todas las dependencias universales están instaladas.")

print(f"[OK] Python: {sys.executable}")
subprocess.call([sys.executable, "-m", "scrapy", "version"])
