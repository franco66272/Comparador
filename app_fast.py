"""Entrada de producción ligera para TecnoRadar.

Importa la aplicación real sin ejecutar consultas de productos durante el
arranque y ofrece un endpoint de salud que responde inmediatamente.
"""
from app import app, NOMBRES_TIENDAS, DOMINIOS_TIENDAS

# Alias de tiendas agregadas sin duplicar la lógica del sitio principal.
NOMBRES_TIENDAS["goldentechstore_com_ar"] = "GoldenTech Store"
DOMINIOS_TIENDAS["goldentechstore_com_ar"] = "goldentechstore.com.ar"


@app.route("/health-fast")
def health_fast():
    return {"ok": True, "servicio": "TecnoRadar"}


# Render puede seguir consultando /health sin obligar a cargar productos.
app.view_functions["health"] = health_fast
