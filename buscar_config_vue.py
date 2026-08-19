import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "diagnostico_salida.html"
html = open(path, encoding="utf-8").read()

print("--- <script src=...> encontrados ---")
for src in sorted(set(re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html))):
    print(f"  {src}")

print("\n--- Posibles variables de configuración (apiUrl, baseUrl, itemsData, axios) ---")
for patron in [r"apiUrl[^;,\n]{0,150}", r"baseUrl[^;,\n]{0,150}", r"itemsData\s*[:=][^;,\n]{0,150}", r"axios\.\w+\([^)]{0,150}"]:
    for m in re.findall(patron, html, re.IGNORECASE):
        print(f"  {m.strip()}")
