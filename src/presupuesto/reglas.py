"""Gestión de reglas de categorización automática.

Las reglas se almacenan en un fichero JSON con esta estructura:
{
  "reglas": [
    {
      "patron": "eroski",
      "tipo": "contains" | "startswith" | "regex",
      "campos": {
        "categoria1": "...", "categoria2": "...", "categoria3": "...",
        "entidad": "...", "proveedor": "...", "tipo_gasto": "..."
      }
    }
  ]
}
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TypedDict

# Ruta al fichero de reglas iniciales incluido en el paquete
REGLAS_INICIALES = Path(__file__).parent.parent.parent / "datos" / "reglas_iniciales.json"


class CamposCategoria(TypedDict):
    """Campos de categorización que devuelve una regla."""
    categoria1: str
    categoria2: str
    categoria3: str
    entidad: str
    proveedor: str
    tipo_gasto: str


class Regla(TypedDict):
    patron: str
    tipo: str  # contains | startswith | regex
    campos: CamposCategoria


def _hace_match(regla: Regla, concepto: str) -> bool:
    """Comprueba si una regla hace match con el concepto (case-insensitive)."""
    patron = regla["patron"]
    tipo = regla["tipo"]
    concepto_lower = concepto.lower()

    if tipo == "contains":
        return bool(re.search(r"\b" + re.escape(patron.lower()) + r"\b", concepto_lower))
    if tipo == "contains_all":
        palabras = patron.lower().split()
        return all(re.search(r"\b" + re.escape(p) + r"\b", concepto_lower) for p in palabras)
    if tipo == "startswith":
        return concepto_lower.startswith(patron.lower())
    if tipo == "regex":
        return bool(re.search(patron, concepto, re.IGNORECASE))

    return False


class GestorReglas:
    """Carga, guarda y consulta las reglas de categorización del usuario."""

    def __init__(self, ruta_fichero: str | Path):
        self.ruta = Path(ruta_fichero)
        self._reglas: list[Regla] = []
        self._inicializar()

    def _inicializar(self) -> None:
        """Carga el fichero de reglas. Si no existe, lo inicializa desde reglas_iniciales.json."""
        if not self.ruta.exists():
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            if REGLAS_INICIALES.exists():
                shutil.copy2(REGLAS_INICIALES, self.ruta)
            else:
                self._guardar_lista([])
        self._cargar()

    def _cargar(self) -> None:
        with open(self.ruta, encoding="utf-8") as f:
            datos = json.load(f)
        self._reglas = datos.get("reglas", [])

    def _guardar_lista(self, reglas: list[Regla]) -> None:
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump({"reglas": reglas}, f, ensure_ascii=False, indent=2)

    # --- Consulta ---

    def buscar_match(self, concepto: str) -> CamposCategoria | None:
        """Devuelve los campos de la primera regla que haga match, o None."""
        for regla in self._reglas:
            if _hace_match(regla, concepto):
                return regla["campos"]
        return None

    def buscar_match_con_patron(self, concepto: str) -> tuple[CamposCategoria, str] | None:
        """Devuelve (campos, patron) de la primera regla que haga match, o None."""
        for regla in self._reglas:
            if _hace_match(regla, concepto):
                return regla["campos"], regla["patron"]
        return None

    def listar(self) -> list[Regla]:
        """Devuelve una copia de la lista de reglas."""
        return list(self._reglas)

    def total(self) -> int:
        return len(self._reglas)

    # --- Modificación ---

    def añadir(self, patron: str, tipo: str, campos: CamposCategoria) -> None:
        """Añade una nueva regla al final de la lista y guarda."""
        if tipo not in ("contains", "contains_all", "startswith", "regex"):
            raise ValueError(f"Tipo de regla inválido: '{tipo}'. Use contains, contains_all, startswith o regex.")
        regla: Regla = {"patron": patron, "tipo": tipo, "campos": campos}
        self._reglas.append(regla)
        self._guardar_lista(self._reglas)

    def eliminar(self, patron: str) -> int:
        """Elimina todas las reglas con ese patrón exacto. Devuelve el número eliminadas."""
        antes = len(self._reglas)
        self._reglas = [r for r in self._reglas if r["patron"] != patron]
        eliminadas = antes - len(self._reglas)
        if eliminadas:
            self._guardar_lista(self._reglas)
        return eliminadas

    def guardar(self) -> None:
        """Guarda el estado actual en disco."""
        self._guardar_lista(self._reglas)

    # --- Importar / exportar ---

    def exportar(self, ruta_destino: str | Path) -> None:
        """Exporta las reglas actuales a otro fichero JSON."""
        shutil.copy2(self.ruta, ruta_destino)

    def importar_fusionar(self, ruta_origen: str | Path) -> int:
        """Añade las reglas del fichero origen que no existan ya (por patrón). Devuelve las añadidas."""
        with open(ruta_origen, encoding="utf-8") as f:
            datos = json.load(f)
        patrones_existentes = {r["patron"] for r in self._reglas}
        nuevas = [r for r in datos.get("reglas", []) if r["patron"] not in patrones_existentes]
        self._reglas.extend(nuevas)
        if nuevas:
            self._guardar_lista(self._reglas)
        return len(nuevas)

    def importar_reemplazar(self, ruta_origen: str | Path) -> int:
        """Reemplaza todas las reglas con las del fichero origen. Devuelve el total cargado."""
        with open(ruta_origen, encoding="utf-8") as f:
            datos = json.load(f)
        self._reglas = datos.get("reglas", [])
        self._guardar_lista(self._reglas)
        return len(self._reglas)

    def resetear(self) -> int:
        """Restaura las reglas iniciales. Devuelve el número de reglas cargadas."""
        if not REGLAS_INICIALES.exists():
            raise FileNotFoundError(f"No se encontró el fichero de reglas iniciales: {REGLAS_INICIALES}")
        return self.importar_reemplazar(REGLAS_INICIALES)
