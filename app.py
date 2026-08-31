"""Punto de entrada estable de TecnoRadar.

La aplicación optimizada ya no depende del mapa de rutas que construye
app_base. Se crea una instancia Flask limpia y se registran explícitamente
las rutas públicas que utiliza la interfaz. Esto evita que una ruta antigua
registrada por app_base capture / y produzca un 404.
"""
from flask import Flask

from app_optimizado import inicio_optimizado, producto_optimizado


app = Flask(__name__, template_folder="templates", static_folder="static")

# Rutas públicas de la aplicación.
app.add_url_rule("/", endpoint="inicio", view_func=inicio_optimizado, methods=["GET"])
app.add_url_rule(
    "/producto/<codigo>",
    endpoint="producto",
    view_func=producto_optimizado,
    methods=["GET"],
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
