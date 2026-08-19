import re
html = open("diagnostico_salida.html", encoding="utf-8").read()
bloques = re.findall(r"<script type=\"application/ld\+json\">(.*?)</script>", html, re.DOTALL)
print(len(bloques), "bloques")
print(bloques[1][:3000] if len(bloques) > 1 else "no hay segundo bloque")
