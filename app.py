"""Punto de entrada estable de TecnoRadar."""
import json
from flask import Flask, Response, redirect

import app_base as base
from app_optimizado import inicio_optimizado, producto_optimizado

app = Flask(__name__, template_folder="templates", static_folder="static")

if not hasattr(base, "cargar_detalles"):
    def cargar_detalles():
        try:
            with open("detalles_productos.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    base.cargar_detalles = cargar_detalles


def resolver_imagen(imagen="", producto=""):
    valor = str(imagen or "").strip()
    if base.imagen_utilizable(valor):
        return redirect(valor)
    return Response("", status=404, mimetype="text/plain")

app.add_url_rule("/", endpoint="inicio", view_func=inicio_optimizado, methods=["GET"])
app.add_url_rule("/producto/<codigo>", endpoint="producto_detalle", view_func=producto_optimizado, methods=["GET"])
app.add_url_rule("/producto/<codigo>", endpoint="producto", view_func=producto_optimizado, methods=["GET"])
app.add_url_rule("/resolver-imagen", endpoint="resolver_imagen", view_func=resolver_imagen, methods=["GET"])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
