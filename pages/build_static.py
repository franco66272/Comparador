from pathlib import Path
import re
import shutil

from app import app

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
RENDER_BASE = "https://tecnoradar.onrender.com"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

# Render the same Flask home page using the repository's current local data.
with app.test_client() as client:
    response = client.get("/")
    response.raise_for_status = lambda: None
    html = response.get_data(as_text=True)

# GitHub Pages hosts the visual shell. Anything requiring Flask is sent to Render.
html = re.sub(r'(href|src)="/static/', r'\1="static/', html)
html = html.replace('action="/"', f'action="{RENDER_BASE}/"')
html = html.replace('href="/"', f'href="{RENDER_BASE}/"')
html = re.sub(r'href="/producto/([^\"]+)"', rf'href="{RENDER_BASE}/producto/\1"', html)
html = re.sub(r'href="/\?([^\"]+)"', rf'href="{RENDER_BASE}/?\1"', html)
html = html.replace('href="/salud"', f'href="{RENDER_BASE}/salud"')
html = html.replace('href="/health"', f'href="{RENDER_BASE}/health"')

# Keep the GitHub Pages test clearly identifiable without changing the site's design.
html = html.replace('</head>', '<meta name="generator" content="TecnoRadar GitHub Pages performance test"></head>', 1)
(OUT / "index.html").write_text(html, encoding="utf-8")

# Copy the existing frontend assets exactly as they are used by Render.
shutil.copytree(ROOT / "static", OUT / "static")

# Prevent GitHub Pages from treating files beginning with underscores specially.
(OUT / ".nojekyll").write_text("", encoding="utf-8")
print(f"Static TecnoRadar test built at {OUT}")
