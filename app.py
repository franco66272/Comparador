"""Entrada principal optimizada de TecnoRadar.

El arranque rebinda explícitamente las reglas Flask heredadas de app_base.
Esto evita depender de los nombres internos de los endpoints de la aplicación
base y garantiza que / y /producto/<codigo> usen las vistas optimizadas.
"""
from app_optimizado import app, inicio_optimizado, producto_optimizado


def _rebind_routes():
    app.view_functions["inicio_optimizado"] = inicio_optimizado
    app.view_functions["producto_optimizado"] = producto_optimizado

    for rule in app.url_map.iter_rules():
        if rule.rule == "/":
            rule.endpoint = "inicio_optimizado"
        elif rule.rule.startswith("/producto/") and "<codigo" in rule.rule:
            rule.endpoint = "producto_optimizado"


_rebind_routes()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
