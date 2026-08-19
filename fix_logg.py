content = open("extractores/logg.py", encoding="utf-8").read()

if '"precio": precio,' in content:
    print("ya estaba corregido, no se toca")
else:
    marcador = '"nombre": nombre,'
    idx = content.find(marcador)
    if idx == -1:
        raise SystemExit("no encontre el marcador, avisame")
    insercion = '\n        "precio": precio,'
    content = content[:idx] + marcador + insercion + content[idx + len(marcador):]

    marcador2 = '"imagen": imagen,'
    idx2 = content.find(marcador2)
    insercion2 = '"stock": 1,\n        '
    content = content[:idx2] + insercion2 + content[idx2:]

    open("extractores/logg.py", "w", encoding="utf-8", newline="").write(content)
    print("logg.py corregido")
