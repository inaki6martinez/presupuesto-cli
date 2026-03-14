"""Gestión de reglas de categorización automática.

Las reglas se almacenan en un fichero JSON con esta estructura:
{
  "reglas": [
    {
      "patron": "eroski",
      "tipo": "contains" | "startswith" | "regex" | "contains_all",
      "cuenta": "Cuenta Nomina",   (opcional)
      "campos": {
        "categoria1": "...", "categoria2": "...", "categoria3": "...",
        "entidad": "...", "proveedor": "...", "tipo_gasto": "..."
      }
    }
  ]
}

Si una regla tiene "cuenta", solo se aplica cuando el movimiento pertenece a
esa cuenta. En la búsqueda se prueban primero las reglas específicas de la
cuenta y, si ninguna hace match, las reglas sin cuenta asignada.
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


class _ReglaBase(TypedDict):
    patron: str
    tipo: str  # contains | contains_all | startswith | regex
    campos: CamposCategoria


class Regla(_ReglaBase, total=False):
    cuenta: str  # opcional: limita la regla a una cuenta concreta


def describir_match(regla: Regla, concepto: str) -> dict | None:
    """Describe cómo una regla hace match con el concepto.

    Devuelve None si no hay match, o un dict con:
      - "busca":    descripción legible de lo que buscaba la regla.
      - "coincide": texto o lista de textos que coincidieron en el concepto.
    """
    patron = regla["patron"]
    tipo   = regla["tipo"]
    concepto_lower = concepto.lower()

    if tipo == "contains":
        m = re.search(r"\b" + re.escape(patron.lower()) + r"\b", concepto_lower)
        if not m:
            return None
        return {
            "busca":    f'frase exacta "{patron}"',
            "coincide": concepto[m.start():m.end()],
        }

    if tipo == "contains_all":
        palabras = patron.lower().split()
        encontradas = []
        for p in palabras:
            m = re.search(r"\b" + re.escape(p) + r"\b", concepto_lower)
            if not m:
                return None
            encontradas.append(concepto[m.start():m.end()])
        return {
            "busca":    f'todas las palabras {palabras}',
            "coincide": encontradas,
        }

    if tipo == "startswith":
        if not concepto_lower.startswith(patron.lower()):
            return None
        return {
            "busca":    f'empieza por "{patron}"',
            "coincide": concepto[:len(patron)],
        }

    if tipo == "regex":
        m = re.search(patron, concepto, re.IGNORECASE)
        if not m:
            return None
        return {
            "busca":    f'regex "{patron}"',
            "coincide": m.group(0),
        }

    return None


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

    def buscar_regla_con_match(self, concepto: str, cuenta: str = "") -> "Regla | None":
        """Devuelve la Regla completa (con tipo) de la primera que haga match, o None."""
        todas = self.buscar_todas_con_match(concepto, cuenta)
        return todas[0] if todas else None

    def buscar_todas_con_match(self, concepto: str, cuenta: str = "") -> "list[Regla]":
        """Devuelve todas las reglas que hacen match, en orden de prioridad.

        Primero las específicas de `cuenta`, luego las genéricas. La primera
        de la lista es la que realmente se aplica.
        """
        especificas = [r for r in self._reglas if r.get("cuenta", "") == cuenta and cuenta]
        genericas   = [r for r in self._reglas if not r.get("cuenta", "")]
        return [r for r in (*especificas, *genericas) if _hace_match(r, concepto)]

    def buscar_match(self, concepto: str, cuenta: str = "") -> CamposCategoria | None:
        """Devuelve los campos de la primera regla que haga match, o None."""
        resultado = self.buscar_match_con_patron(concepto, cuenta)
        return resultado[0] if resultado else None

    def buscar_match_con_patron(
        self, concepto: str, cuenta: str = ""
    ) -> tuple[CamposCategoria, str] | None:
        """Devuelve (campos, patron) de la primera regla que haga match, o None.

        Prioridad: primero las reglas específicas de `cuenta`, luego las genéricas
        (sin campo "cuenta"). Las reglas de otra cuenta nunca se aplican.
        """
        especificas = [r for r in self._reglas if r.get("cuenta", "") == cuenta and cuenta]
        genericas   = [r for r in self._reglas if not r.get("cuenta", "")]
        for regla in (*especificas, *genericas):
            if _hace_match(regla, concepto):
                return regla["campos"], regla["patron"]
        return None

    def listar(self) -> list[Regla]:
        """Devuelve una copia de la lista de reglas."""
        return list(self._reglas)

    def total(self) -> int:
        return len(self._reglas)

    # --- Modificación ---

    def añadir(self, patron: str, tipo: str, campos: CamposCategoria, cuenta: str = "") -> None:
        """Añade una nueva regla al final de la lista y guarda."""
        if tipo not in ("contains", "contains_all", "startswith", "regex"):
            raise ValueError(f"Tipo de regla inválido: '{tipo}'. Use contains, contains_all, startswith o regex.")
        regla: Regla = {"patron": patron, "tipo": tipo, "campos": campos}
        if cuenta:
            regla["cuenta"] = cuenta
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

    def recargar(self) -> int:
        """Recarga las reglas desde disco. Devuelve el número de reglas cargadas."""
        self._cargar()
        return len(self._reglas)

    def resetear(self) -> int:
        """Restaura las reglas iniciales. Devuelve el número de reglas cargadas."""
        if not REGLAS_INICIALES.exists():
            raise FileNotFoundError(f"No se encontró el fichero de reglas iniciales: {REGLAS_INICIALES}")
        return self.importar_reemplazar(REGLAS_INICIALES)
