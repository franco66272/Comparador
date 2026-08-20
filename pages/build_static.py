from pathlib import Path
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, clave_producto, cargar_detalles, cargar_historial, cargar_productos, construir_categorias, nombre_tienda_visible

OUT = ROOT / "_site"
RENDER_BASE = "https://tecnoradar.onrender.com"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

productos = cargar_productos()
historial = cargar_historial()
detalles = cargar_detalles()

# Renderiza la portada con exactamente los datos actuales del catálogo.
with app.test_client() as client:
    response = client.get("/")
    if response.status_code >= 400:
        raise RuntimeError(f"No se pudo generar la portada estática: HTTP {response.status_code}")
    html = response.get_data(as_text=True)

# La portada queda estática. Búsquedas/filtros que necesitan Flask siguen enviándose a Render.
html = re.sub(r'(href|src)="/static/', r'\1="static/', html)
html = html.replace('action="/"', f'action="{RENDER_BASE}/"')
html = html.replace('href="/"', 'href="index.html"')
# Las publicaciones pasan a ser estáticas y ya no despiertan Render.
html = re.sub(r'href="/producto/([^\"]+)"', r'href="producto.html?codigo=\1"', html)
html = re.sub(r'href="/\?([^\"]+)"', rf'href="{RENDER_BASE}/?\1"', html)
html = html.replace('href="/salud"', f'href="{RENDER_BASE}/salud"')
html = html.replace('href="/health"', f'href="{RENDER_BASE}/health"')
html = html.replace('</head>', '<meta name="generator" content="TecnoRadar GitHub Pages performance test"></head>', 1)
(OUT / "index.html").write_text(html, encoding="utf-8")

# Página única de producto: el navegador descarga solamente un JSON pequeño por producto.
producto_template = (ROOT / "pages" / "producto_static.html").read_text(encoding="utf-8")
(OUT / "producto.html").write_text(producto_template, encoding="utf-8")

# Datos mínimos por producto. Esto evita cargar el catálogo completo al abrir una publicación.
data_root = OUT / "data" / "productos"
data_root.mkdir(parents=True, exist_ok=True)
for producto in productos:
    codigo = clave_producto(producto)
    payload = {
        "producto": {
            "tienda": producto.get("tienda"),
            "tienda_nombre": nombre_tienda_visible(producto.get("tienda")),
            "nombre": producto.get("nombre"),
            "precio": producto.get("precio"),
            "precio_anterior": producto.get("precio_anterior"),
            "stock": producto.get("stock"),
            "imagen": producto.get("imagen"),
            "url": producto.get("url"),
            "id_producto": producto.get("id_producto"),
            "actualizado_en": producto.get("actualizado_en"),
        },
        "detalle": detalles.get(codigo, {}),
        "historial": historial.get(codigo, []),
    }
    (data_root / f"{codigo}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# Menú de categorías precalculado para que la página de producto no consulte Flask.
meta = {"categorias": construir_categorias(productos)}
(OUT / "data" / "catalogo_meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# Copiar todos los assets frontend exactamente como se usan en Render.
static_dir = ROOT / "static"
if not static_dir.is_dir():
    raise RuntimeError(f"No existe el directorio de frontend: {static_dir}")
shutil.copytree(static_dir, OUT / "static")

(OUT / ".nojekyll").write_text("", encoding="utf-8")
print(f"Static TecnoRadar built: {len(productos)} products")
