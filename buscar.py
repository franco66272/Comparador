import json

with open("compragamer.json", "r", encoding="utf-8") as f:
    productos = json.load(f)

busqueda = input("¿Qué producto querés buscar? ")

busqueda = busqueda.lower()

resultados = []

for producto in productos:

    nombre = producto["nombre"].lower()

    if busqueda in nombre:
        resultados.append(producto)

resultados.sort(
    key=lambda p: p["precio"] or 999999999
)

print()
print(f"Resultados encontrados: {len(resultados)}")
print()

for producto in resultados:

    print(
        f"${producto['precio']:,.0f} | "
        f"{producto['nombre']} | "
        f"Stock: {producto['stock']}"
    )

    print(producto["url"])
    print()