import json
import sys
import subprocess
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print("Uso: python -m extractores.runner_auto MODULO SALIDA_JSON")
        raise SystemExit(2)

    modulo_nombre = sys.argv[1]
    salida = Path(sys.argv[2])

    try:
        if modulo_nombre == "extractores.auto_auditoria":
            proc = subprocess.run([sys.executable, "-m", modulo_nombre], capture_output=True, text=True)
            salida.write_text(json.dumps({"ok": proc.returncode == 0, "tienda": "auditoria", "productos": [], "warnings": proc.stdout.splitlines()[-20:]}, ensure_ascii=False), encoding="utf-8")
            raise SystemExit(proc.returncode)

        modulo = __import__(modulo_nombre, fromlist=["extraer"])
        resultado = modulo.extraer()
        if not isinstance(resultado, dict):
            resultado = {
                "ok": False,
                "tienda": modulo_nombre.rsplit(".", 1)[-1],
                "productos": [],
                "warnings": ["El extractor no devolvió un dict"],
            }

        salida.write_text(
            json.dumps(resultado, ensure_ascii=False),
            encoding="utf-8",
        )
        raise SystemExit(0 if resultado.get("ok") else 1)

    except Exception as exc:
        resultado = {
            "ok": False,
            "tienda": modulo_nombre.rsplit(".", 1)[-1],
            "productos": [],
            "warnings": [f"Excepción del extractor: {exc}"],
        }
        salida.write_text(
            json.dumps(resultado, ensure_ascii=False),
            encoding="utf-8",
        )
        raise SystemExit(1)

if __name__ == "__main__":
    main()
