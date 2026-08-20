"""Entrada de producción ligera para TecnoRadar.

Importa la aplicación real sin ejecutar consultas de productos durante el
arranque y ofrece un endpoint de salud que responde inmediatamente.
"""
from app import app


@app.route("/health-fast")
def health_fast():
    return {"ok": True, "servicio": "TecnoRadar"}

# Render puede seguir consultando /health sin obligar a cargar productos.
app.view_functions["health"] = health_fast
