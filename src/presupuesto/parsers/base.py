"""Interfaz base para todos los parsers de extractos bancarios."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class MovimientoCrudo:
    """Movimiento bancario tal como sale del parser, antes de categorizar."""
    fecha: date
    concepto: str          # Texto limpio y normalizado para mostrar / categorizar
    importe: Decimal       # Positivo = ingreso, negativo = gasto
    concepto_original: str  # Texto sin procesar extraído del archivo


class ParserBase(ABC):
    """Clase base que deben heredar todos los parsers de banco."""

    @abstractmethod
    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Devuelve True si este parser reconoce el archivo."""

    @abstractmethod
    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae y devuelve los movimientos del archivo."""
