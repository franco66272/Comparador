# TecnoRadar V4.7

## Corrección de precios

Esta versión corrige un problema del extractor universal: algunos vendedores incluyen importes promocionales dentro del nombre del producto (por ejemplo, `OFERTA $ 240`). Ese importe no representa necesariamente el precio real.

### Cambios
- El extractor ya no usa el nombre como fuente de precio.
- Si detecta que un importe del título coincide exactamente con el precio candidato, verifica la ficha individual antes de guardarlo.
- El verificador periódico prioriza JSON-LD, metadatos de producto y etiquetas como `Precio especial`/`Precio de oferta` antes de selectores genéricos.
- Los productos sospechosos se vuelven a verificar aunque todavía no haya vencido su intervalo normal.
- `reparar_precios_sospechosos.py` queda disponible para reparar catálogos antiguos.

### Correcciones incluidas en el catálogo
Se corrigieron tres registros de FullH4rd que tenían valores inconsistentes con la ficha del vendedor al momento de esta versión:
- Watercooler 360 Solarmax: $127.690
- Watercooler 420 Thermaltake: $124.473
- Intel Core i7-12700K: $648.660

Las fichas oficiales consultadas mostraban $127.690,03; $124.472,80 y $648.660,00 respectivamente.

### Verificación continua
Ejecutar:

```bat
..\venv\Scripts\python.exe verificar_precios_continuo.py
```

O usar `iniciar_verificacion_continua.bat`.
