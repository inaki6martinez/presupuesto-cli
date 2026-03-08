"""Parsers de extractos bancarios."""

from presupuesto.parsers.abanca import ParserAbanca
from presupuesto.parsers.base import MovimientoCrudo, ParserBase
from presupuesto.parsers.bbva import ParserBBVA
from presupuesto.parsers.ing import ParserING
from presupuesto.parsers.kutxabank import ParserKutxabank
from presupuesto.parsers.n26 import ParserN26
from presupuesto.parsers.openbank import ParserOpenbank

# Mapa banco → clase parser (clave = identificador para --banco y cuentas_defecto)
BANCO_A_PARSER: dict[str, type[ParserBase]] = {
    "n26":       ParserN26,
    "openbank":  ParserOpenbank,
    "abanca":    ParserAbanca,
    "kutxabank": ParserKutxabank,
    "bbva":      ParserBBVA,
    "ing":       ParserING,
}

# Mapa inverso: clase parser → banco key
PARSER_A_BANCO: dict[type[ParserBase], str] = {v: k for k, v in BANCO_A_PARSER.items()}

__all__ = [
    "MovimientoCrudo", "ParserBase",
    "ParserN26", "ParserOpenbank", "ParserAbanca",
    "ParserKutxabank", "ParserBBVA", "ParserING",
    "BANCO_A_PARSER", "PARSER_A_BANCO", "detectar_parser",
]


def detectar_parser(ruta_archivo: str) -> ParserBase | None:
    """Detecta automáticamente el parser adecuado para el archivo dado.

    Prueba cada parser en orden y devuelve el primero que reconoce el archivo.
    Devuelve None si ninguno lo reconoce.
    """
    for parser_class in BANCO_A_PARSER.values():
        parser = parser_class()
        try:
            if parser.puede_parsear(ruta_archivo):
                return parser
        except Exception:
            continue
    return None
