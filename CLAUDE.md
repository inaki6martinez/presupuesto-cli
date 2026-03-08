# CLAUDE.md — Contexto del proyecto

## Qué es este proyecto

Herramienta CLI en Python que importa extractos bancarios (PDF, Excel, CSV) y los escribe en la hoja "Datos" de `presupuesto.xlsx`, categorizando cada movimiento según los valores definidos en las hojas "Maestro" y "Claves" del mismo archivo.

## Documentación

- `requisitos-presupuesto-cli.md` — Especificación completa de requisitos (formato de salida, parsers, categorización, estructura del proyecto).
- `guia-desarrollo-presupuesto-cli.md` — Guía paso a paso de desarrollo.

Lee ambos documentos antes de hacer cualquier cambio significativo.

## Arquitectura clave

### Hoja "Datos" — 13 columnas (A→M)

Año | Mes | Categoría 1 | Categoría 2 | Categoría 3 | Entidad | Importe | Proveedor | Tipo de Gasto | Cuentas | Banco | Tipo de cuenta | Estado

- Columnas J→L (Cuentas, Banco, Tipo de cuenta) están vinculadas: la Cuenta determina el Banco y Tipo de cuenta automáticamente usando la tabla de la hoja "Claves".
- Estado = "Real" para movimientos importados, "Presupuesto" para los presupuestados.
- Importe: positivo = ingreso, negativo = gasto.
- Mes: abreviatura española de 3 letras (Ene, Feb, Mar, Abr, May, Jun, Jul, Ago, Sep, Oct, Nov, Dic).

### Hoja "Maestro" — Listas de valores válidos

Cada columna es una lista independiente (no hay relación entre filas de distintas columnas). Fila 1 = cabecera. Los campos de cada movimiento deben validarse contra estas listas.

### Hoja "Claves" — Relación cuenta→banco→tipo

| Cuenta | Banco | Tipo de cuenta |
|---|---|---|
| Cuenta Nomina | Openbank | Activos liquidos |
| Cuenta Ahorro | Openbank | Activos liquidos |
| Kutxabank | Kutxabank | Activos liquidos |
| Cuenta Ahorro N26 | N26 | Activos liquidos |
| Cuenta Ocio | N26 | Activos liquidos |
| Fondos | Indexa Capital | Activos medio liquidos |
| EPSV | Indexa Capital | Activos poco liquidos |
| Efectivo | Yo | Activos liquidos |
| Hipoteca Piso | BBVA | Pasivo |
| Cuenta Hipoteca | BBVA | Activos liquidos |
| Ahorro colchon | Trade republic | Activos liquidos |

### Categorización — 3 capas (sin IA)

1. **Reglas** (`reglas.json`): matching de patrones case-insensitive (contains, startswith, regex).
2. **Similitud historial**: fuzzy matching con `rapidfuzz` contra movimientos existentes en "Datos".
3. **Interactivo**: pregunta al usuario en terminal, ofrece guardar como regla nueva.

No se usa IA ni LLM. "Aprendizaje" = guardar decisiones del usuario en reglas.json.

### Parsers — Uno por banco, modulares

Bancos: Openbank, Kutxabank, N26, BBVA, Trade Republic, Abanca. Cada parser hereda de `ParserBase` y devuelve `list[MovimientoCrudo]`. Detección automática de banco por contenido del archivo.

## Convenciones

- Lenguaje del código: Python, nombres de variables y funciones en **snake_case en español** (ej: `datos_maestros`, `movimiento_crudo`, `tipo_gasto`).
- Mensajes al usuario en la terminal: en **español**.
- Docstrings y comentarios en código: en **español**.
- Lectura xlsx: `openpyxl` con `data_only=True` para leer valores.
- Escritura xlsx: `openpyxl` **sin** `data_only` para preservar fórmulas. Nunca crear un workbook nuevo, siempre abrir el existente y añadir filas.
- Nunca usar `pandas` para escribir en xlsx (destruye formatos).
- Backup automático antes de cada escritura: `presupuesto_backup_YYYYMMDD_HHMMSS.xlsx`.

## Comandos útiles

```bash
# Instalar en modo desarrollo
pip install -e .

# Ejecutar tests
pytest

# Probar sin escribir
presupuesto importar extracto.csv --dry-run

# Ver reglas actuales
presupuesto reglas listar
```

## Errores comunes a evitar

- No asumir relación entre filas del Maestro (cada columna es una lista independiente).
- No usar `WidthType.PERCENTAGE` en openpyxl (usar valores directos).
- Los extractos pueden venir en UTF-8, Latin-1 o Windows-1252 — detectar encoding.
- Los PDFs de cada banco cambian de formato periódicamente — los parsers de PDF deben ser tolerantes.
- `openpyxl` puede perder validaciones de datos y formato condicional — verificar manualmente tras la primera escritura real.
