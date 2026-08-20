"""Actualiza únicamente el catálogo de GoldenTech sin tocar las demás tiendas."""
import json
from pathlib import Path

from extractores import goldentechstore_com_ar

RAIZ = Path(__file__).parent
MIN_PRODUCTOS_VALIDOS = 100


def main():
    resultado = goldentechstore_com_ar.extraer()
    nuevos = resultado.get("productos", [])

    print(f"GoldenTech extraídos: {len(nuevos)}")

    # No reemplazar un catálogo existente con una extracción claramente rota.
    anterior_path = RAIZ / "goldentechstore_com_ar.json"
    anterior = []
    if anterior_path.exists():
        try:
            anterior = json.loads(anterior_path.read_text(encoding="utf-8"))
        except Exception:
            anterior = []

    if len(nuevos) < MIN_PRODUCTOS_VALIDOS and len(anterior) >= MIN_PRODUCTOS_VALIDOS:
        raise RuntimeError(
            f"Extracción sospechosa: {len(nuevos)} productos; "
            f"se conserva el catálogo anterior de {len(anterior)}."
        )

    anterior_path.write_text(
        json.dumps(nuevos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    productos_path = RAIZ / "productos.json"
    try:
        productos = json.loads(productos_path.read_text(encoding="utf-8"))
    except Exception:
        productos = []

    productos = [
        p for p in productos
        if str(p.get("tienda", "")).strip() != "GoldenTech Store"
    ]
    productos.extend(nuevos)

    productos_path.write_text(
        json.dumps(productos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Productos unificados: {len(productos)}")


if __name__ == "__main__":
    main()
