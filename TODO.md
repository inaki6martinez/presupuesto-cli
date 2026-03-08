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
- [ ] Implementar `parsers/bbva.py` (CSV + PDF) + fixture + test
- [ ] Implementar `parsers/trade_republic.py` (CSV + PDF) + fixture + test
- [x] Implementar `parsers/abanca.py` (CSV + PDF) + fixture + test
- [ ] Función `detectar_parser()` en `parsers/__init__.py`
- [ ] Tests de detección automática de banco

## Fase 3: Lógica central

- [ ] Implementar `categorizar.py` — 3 capas (reglas → similitud → None)
- [ ] Implementar `interactivo.py` — UI con rich (mostrar movimiento, pedir categorización, guardar regla)
- [ ] Implementar `duplicados.py` — detección por Año + Mes + Importe + Categoría2
- [ ] Implementar `escritor.py` — escritura en hoja Datos con backup automático
- [ ] Tests para categorización, duplicados y escritor

## Fase 4: Integración

- [ ] Comando `presupuesto importar` con opciones (--banco, --cuenta, --dry-run, --no-interactivo, --verbose)
- [ ] Comando `presupuesto maestro` (categorias, proveedores, cuentas, todo)
- [ ] Mensajes de error claros y --help descriptivo en todos los comandos
- [ ] Tests de integración (flujo completo con fixture → categorizar → escribir)
- [ ] Probar con extracto real en --dry-run y ajustar parsers
