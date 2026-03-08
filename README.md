# presupuesto-cli

Herramienta CLI para importar extractos bancarios (PDF, Excel, CSV) a `presupuesto.xlsx`, categorizando cada movimiento según las hojas "Maestro" y "Claves".

## Bancos soportados

- Openbank (PDF, CSV)
- Kutxabank (PDF, Excel)
- N26 (CSV)
- BBVA (PDF, Excel/CSV)
- Trade Republic (PDF, CSV)
- Abanca (PDF, Excel/CSV)

## Instalación

```bash
pip install -e .
```

## Uso

```bash
# Importar un extracto
presupuesto importar extracto.csv

# Simular sin escribir
presupuesto importar extracto.csv --dry-run

# Ver reglas de categorización
presupuesto reglas listar

# Configuración
presupuesto config

# Consultar el Maestro
presupuesto maestro categorias
presupuesto maestro cuentas
```

## Estructura del proyecto

```
src/presupuesto/
├── cli.py          # Comandos CLI (click)
├── config.py       # Gestión de configuración (~/.config/presupuesto/)
├── maestro.py      # Lector de hojas Maestro y Claves
├── reglas.py       # Motor de reglas de categorización
├── categorizar.py  # Categorizador (reglas + similitud + interactivo)
├── interactivo.py  # UI de terminal con rich
├── escritor.py     # Escritura en presupuesto.xlsx con backup
├── duplicados.py   # Detección de duplicados
└── parsers/
    ├── base.py         # Clase abstracta ParserBase + MovimientoCrudo
    ├── n26.py
    ├── openbank.py
    ├── kutxabank.py
    ├── bbva.py
    ├── trade_republic.py
    └── abanca.py

datos/
└── reglas_iniciales.json

tests/
├── fixtures/       # Archivos de ejemplo para tests
└── test_*.py
```
