# TODO — presupuesto-cli

## Fase 1: Cimientos

- [x] Crear estructura del proyecto (pyproject.toml, carpetas, entry point CLI)
- [x] Verificar que `pip install -e .` funciona y `presupuesto --help` responde
- [x] Implementar `maestro.py` — clase DatosMaestros que lea Maestro y Claves del xlsx
- [x] Implementar `config.py` — gestión de `~/.config/presupuesto/config.toml`
- [x] Comando `presupuesto config` para ver/editar configuración
- [x] Implementar `reglas.py` — carga, búsqueda y guardado de reglas.json
- [x] Crear `datos/reglas_iniciales.json` con mapeos de proveedores conocidos
- [x] Comandos `presupuesto reglas listar|exportar|importar`
- [x] Tests para maestro, config y reglas

## Fase 2: Parsers

- [x] Implementar `parsers/base.py` — clase abstracta ParserBase y dataclass MovimientoCrudo
- [x] Implementar `parsers/n26.py` + fixture de ejemplo + test
- [x] Implementar `parsers/openbank.py` (CSV + PDF) + fixture + test
- [x] Implementar `parsers/kutxabank.py` (CSV + PDF) + fixture + test
- [x] Implementar `parsers/bbva.py` (CSV + PDF) + fixture + test
- [x] Implementar `parsers/trade_republic.py` (CSV + PDF) + fixture + test
- [x] Implementar `parsers/abanca.py` (CSV + PDF) + fixture + test
- [x] Función `detectar_parser()` en `parsers/__init__.py`
- [x] Tests de detección automática de banco

## Fase 3: Lógica central

- [x] Implementar `categorizar.py` — 3 capas (reglas → similitud → None)
- [x] Implementar `interactivo.py` — UI con rich (mostrar movimiento, pedir categorización, guardar regla)
- [x] Implementar `duplicados.py` — detección por Año + Mes + Importe + Categoría2
- [x] Implementar `escritor.py` — escritura en hoja Datos con backup automático
- [x] Tests para categorización, duplicados y escritor

## Fase 4: Integración

- [x] Comando `presupuesto importar` con opciones (--banco, --cuenta, --dry-run, --no-interactivo, --verbose)
- [x] Comando `presupuesto maestro` (categorias, proveedores, cuentas, todo)
- [x] Mensajes de error claros y --help descriptivo en todos los comandos
- [x] Tests de integración (flujo completo con fixture → categorizar → escribir)
- [x] Probar con extracto real en --dry-run y ajustar parsers

## Fase 5: Mejoras

- [x] Cerrar mes y crear presupuesto años siguiente
- [x] Añadir campo cuenta a las reglas, para buscar primero por cuenta y afinar mas. Por ejemplo para la cuenta compra poder desglosar cuanto va a carniceria, fruteria...
- [x] Introducir valor en cuenta para crear entrada balance en la cuenta. Esto está pensado para fondos, EPSV, cuenta ocio, cuenta compra, etc.
- [x] Con lo presupuestado y el saldo actual, sacar una tabla con el balance esperado para cada mes que esta presupuestado
- [x] Añadir entrada en presupuesto. Que se pueda seleccionar multiples meses de lo ya presupuestado y añadir una nueva entrada con categorizacion y valor
- [x] Comando para presupuesto año vista y año en curso
- [x] Comand de vista que permita añadir una nueva entrada con categorización y valor (o duplicar usando lo de otro mes)
- [ ] Hacer automatico el aumento en cuentas destino de ahorro colchon, jubilacion, fondos, etc.
- [ ] Para las cuentas de fondos y jubilacion, el comando actulizar que meta el valor a actualizar como Finanzas - Intereses
