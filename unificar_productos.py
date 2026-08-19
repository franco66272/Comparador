import json
import os


ARCHIVOS = [
    "compragamer.json",
    "mexx.json",
    "venex.json",
    "puertominero.json",
    "quantum.json",
]


productos = []


for archivo in ARCHIVOS:

    if not os.path.exists(archivo):
        print(f"No existe: {archivo}")
        continue

    with open(
        archivo,
        "r",
        encoding="utf-8"
    ) as f:

        datos = json.load(f)

    print(
        f"{archivo}: {len(datos)} productos"
    )

    for producto in datos:

        p = dict(producto)

        if not p.get("imagen"):

            imagenes = p.get(
                "imagenes",
                []
            )

            if imagenes:

                primera = imagenes[0]

                if isinstance(
                    primera,
                    dict
                ):
                    nombre_imagen = primera.get(
                        "nombre"
                    )
                else:
                    nombre_imagen = primera

                if (
                    nombre_imagen
                    and
                    p.get("tienda")
                    == "CompraGamer"
                ):

                    p["imagen"] = (
                        "https://imagenes.compragamer.com/"
                        "productos/"
                        "compragamer_Imganen_general_"
                        f"{nombre_imagen}-grn.jpg"
                    )

        p.setdefault(
            "precio_anterior",
            None
        )

        p.setdefault(
            "imagen",
            None
        )

        p.setdefault(
            "stock",
            0
        )

        productos.append(p)


with open(
    "productos.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        productos,
        f,
        ensure_ascii=False,
        indent=2
    )


print()
print(
    f"Productos unificados: {len(productos)}"
)

print()

for tienda in sorted(
    set(
        p.get("tienda")
        for p in productos
    )
):

    cantidad = sum(
        1
        for p in productos
        if p.get("tienda") == tienda
    )

    con_imagen = sum(
        1
        for p in productos
        if (
            p.get("tienda") == tienda
            and p.get("imagen")
        )
    )

    print(
        f"{tienda}: "
        f"{cantidad} productos / "
        f"{con_imagen} con imagen"
    )