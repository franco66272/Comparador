"""Punto de entrada estable de TecnoRadar."""
from flask import Flask, redirect

from app_optimizado import inicio_optimizado, producto_optimizado

app = Flask(__name__, template_folder="templates", static_folder="static")

# Los templates existentes llaman a estos endpoints por sus nombres originales.
app.add_url_rule("/", endpoint="inicio", view_func=inicio_optimizado, methods=["GET"])
app.add_url_rule(
    "/producto/<codigo>",
    endpoint="producto_detalle",
    view_func=producto_optimizado,
    methods=["GET"],
)

# Alias públicos adicionales para compatibilidad con enlaces antiguos.
app.add_url_rule(
    "/producto/<codigo>",
    endpoint="producto",
    view_func=producto_optimizado,
    methods=["GET"],
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
