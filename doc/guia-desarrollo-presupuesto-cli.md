# Guía de desarrollo paso a paso con Claude Code

## Cómo usar esta guía

Cada paso es una instrucción independiente para darle a Claude Code. Completa y prueba cada paso antes de pasar al siguiente. El orden está pensado para que cada paso construya sobre el anterior y puedas verificar que funciona.

> **Consejo**: Antes de cada paso, copia el bloque de instrucciones y pégalo en Claude Code. Si algo falla, pídele que lo corrija antes de avanzar.

---

## Paso 0 — Scaffold del proyecto

> Crea la estructura del proyecto Python `presupuesto-cli` con `pyproject.toml`, la estructura de carpetas (`src/presupuesto/`, `src/presupuesto/parsers/`, `datos/`, `tests/`, `tests/fixtures/`) y un `README.md` básico. Usa `click` como framework CLI y configura el entry point como `presupuesto`. Incluye las dependencias: `click`, `openpyxl`, `pdfplumber`, `pandas`, `rapidfuzz`, `rich`, `tomli-w`. El proyecto debe ser instalable con `pip install -e .`. No implementes nada todavía, solo la estructura y un comando `presupuesto --help` que funcione.

**Verificación**: `pip install -e .` funciona y `presupuesto --help` muestra la ayuda.

---

## Paso 1 — Lector de datos maestros

> Crea el módulo `src/presupuesto/maestro.py`. Debe abrir `presupuesto.xlsx` con `openpyxl` (en modo `data_only=True`) y extraer:
>
> 1. De la hoja "Maestro": las listas de valores válidos de cada columna (A=años, B=meses, C=categoría1, D=categoría2, E=categoría3, F=entidades, G=proveedores, H=tipos de gasto, I=cuentas, J=bancos, K=tipos de cuenta). Cada columna es una lista independiente (no hay relación entre filas de distintas columnas). Ignorar la fila 1 (cabecera). Ignorar celdas vacías.
> 2. De la hoja "Claves": la tabla de relación cuenta→banco→tipo_de_cuenta (columnas A, B, C). Esto permite autocompletar Banco y Tipo de cuenta a partir de la Cuenta seleccionada.
>
> Exponer ambos como una clase `DatosMaestros` con métodos para validar valores y obtener las listas. Incluir un método `autocompletar_cuenta(nombre_cuenta)` que devuelva `(banco, tipo_cuenta)` usando la tabla Claves.
>
> Añade un test en `tests/test_maestro.py` que cargue el archivo real y verifique que se leen los datos correctamente.

**Verificación**: El test pasa. Puedes probar con `python -c "from presupuesto.maestro import DatosMaestros; m = DatosMaestros('presupuesto.xlsx'); print(m.categorias1)"` y ver la lista de categorías.

---

## Paso 2 — Configuración

> Crea `src/presupuesto/config.py`. Debe gestionar un fichero TOML en `~/.config/presupuesto/config.toml` con estas claves:
>
> ```toml
> archivo_presupuesto = ""
> archivo_reglas = "~/.config/presupuesto/reglas.json"
>
> [cuentas_defecto]
> openbank = "Cuenta Nomina"
> n26 = "Cuenta Ahorro N26"
> kutxabank = "Kutxabank"
> bbva = "Cuenta Hipoteca"
> trade_republic = "Ahorro colchon"
> abanca = ""
> ```
>
> Implementar: carga con valores por defecto si no existe, creación automática del directorio, expansión de `~`, y un comando CLI `presupuesto config` que muestre la configuración actual y permita establecer el `archivo_presupuesto` si no está configurado.

**Verificación**: `presupuesto config` muestra la configuración. El fichero se crea en `~/.config/presupuesto/`.

---

## Paso 3 — Gestión de reglas

> Crea `src/presupuesto/reglas.py`. Gestiona el fichero `reglas.json` con esta estructura:
>
> ```json
> {
>   "reglas": [
>     {
>       "patron": "eroski",
>       "tipo": "contains",
>       "campos": {
>         "categoria1": "Alimentación",
>         "categoria2": "Compra",
>         "categoria3": "",
>         "entidad": "",
>         "proveedor": "Eroski",
>         "tipo_gasto": "Optimizable"
>       }
>     }
>   ]
> }
> ```
>
> Implementar: cargar reglas, guardar reglas, buscar match para un concepto dado (case-insensitive, soportando tipos `contains`, `startswith` y `regex`), añadir nueva regla, eliminar regla. Crear también `datos/reglas_iniciales.json` con reglas predefinidas para los proveedores conocidos del Maestro:
>
> - Eroski, BM, Carniceria, Fruteria → Alimentación > Compra, Optimizable
> - Netflix, HBO, Spotify, Audible, Overcast, Sleep Cycle → Gastos Personales > Subscripciones y Apps, Discrecionales
> - Lowi → Comunicaciones > Internet y moviles, Fijos
> - Altafit, Dreamfit, Gasteiz training → Salud > Deporte, Discrecionales
> - Repsol, Totalenergies → Transporte > Gasolina, Discrecionales
> - ACNUR → Gastos Personales > Donaciones, Discrecionales
> - Decathlon, Forum Sport → Ropa > Deporte, Discrecionales
> - DGT → Transporte > Impuestos, Excepcionales
> - Ecolaundry → Vivienda > Limpieza, Optimizable
> - Leroy Merlin → Vivienda > Equipamiento, Discrecionales
> - Media Markt → Gastos Personales > Gadgets, Discrecionales
>
> Añadir comandos CLI: `presupuesto reglas listar`, `presupuesto reglas exportar <archivo>`, `presupuesto reglas importar <archivo>`.

**Verificación**: `presupuesto reglas listar` muestra las reglas iniciales. Se puede buscar match para "compra eroski vitoria" y devuelve Alimentación > Compra.

---

## Paso 4 — Parser base y primer parser (N26)

> Crea `src/presupuesto/parsers/base.py` con una clase abstracta `ParserBase` que defina la interfaz:
>
> - `puede_parsear(ruta_archivo: str) -> bool` — detecta si el archivo es de este banco.
> - `parsear(ruta_archivo: str) -> list[MovimientoCrudo]` — extrae los movimientos.
> - `MovimientoCrudo` es un dataclass con: `fecha: date`, `concepto: str`, `importe: Decimal`, `concepto_original: str` (texto sin procesar).
>
> Luego implementa `src/presupuesto/parsers/n26.py` como primer parser. N26 exporta CSV con cabeceras conocidas. El parser debe:
>
> - Detectar el archivo por sus cabeceras CSV típicas de N26.
> - Extraer fecha, concepto (payee/merchant) e importe.
> - Normalizar fecha a `date` y el importe a `Decimal`.
> - Manejar encoding UTF-8 y posibles variaciones de cabeceras entre exportaciones antiguas y nuevas.
>
> Crea un CSV de ejemplo en `tests/fixtures/n26_ejemplo.csv` con 5-10 movimientos ficticios y un test que verifique el parseo. En la carpeta movimientos_bancos dentro de el proyecto hay un csv que empieza por n26 que tiene movimientos reales obtenidos de n26.

**Verificación**: El test pasa y parsea correctamente los movimientos del CSV de ejemplo.

---

## Paso 5 — Resto de parsers

> Implementa los parsers restantes, uno por fichero, todos heredando de `ParserBase`:
>
> - `openbank.py` — Soportar PDF y CSV/Excel. Para PDF usar `pdfplumber` para extraer tablas. Los movimientos de Openbank suelen tener: fecha, fecha valor, concepto, importe, saldo.
> - `kutxabank.py` — Soportar PDF y Excel. Kutxabank tiene un formato particular con movimientos en tabla.
> - `bbva.py` — Soportar PDF y Excel/CSV. BBVA incluye fecha operación, fecha valor, concepto, importe.
> - `trade_republic.py` — Soportar PDF y CSV. Movimientos de inversión y cuenta.
> - `abanca.py` — Soportar PDF y Excel/CSV.
>
> Para cada parser:
>
> 1. Implementar `puede_parsear()` que detecte el banco por contenido del archivo (cabeceras CSV, texto identificativo en PDF, etc.).
> 2. Implementar `parsear()` con extracción robusta.
> 3. Crear un fixture de ejemplo en `tests/fixtures/` y un test básico.
>
> Crear también `src/presupuesto/parsers/__init__.py` con una función `detectar_parser(ruta_archivo)` que pruebe todos los parsers y devuelva el que haga match, o `None` si ninguno lo reconoce.
>
> **Importante**: Los parsers de PDF serán los más difíciles de afinar porque dependen del formato exacto de cada banco. Implementar una versión inicial razonable y documentar con comentarios dónde habrá que ajustar cuando se pruebe con extractos reales.

**Verificación**: Cada parser tiene un test que pasa con su fixture. `detectar_parser()` identifica correctamente cada fixture.

---

## Paso 6 — Motor de categorización

Crea `src/presupuesto/categorizar.py` con una clase `Categorizador` que recibe `DatosMaestros` y `GestorReglas`. Implementa el método `categorizar(movimiento_crudo, cuenta) -> MovimientoCategorizado` con las 3 capas:

## Contexto de cuentas

Cada cuenta se usa en un contexto específico de la vida del usuario. Esta información debe usarse como señal adicional para afinar la categorización cuando el concepto es ambiguo. Definir un mapeo de contextos en un diccionario configurable:

```python
CONTEXTO_CUENTAS = {
    "Cuenta Hipoteca": {
        "descripcion": "Casa y vivienda",
        "categoria1_probable": ["Vivienda", "Finanzas"],
        "tipo_gasto_probable": "Fijos",
    },
    "Cuenta Ocio": {
        "descripcion": "Ocio y salidas",
        "categoria1_probable": ["Ocio", "Alimentación"],
        "tipo_gasto_probable": "Discrecionales",
    },
    "Cuenta Nomina": {
        "descripcion": "Nómina y gastos personales (Abanca)",
        "categoria1_probable": ["Ingresos", "Gastos Personales", "Alimentación"],
        "tipo_gasto_probable": None,
    },
    "Cuenta Ahorro N26": {
        "descripcion": "Ocio y gastos discrecionales",
        "categoria1_probable": ["Ocio", "Gastos Personales"],
        "tipo_gasto_probable": "Discrecionales",
    },
    "Kutxabank": {
        "descripcion": "Peajes y gastos de transporte",
        "categoria1_probable": ["Transporte"],
        "tipo_gasto_probable": "Fijos",
    },
    "Ahorro colchon": {
        "descripcion": "Ahorro Trade Republic",
        "categoria1_probable": ["Ahorro", "Finanzas"],
        "tipo_gasto_probable": "Fijos",
    },
    "EPSV": {
        "descripcion": "Jubilación Indexa Capital",
        "categoria1_probable": ["Ahorro"],
        "tipo_gasto_probable": "Fijos",
    },
    "Fondos": {
        "descripcion": "Inversión Indexa Capital",
        "categoria1_probable": ["Ahorro", "Finanzas"],
        "tipo_gasto_probable": "Discrecionales",
    },
}
```

## Las 3 capas de categorización

### Capa 1 — Reglas

Buscar match en `reglas.json` por el concepto del movimiento. Si hay match, devolver la categorización completa con confianza "alta" y `requiere_confirmacion = False`.

### Capa 2 — Similitud historial

Cargar los movimientos existentes de la hoja "Datos". Usar `rapidfuzz` para comparar el concepto con los conceptos/proveedores de movimientos anteriores.

- Si hay coincidencia con score > 85: confianza "media", `requiere_confirmacion = True` pero la sugerencia viene pre-rellenada.
- Si hay coincidencia con score entre 70 y 85: confianza "baja", `requiere_confirmacion = True`, sugerencia pre-rellenada pero marcada como dudosa.
- Si no hay coincidencia o score < 70: pasar a capa 3.

Cuando la similitud devuelve varias coincidencias posibles con scores parecidos, usar el contexto de la cuenta como desempate: priorizar la coincidencia cuya categoría1 esté en la lista `categoria1_probable` de la cuenta de origen.

### Capa 3 — Sin match

Devolver un `MovimientoCategorizado` parcial con confianza "ninguna" y `requiere_confirmacion = True`. Los campos de categorización quedan vacíos, pero usar el contexto de la cuenta para pre-rellenar sugerencias por defecto:

- Si la cuenta tiene `tipo_gasto_probable`, usarlo como sugerencia para tipo_gasto.
- Si la cuenta tiene `categoria1_probable` con un solo valor, usarlo como sugerencia para categoria1.
- Si tiene varios valores en `categoria1_probable`, no pre-rellenar (demasiado ambiguo).

Esto ayuda al usuario en el modo interactivo: en vez de partir de campos vacíos, ya tiene una pista basada en la cuenta.

## Dataclass de salida

`MovimientoCategorizado` es un dataclass con los 13 campos de la hoja "Datos":

1. año, mes — extraídos de la fecha del movimiento
2. categoria1, categoria2, categoria3 — de las reglas, similitud o interactivo
3. entidad — de las reglas o interactivo
4. importe — del movimiento crudo
5. proveedor — de las reglas o interactivo
6. tipo_gasto — de las reglas, contexto de cuenta, o interactivo
7. cuenta — la cuenta de origen
8. banco — autocompletado desde Claves
9. tipo_cuenta — autocompletado desde Claves
10. estado — siempre "Real"

Campos adicionales (no se escriben en el xlsx):

- `confianza`: "alta", "media", "baja" o "ninguna"
- `requiere_confirmacion`: bool
- `concepto_original`: texto original del extracto (útil para el modo interactivo y para generar reglas)

Autocompletar banco y tipo_cuenta usando `DatosMaestros.autocompletar_cuenta()`.

## Tests

Añadir tests en `tests/test_categorizar.py` que verifiquen:

- Capa 1: un movimiento con concepto "COMPRA EN EROSKI CENTER" se categoriza por regla con confianza "alta".
- Capa 2: un movimiento similar a uno existente en el historial se sugiere con confianza "media".
- Capa 2 con desempate: un concepto ambiguo que coincide con dos categorías distintas en el historial, pero viene de "Cuenta Ocio", prioriza la categoría de Ocio.
- Capa 3: un movimiento totalmente desconocido devuelve confianza "ninguna" con `requiere_confirmacion = True`.
- Capa 3 con contexto: un movimiento desconocido desde "Cuenta Hipoteca" sugiere tipo_gasto "Fijos".
- Autocompletado: banco y tipo_cuenta se rellenan correctamente a partir de la cuenta.

## Verificación

- Tests pasan.
- Un movimiento con "eroski" se categoriza por regla (confianza alta, no requiere confirmación).
- Un movimiento similar al historial se sugiere (confianza media, requiere confirmación).
- Un movimiento desconocido desde "Cuenta Ocio" sugiere tipo_gasto "Discrecionales".
- Un movimiento totalmente desconocido sin contexto útil devuelve campos vacíos.

---

## Paso 7 — Interfaz interactiva en terminal

> Crea `src/presupuesto/interactivo.py` usando la librería `rich` para una UI bonita en terminal. Implementar:
>
> 1. `mostrar_movimiento(movimiento_crudo, sugerencia)` — Muestra los datos del movimiento y la sugerencia (si existe) en un panel.
> 2. `pedir_categorizacion(datos_maestros, sugerencia)` — Flujo interactivo:
>    - Si hay sugerencia, mostrarla y permitir aceptar con Enter.
>    - Para cada campo (categoría1, categoría2, categoría3, entidad, proveedor, tipo_gasto), mostrar las opciones válidas del Maestro con búsqueda por texto (el usuario escribe unas letras y se filtran las opciones).
>    - Permitir saltar el movimiento con `s`.
>    - Permitir guardar progreso y salir con `q`.
> 3. `preguntar_guardar_regla(concepto, campos)` — Tras categorizar, preguntar si guardar como regla. Sugerir un patrón basado en el concepto (la palabra más significativa). Permitir al usuario editar el patrón.
> 4. `mostrar_resumen(movimientos)` — Tabla resumen con todos los movimientos procesados antes de escribir.
> 5. `pedir_confirmacion_escritura(num_movimientos)` — Confirmación final antes de escribir en el xlsx.

**Verificación**: Probar manualmente ejecutando las funciones con datos de ejemplo. La UI se ve bien en terminal, la búsqueda de opciones funciona.

---

## Paso 8 — Escritor de datos y detección de duplicados

# Paso 8 — Escritor de datos, agrupación y control de duplicados

Crea `src/presupuesto/escritor.py`, `src/presupuesto/duplicados.py` y `src/presupuesto/agrupador.py`.

## agrupador.py — Agrupación de movimientos

Antes de escribir en el xlsx, los movimientos categorizados se agrupan para reducir el número de filas. Dos movimientos se agrupan si comparten **todos** estos campos:

- Año
- Mes
- Categoría 1
- Categoría 2
- Categoría 3
- Entidad
- Proveedor
- Tipo de Gasto
- Cuenta
- Estado

Al agrupar, los importes se suman. Por ejemplo, 5 compras en Eroski en marzo 2025 desde Cuenta Nomina se convierten en una sola fila con el importe total.

Implementar una función `agrupar_movimientos(movimientos: list[MovimientoCategorizado]) -> list[MovimientoCategorizado]` que:

1. Agrupe por la combinación de campos indicada arriba.
2. Sume los importes de cada grupo.
3. Devuelva la lista agrupada.
4. Lleve un registro interno de cuántos movimientos originales componen cada grupo (útil para el resumen al usuario: "5 movimientos Eroski → 1 fila de -234.50€").

## duplicados.py — Control de duplicados con marcador de última importación

### Problema

Como los movimientos se agrupan, importar un extracto parcial y luego el completo podría generar entradas duplicadas o solapadas. Ejemplo: importo los movimientos de marzo a día 15, se agrupan las compras de Eroski en una fila. Luego importo el mes completo, y se generaría otra fila con compras de todo marzo que incluye las del 1 al 15.

### Solución: marcador de última importación

Mantener un fichero `~/.config/presupuesto/marcadores.json` que registre, por cada cuenta, la fecha del último movimiento importado:

```json
{
  "Cuenta Nomina": "2025-03-15",
  "Cuenta Ahorro N26": "2025-03-10",
  "Kutxabank": "2025-02-28",
  "Cuenta Hipoteca": "2025-03-01"
}
```

Comportamiento:

1. **Al parsear**: después de extraer los movimientos del extracto, filtrar automáticamente los que tengan fecha anterior o igual al marcador de esa cuenta. Informar al usuario: "Descartados X movimientos anteriores al 15/03/2025 (ya importados)".
2. **Al escribir**: si la importación se confirma y se escribe en el xlsx, actualizar el marcador con la fecha del último movimiento importado de esa cuenta.
3. **Override manual**: la opción `--desde YYYY-MM-DD` permite ignorar el marcador y forzar la importación desde una fecha concreta. Útil si algo salió mal y hay que reimportar.
4. **Primera importación**: si no hay marcador para una cuenta, importar todos los movimientos del extracto.

### Detección de duplicados adicional

Además del marcador, mantener una comprobación contra los datos existentes en la hoja "Datos" como red de seguridad. Comparar cada movimiento agrupado contra las filas existentes usando: Año + Mes + Categoría1 + Categoría2 + Cuenta + Importe (con tolerancia de ±0.01 por redondeos de agrupación). Si hay coincidencia, marcar como posible duplicado y pedir confirmación al usuario.

## escritor.py — Escritura en presupuesto.xlsx

Clase `EscritorDatos` que:

1. Abre `presupuesto.xlsx` con `openpyxl` (NO `data_only`, para preservar fórmulas).
2. Antes de escribir, crea backup automático: `presupuesto_backup_YYYYMMDD_HHMMSS.xlsx` en el mismo directorio.
3. Localiza la hoja "Datos" y encuentra la última fila con datos.
4. Recibe los movimientos ya agrupados y escribe cada uno como nueva fila con los 13 campos en orden (A→M).
5. Guarda el archivo preservando todas las demás hojas, formatos y fórmulas.
6. Tras escritura exitosa, devuelve el número de filas escritas para que el flujo principal actualice los marcadores.

**Importante**: Usar `openpyxl` sin `data_only` para preservar fórmulas. No crear un workbook nuevo, abrir el existente y solo añadir filas.

## Flujo completo (para contexto)

```
Movimientos crudos del parser
    ↓
Filtrar por marcador (descartar ya importados)
    ↓
Categorizar (paso 6)
    ↓
Agrupar por campos iguales dentro del mismo mes
    ↓
Detectar duplicados contra datos existentes
    ↓
Mostrar resumen al usuario
    ↓
Escribir en xlsx + actualizar marcador
```

## Tests

Añadir tests en `tests/test_escritor.py`, `tests/test_agrupador.py` y `tests/test_duplicados.py`:

**test_agrupador.py**:
- 5 movimientos con misma categoría y mes se agrupan en 1 con importe sumado.
- 2 movimientos con distinta categoría2 en el mismo mes NO se agrupan.
- 2 movimientos con misma categoría pero distinto mes NO se agrupan.
- El registro interno indica cuántos movimientos originales componen cada grupo.

**test_duplicados.py**:
- Marcador filtra correctamente movimientos anteriores a la fecha guardada.
- Sin marcador, pasan todos los movimientos.
- `--desde` ignora el marcador.
- Detección contra datos existentes encuentra duplicado por Año + Mes + Categoría1 + Categoría2 + Cuenta + Importe.
- Tolerancia de ±0.01 en importe funciona.

**test_escritor.py**:
- Se escriben filas correctamente en una copia del presupuesto.xlsx.
- El backup se crea antes de escribir.
- Las demás hojas no se modifican.
- Las fórmulas existentes se preservan.
- El marcador se actualiza tras escritura exitosa.

## Verificación

- Tests pasan.
- Importar un fixture de 20 movimientos genera menos de 20 filas (los que comparten categoría y mes se agrupan).
- Importar el mismo fixture dos veces: la segunda vez se descartan por marcador, o se detectan como duplicados.
- El backup se crea en el directorio del presupuesto.
- Abrir el xlsx resultante en Excel/LibreOffice y verificar que las demás hojas y fórmulas están intactas.

---

## Paso 9 — Comando principal `importar`

> Implementa el comando CLI `presupuesto importar` en `src/presupuesto/cli.py` que integre todo el flujo:
>
> 1. Recibe uno o más archivos como argumentos.
> 2. Opciones: `--banco` (forzar banco), `--cuenta` (forzar cuenta), `--dry-run` (no escribir), `--no-interactivo` (saltar desconocidos), `--verbose`.
> 3. Flujo por cada archivo:
>    a. Detectar parser (o usar `--banco`).
>    b. Parsear extracto → lista de movimientos crudos.
>    c. Determinar cuenta (por --cuenta, por config de cuentas_defecto, o preguntar).
>    d. Para cada movimiento: categorizar (3 capas) → si requiere confirmación → interactivo.
>    e. Detectar duplicados → avisar al usuario.
> 4. Mostrar resumen de todos los movimientos a importar.
> 5. Si no es dry-run: pedir confirmación → escribir → mostrar resultado.
> 6. Si es `--no-interactivo`: los movimientos sin categorizar se guardan en `pendientes.json`.
>
> Manejar errores de forma limpia: archivo no encontrado, banco no reconocido, presupuesto.xlsx no configurado, etc.

**Verificación**: `presupuesto importar tests/fixtures/n26_ejemplo.csv --dry-run` muestra los movimientos que se importarían sin escribir nada.

---

## Paso 10 — Comando `maestro` y pulido final

> Añadir el comando `presupuesto maestro` que muestra los valores válidos del maestro:
>
> - `presupuesto maestro categorias` — muestra categorías 1, 2 y 3.
> - `presupuesto maestro proveedores` — muestra lista de proveedores.
> - `presupuesto maestro cuentas` — muestra cuentas con su banco y tipo.
> - `presupuesto maestro todo` — muestra todo.
>
> Pulir:
>
> - Mensajes de error claros y con color (usando `rich`).
> - `--help` descriptivo en todos los comandos y subcomandos.
> - Si `archivo_presupuesto` no está configurado en ningún comando, avisar y guiar al usuario a `presupuesto config`.

**Verificación**: Todos los comandos funcionan, la ayuda es clara, los errores son legibles.

---

## Paso 11 — Tests de integración

> Crea tests de integración en `tests/test_integracion.py` que cubran el flujo completo:
>
> 1. Parsear un fixture CSV → categorizar con reglas → escribir en una copia del presupuesto.xlsx → verificar que las filas se añadieron correctamente.
> 2. Verificar detección de duplicados: importar el mismo fixture dos veces y comprobar que se detectan.
> 3. Verificar que el backup se crea antes de escribir.
> 4. Verificar que los valores escritos son válidos según el Maestro.
>
> Usar una copia temporal del presupuesto.xlsx para los tests (no modificar el original).

**Verificación**: `pytest` ejecuta todos los tests y pasan.

---

## Paso 12 - Los casos distintos

> **Caso 2**: Los fondos, añadir el balance mensual para el caso de los fondos y los EPSV.

## Notas para el desarrollo

- **Prioridad de parsers**: Empieza con N26 (CSV simple) y deja los parsers de PDF para el final. Son los más difíciles y necesitan extractos reales para afinar.
- **Reglas iniciales**: Revisa las reglas que genera y ajusta las que no te convenzan antes de seguir.
- **Pruebas con datos reales**: Después del paso 9, prueba con un extracto real en modo `--dry-run` para verificar el parser y la categorización. Ajusta lo que haga falta.
- **Extensión futura IA**: Si en el futuro quieres añadir una capa de IA, solo tendrás que crear `src/presupuesto/categorizar_ia.py` con una función que reciba el concepto y los valores del Maestro, y enchufarla entre la capa 2 y la capa 3 en `categorizar.py`. El resto del código no se toca.
