"""Gestión de la configuración de presupuesto-cli.

El fichero de configuración se guarda en ~/.config/presupuesto/config.toml.
Si no existe, se crea automáticamente con los valores por defecto.
"""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path

import tomli_w

DIRECTORIO_CONFIG = Path("~/.config/presupuesto").expanduser()
RUTA_CONFIG = DIRECTORIO_CONFIG / "config.toml"

CONFIG_DEFECTO: dict = {
    "archivo_presupuesto": "",
    "archivo_reglas": str(DIRECTORIO_CONFIG / "reglas.json"),
    "cuentas_defecto": {
        "openbank": "Cuenta Nomina",
        "n26": "Cuenta Ahorro N26",
        "kutxabank": "Kutxabank",
        "bbva": "Cuenta Hipoteca",
        "trade_republic": "Ahorro colchon",
        "abanca": "",
    },
}


def _fusionar_defecto(defecto: dict, actual: dict) -> dict:
    """Fusiona recursivamente, añadiendo claves que falten del defecto."""
    resultado = dict(defecto)
    for clave, valor in actual.items():
        if clave in resultado and isinstance(resultado[clave], dict) and isinstance(valor, dict):
            resultado[clave] = _fusionar_defecto(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado


def cargar_config() -> dict:
    """Carga la configuración desde disco. Crea el fichero si no existe."""
    DIRECTORIO_CONFIG.mkdir(parents=True, exist_ok=True)

    if not RUTA_CONFIG.exists():
        guardar_config(CONFIG_DEFECTO)
        return dict(CONFIG_DEFECTO)

    with open(RUTA_CONFIG, "rb") as f:
        leido = tomllib.load(f)

    # Asegurar que siempre existen todas las claves por defecto
    return _fusionar_defecto(CONFIG_DEFECTO, leido)


def guardar_config(config: dict) -> None:
    """Guarda la configuración en disco."""
    DIRECTORIO_CONFIG.mkdir(parents=True, exist_ok=True)
    with open(RUTA_CONFIG, "wb") as f:
        tomli_w.dump(config, f)


def obtener_archivo_presupuesto(config: dict) -> Path | None:
    """Devuelve la ruta al presupuesto.xlsx expandida, o None si no está configurada."""
    valor = config.get("archivo_presupuesto", "").strip()
    if not valor:
        return None
    return Path(valor).expanduser()


def establecer_archivo_presupuesto(ruta: str | Path) -> None:
    """Guarda la ruta del archivo presupuesto en la configuración."""
    config = cargar_config()
    config["archivo_presupuesto"] = str(Path(ruta).expanduser())
    guardar_config(config)


def obtener_cuenta_defecto(config: dict, banco: str) -> str:
    """Devuelve la cuenta por defecto para un banco dado (clave en minúsculas)."""
    return config.get("cuentas_defecto", {}).get(banco.lower(), "")
