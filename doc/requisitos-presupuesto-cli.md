# Requisitos: Herramienta CLI de procesamiento de movimientos bancarios

## 1. Descripción general

Herramienta de terminal Linux que recibe extractos bancarios (PDF, Excel o CSV) de distintos bancos, los procesa, categoriza y escribe directamente en la hoja **"Datos"** del archivo `presupuesto.xlsx`, respetando su formato exacto. Utiliza los valores válidos definidos en la hoja **"Maestro"** y la tabla **"Claves"** (relación cuenta→banco→tipo de cuenta) para validar y autocompletar campos.

---

## 2. Formato de salida (hoja "Datos")

Cada movimiento procesado debe generar una fila con exactamente **13 columnas** en este orden:

| Col | Campo | Descripción | Origen |
|-----|-------|-------------|--------|
| A | Año | Año numérico (2022, 2023…) | Extraído de la fecha del movimiento |
| B | Mes | Abreviatura de 3 letras: Ene, Feb, Mar, Abr, May, Jun, Jul, Ago, Sep, Oct, Nov, Dic | Extraído de la fecha del movimiento |
| C | Categoría 1 | Nivel principal de clasificación | Maestro columna C (ej: Alimentación, Transporte, Ingresos…) |
| D | Categoría 2 | Subcategoría | Maestro columna D (ej: Compra, Gasolina, Salario…) |
| E | Categoría 3 | Detalle opcional (puede estar vacío) | Maestro columna E (ej: Electricidad, Paga normal…) |
| F | Entidad | Persona o entidad asociada (puede estar vacío) | Maestro columna F (ej: Iñaki, Alba, Piso…) |
| G | Importe | Cantidad numérica. Positivo = ingreso, negativo = gasto | Extraído del extracto bancario |
| H | Proveedor | Comercio o proveedor (puede estar vacío) | Maestro columna G (ej: Eroski, Amazon, Netflix…) |
| I | Tipo de Gasto | Clasificación del gasto | Maestro columna H: Fijos, Optimizable, Discrecionales, Excepcionales |
| J | Cuentas | Producto financiero de origen | Claves columna A (ej: Cuenta Nomina, Cuenta Ahorro, Kutxabank…) |
| K | Banco | Entidad bancaria | Claves columna B — se autocompleta a partir de J |
| L | Tipo de cuenta | Clasificación contable | Claves columna C — se autocompleta a partir de J |
| M | Estado | Siempre "Real" para movimientos importados desde extractos | Valor fijo |

---

## 3. Datos maestros (hoja "Maestro")

La hoja Maestro contiene listas de valores válidos en columnas independientes (no son relaciones fila a fila, sino listas verticales por columna):

- **Col A**: Años válidos (2022–2026)
- **Col B**: Meses (Ene–Dic)
- **Col C**: Categorías nivel 1 (15 valores: Ahorro, Alimentación, Comunicaciones, Educación, Finanzas, Gastos Personales, Ingresos, Mascotas, Ocio, Personal, Ropa, Salud, Transporte, Vivienda)
- **Col D**: Categorías nivel 2 (~53 valores: Alquiler, Compra, Deporte, Fondos, Gasolina, Gym, Hipoteca, Salario…)
- **Col E**: Categorías nivel 3 (~34 valores: Agua, Avión, Calefacción, Dentista, Electricidad, Paga normal…)
- **Col F**: Entidades (Alba, Alba y Iñaki, Garaje, Iñaki, Piso, Seat Leon, Vietnam(viaje))
- **Col G**: Proveedores (~45 valores: ACNUR, Altafit, Amazon, Apple, Eroski, Netflix, Spotify…)
- **Col H**: Tipos de gasto (Fijos, Optimizable, Discrecionales, Excepcionales)
- **Col I**: Cuentas (Cuenta Nomina, Cuenta Ahorro, Kutxabank, Fondos, EPSV, Cuenta Ocio, Efectivo, Cuenta Ahorro N26, Inmuebles, Hipoteca Piso, Deuda aitas Iñaki, Ahorro colchon, Cuenta Hipoteca)
- **Col J**: Bancos (Kutxabank, Openbank, Indexa Capital, N26, Yo, BBVA, Trade republic)
- **Col K**: Tipos de cuenta (Pasivo, Activos liquidos, Activos medio liquidos, Activos poco liquidos)

### Tabla "Claves" (relaciones cuenta→banco→tipo)

La hoja "Claves" define la relación entre cuentas, bancos y tipos de cuenta. Se usa para autocompletar K y L a partir de J:

| Cuenta (J) | Banco (K) | Tipo de cuenta (L) |
|---|---|---|
| Cuenta Nomina | Openbank | Activos liquidos |
| Cuenta Ahorro | Openbank | Activos liquidos |
| Cuenta Ahorro N26 | N26 | Activos liquidos |
| Kutxabank | Kutxabank | Activos liquidos |
| Fondos | Indexa Capital | Activos medio liquidos |
| EPSV | Indexa Capital | Activos poco liquidos |
| Cuenta Ocio | N26 | Activos liquidos |
| Efectivo | Yo | Activos liquidos |
| Inmuebles | (vacío) | Activos poco liquidos |
| Hipoteca Piso | BBVA | Pasivo |
| Deuda aitas Iñaki | (vacío) | Pasivo |
| Ahorro colchon | Trade republic | Activos liquidos |
| Cuenta Hipoteca | BBVA | Activos liquidos |

---

## 4. Parsers de entrada (uno por banco)

La herramienta debe tener un parser modular para cada banco. Cada parser extrae: **fecha, concepto/descripción, importe** del extracto bancario.

### 4.1 Bancos soportados

| Banco | Formatos esperados | Cuenta por defecto (J) |
|---|---|---|
| Openbank | PDF, Excel, CSV | Cuenta Nomina / Cuenta Ahorro (según la cuenta de origen) |
| Kutxabank | PDF, Excel, CSV | Kutxabank |
| N26 | CSV | Cuenta Ahorro N26 / Cuenta Ocio |
| BBVA | PDF, Excel, CSV | Cuenta Hipoteca |
| Trade Republic | PDF, CSV | Ahorro colchon |
| Abanca | PDF, Excel, CSV | (nueva cuenta — pedir al usuario o configurar) |

### 4.2 Requisitos de los parsers

- Cada parser es un módulo independiente (fichero separado) para facilitar añadir nuevos bancos en el futuro.
- Deben normalizar la fecha a Año (numérico) + Mes (abreviatura española de 3 letras).
- Deben normalizar el importe a número decimal con punto (ingresos positivos, gastos negativos).
- Deben extraer el texto del concepto/descripción tal cual viene en el extracto (se usará para la categorización).
- Para PDFs: usar una librería de extracción de texto (ej: `pdfplumber`, `tabula-py`, `camelot`).
- El parser debe ser tolerante a variaciones de formato entre diferentes períodos del mismo banco.

### 4.3 Detección automática de banco

La herramienta debe intentar detectar automáticamente el banco de origen analizando el contenido del archivo (cabeceras, estructura, texto identificativo). Si no puede determinarlo, debe preguntar al usuario.

---

## 5. Sistema de categorización (híbrido: reglas + interactivo + aprendizaje)

La categorización es el núcleo de la herramienta. Funciona en tres capas:

### 5.1 Capa 1 — Reglas aprendidas (fichero `reglas.json`)

Un fichero JSON persistente que mapea patrones de concepto/descripción a categorías completas. Estructura:

```json
{
  "reglas": [
    {
      "patron": "eroski",
      "tipo": "contains",
      "campos": {
        "categoria1": "Alimentación",
        "categoria2": "Compra",
        "categoria3": "",
        "entidad": "",
        "proveedor": "Eroski",
        "tipo_gasto": "Optimizable"
      }
    },
    {
      "patron": "netflix",
      "tipo": "contains",
      "campos": {
        "categoria1": "Gastos Personales",
        "categoria2": "Subscripciones y Apps",
        "categoria3": "",
        "entidad": "Iñaki",
        "proveedor": "Netflix",
        "tipo_gasto": "Discrecionales"
      }
    }
  ]
}
```

- El matching de patrones debe ser case-insensitive.
- Soportar tipos: `contains`, `startswith`, `regex`.
- Si un movimiento hace match con una regla, se categoriza automáticamente sin preguntar.
- El fichero se inicializa vacío y se va alimentando con cada decisión del usuario (capa 3).

### 5.2 Capa 2 — Sugerencia inteligente por similitud

Si no hay match en reglas.json, la herramienta debe intentar sugerir una categorización:

- Buscar en el historial de la hoja "Datos" movimientos con descripciones similares (fuzzy matching del concepto).
- Si encuentra coincidencias con alta confianza, proponer la categorización al usuario como sugerencia por defecto.
- Si no hay coincidencias, dejar todos los campos vacíos para que el usuario los rellene.

### 5.3 Capa 3 — Modo interactivo con aprendizaje

Cuando la herramienta no puede categorizar automáticamente (o la sugerencia es de baja confianza), pide al usuario que categorice manualmente:

```
┌─────────────────────────────────────────────────────────┐
│  Movimiento: "COMPRA EROSKI CITY VITORIA"               │
│  Fecha: 2025-Mar  |  Importe: -45.32  |  Banco: N26    │
│                                                          │
│  Sugerencia: Alimentación > Compra (basada en historial)│
│                                                          │
│  [Enter] Aceptar sugerencia                              │
│  [1] Categoría 1: Alimentación ▼                        │
│  [2] Categoría 2: Compra ▼                              │
│  [3] Categoría 3: (vacío) ▼                             │
│  [4] Entidad: (vacío) ▼                                 │
│  [5] Proveedor: (vacío) ▼                               │
│  [6] Tipo de Gasto: Optimizable ▼                       │
│  [s] Saltar movimiento                                   │
│  [q] Guardar progreso y salir                            │
└─────────────────────────────────────────────────────────┘
```

- Al seleccionar un campo, mostrar las opciones válidas del Maestro con búsqueda/filtro.
- Tras confirmar la categorización, **preguntar si quiere guardar como regla** para el patrón detectado:
  ```
  ¿Guardar regla para futuros movimientos con "EROSKI"? [S/n]
  Patrón a usar: eroski
  ```
- Si el usuario dice sí, añadir la regla a `reglas.json` para que próximos movimientos similares se categoricen automáticamente.

### 5.4 Fichero de reglas pre-cargado

La herramienta debe incluir un fichero `reglas_iniciales.json` con reglas por defecto basadas en los proveedores ya existentes en el Maestro. Ejemplo de mapeos iniciales a generar:

- ACNUR → Gastos Personales > Donaciones
- Altafit / Dreamfit / Gasteiz training → Salud > Deporte > Gym
- Amazon → (preguntar, es demasiado genérico)
- Apple / Google → Gastos Personales > Subscripciones y Apps
- Eroski / BM / Black Market / Carniceria → Alimentación > Compra
- Lowi → Comunicaciones > Internet y moviles
- Netflix / HBO / Spotify / Audible → Gastos Personales > Subscripciones y Apps
- Repsol / Totalenergies → Transporte > Gasolina
- Decathlon / Forum Sport → Ropa o Salud > Deporte (preguntar)

---

## 6. Escritura en presupuesto.xlsx

### 6.1 Comportamiento

- Abrir el archivo `presupuesto.xlsx` existente.
- Localizar la hoja "Datos".
- Encontrar la última fila con datos.
- Añadir los nuevos movimientos a continuación, **sin modificar ni borrar datos existentes**.
- Preservar todo el formato, fórmulas y demás hojas del libro.
- Guardar el archivo.

### 6.2 Detección de duplicados

Antes de escribir, comparar cada movimiento nuevo contra los existentes en "Datos" usando la combinación: **Año + Mes + Importe + Categoría2** (o concepto original si está disponible). Marcar duplicados potenciales y pedir confirmación al usuario.

### 6.3 Librería recomendada

Usar `openpyxl` para leer/escribir el xlsx manteniendo formato y fórmulas. No usar pandas para la escritura (destruye formatos).

---

## 7. Interfaz CLI

### 7.1 Uso básico

```bash
# Procesar un extracto
presupuesto importar extracto_openbank.pdf

# Procesar varios archivos
presupuesto importar *.csv

# Especificar banco manualmente
presupuesto importar extracto.pdf --banco kutxabank

# Especificar cuenta de destino
presupuesto importar extracto.pdf --cuenta "Cuenta Nomina"

# Modo dry-run (previsualizar sin escribir)
presupuesto importar extracto.pdf --dry-run

# Gestionar reglas
presupuesto reglas listar
presupuesto reglas exportar reglas_backup.json
presupuesto reglas importar reglas_custom.json

# Ver valores válidos del maestro
presupuesto maestro categorias
presupuesto maestro proveedores
```

### 7.2 Configuración

Fichero de configuración `~/.config/presupuesto/config.toml`:

```toml
# Ruta al archivo de presupuesto
archivo_presupuesto = "/ruta/a/presupuesto.xlsx"

# Ruta al fichero de reglas
archivo_reglas = "~/.config/presupuesto/reglas.json"

# Cuenta por defecto por banco (override de la detección automática)
[cuentas_defecto]
openbank = "Cuenta Nomina"
n26 = "Cuenta Ahorro N26"
kutxabank = "Kutxabank"
bbva = "Cuenta Hipoteca"
trade_republic = "Ahorro colchon"
abanca = ""
```

### 7.3 Opciones globales

- `--archivo, -a`: Ruta al presupuesto.xlsx (override de config).
- `--dry-run, -d`: Previsualizar movimientos sin escribir.
- `--verbose, -v`: Modo detallado.
- `--no-interactivo`: Saltar movimientos que no se puedan categorizar automáticamente (los deja en un fichero `pendientes.json` para revisión posterior).
- `--auto`: Categorizar automáticamente todo lo posible, preguntar solo los desconocidos.

---

## 8. Stack técnico recomendado

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.10+ |
| CLI framework | `click` o `typer` |
| Lectura/escritura xlsx | `openpyxl` |
| Extracción PDF | `pdfplumber` (principal), `tabula-py` (fallback para tablas) |
| Lectura CSV/Excel | `pandas` (solo para lectura, no escritura) |
| Fuzzy matching | `rapidfuzz` o `thefuzz` |
| Configuración | `tomllib` (stdlib) + `tomli-w` para escritura |
| Interfaz interactiva | `rich` (para tablas y prompts bonitos en terminal) |
| Empaquetado | `pyproject.toml` + `pip install -e .` |

---

## 9. Estructura de proyecto sugerida

```
presupuesto-cli/
├── pyproject.toml
├── README.md
├── src/
│   └── presupuesto/
│       ├── __init__.py
│       ├── cli.py                  # Punto de entrada CLI
│       ├── config.py               # Gestión de configuración
│       ├── maestro.py              # Lectura de datos maestros desde xlsx
│       ├── categorizar.py          # Motor de categorización (3 capas)
│       ├── reglas.py               # Gestión de reglas.json
│       ├── escritor.py             # Escritura en hoja Datos
│       ├── duplicados.py           # Detección de duplicados
│       ├── interactivo.py          # UI interactiva en terminal
│       └── parsers/
│           ├── __init__.py
│           ├── base.py             # Clase base abstracta para parsers
│           ├── openbank.py
│           ├── kutxabank.py
│           ├── n26.py
│           ├── bbva.py
│           ├── trade_republic.py
│           └── abanca.py
├── datos/
│   └── reglas_iniciales.json       # Reglas pre-cargadas
└── tests/
    ├── test_parsers.py
    ├── test_categorizar.py
    └── fixtures/                   # Extractos de ejemplo para tests
```

---

## 10. Flujo completo de ejecución

```
1. Usuario ejecuta: presupuesto importar extracto.pdf
2. Cargar configuración (~/.config/presupuesto/config.toml)
3. Abrir presupuesto.xlsx → leer Maestro, Claves y datos existentes de "Datos"
4. Detectar banco del extracto (o usar --banco)
5. Parsear extracto → lista de movimientos crudos (fecha, concepto, importe)
6. Para cada movimiento:
   a. Convertir fecha → Año + Mes
   b. Determinar Cuenta (J) → autocompletar Banco (K) y Tipo de cuenta (L) desde Claves
   c. Buscar match en reglas.json (capa 1)
   d. Si no hay match → buscar similitud en historial (capa 2)
   e. Si no hay match → modo interactivo (capa 3)
   f. Validar todos los campos contra los valores del Maestro
   g. Comprobar duplicados contra datos existentes
7. Mostrar resumen de movimientos a importar
8. Confirmar escritura
9. Escribir nuevas filas en hoja "Datos"
10. Guardar presupuesto.xlsx
```

---

## 11. Consideraciones adicionales

- **Encoding**: Los extractos pueden venir en UTF-8, Latin-1 o Windows-1252. Detectar automáticamente.
- **Formatos de fecha**: Cada banco usa un formato diferente (DD/MM/YYYY, YYYY-MM-DD, etc.). Cada parser debe manejar su formato.
- **Importes**: Normalizar separadores decimales (coma vs punto) y de miles (punto vs espacio).
- **Backup**: Antes de escribir en presupuesto.xlsx, crear una copia de seguridad automática (`presupuesto_backup_YYYYMMDD_HHMMSS.xlsx`).
- **Idempotencia**: Si se ejecuta dos veces con el mismo extracto, la detección de duplicados debe evitar filas repetidas.
- **Estado "Real"**: Todos los movimientos importados desde extractos bancarios llevan Estado = "Real" (a diferencia de los presupuestados que llevan "Presupuesto").
- **Parsers de PDF**: Priorizar `pdfplumber` por su mejor manejo de tablas. Para cada banco, documentar la estructura esperada del PDF con ejemplos.
- **Extensibilidad de parsers**: Para añadir un nuevo banco en el futuro, solo hay que crear un nuevo fichero en `parsers/` que herede de `base.py` e implementar los métodos requeridos.
