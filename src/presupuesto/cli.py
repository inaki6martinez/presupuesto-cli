"""Punto de entrada principal de la CLI."""

import dataclasses
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

consola = Console()

# Ruta al fichero de pendientes
_RUTA_PENDIENTES = Path("~/.config/presupuesto/pendientes.json").expanduser()

# Ruta al fichero de movimientos sin regla (generado por --dry-run)
_RUTA_SIN_REGLA = Path("~/.config/presupuesto/sin_regla.json").expanduser()

# Ruta al fichero de recuperación (generado cuando falla la escritura en xlsx)
_RUTA_RECOVERY = Path("~/.config/presupuesto/recovery.json").expanduser()


@click.group()
@click.version_option(package_name="presupuesto-cli")
def cli():
    """Herramienta para importar extractos bancarios a presupuesto.xlsx.

    Importa extractos de Openbank, Kutxabank, N26, BBVA, Trade Republic
    y Abanca, categorizando cada movimiento según el Maestro.
    """


@click.command("importar")
@click.argument("archivos", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--banco", help="Forzar banco (n26, openbank, kutxabank, bbva, ing, abanca).")
@click.option("--cuenta", help="Forzar cuenta destino.")
@click.option("--dry-run", is_flag=True, help="Simular sin escribir en el archivo.")
@click.option("--no-interactivo", is_flag=True, help="Guardar desconocidos en pendientes.json sin preguntar.")
@click.option("--verbose", "-v", is_flag=True, help="Mostrar información detallada.")
@click.option("--desde", default=None, metavar="YYYY-MM-DD",
              help="Importar desde esta fecha (ignora el marcador guardado).")
@click.option("--exportar", default=None, metavar="FICHERO.csv",
              help="Guarda el resultado de la categorización en un CSV.")
def cmd_importar(archivos, banco, cuenta, dry_run, no_interactivo, verbose, desde, exportar):
    """Importa uno o varios extractos bancarios a presupuesto.xlsx."""
    from presupuesto.agrupador import agrupar_movimientos
    from presupuesto.categorizar import Categorizador
    from presupuesto.config import cargar_config
    from presupuesto.duplicados import GestorMarcadores, detectar_duplicados
    from presupuesto.escritor import EscritorDatos
    from presupuesto.interactivo import mostrar_resumen
    from presupuesto.maestro import DatosMaestros

    # --- Validar fecha --desde ---
    fecha_desde: date | None = None
    if desde:
        try:
            fecha_desde = date.fromisoformat(desde)
        except ValueError:
            consola.print(f"[red]Formato de fecha inválido:[/red] '{desde}'. Usa YYYY-MM-DD.")
            return

    # --- Cargar infraestructura ---
    ruta_xlsx = _obtener_ruta_xlsx()
    if ruta_xlsx is None:
        return

    try:
        datos_maestros = DatosMaestros(ruta_xlsx)
    except Exception as e:
        consola.print(f"[red]Error al leer el Maestro:[/red] {e}")
        return

    gestor_reglas = _crear_gestor_reglas()
    gestor_marcadores = GestorMarcadores()

    categorizador = Categorizador(datos_maestros, gestor_reglas)
    n_historial = categorizador.cargar_historial(ruta_xlsx)
    if verbose:
        consola.print(f"[dim]Historial cargado: {n_historial} entradas únicas.[/dim]")

    config = cargar_config()

    # Acumuladores para el flujo completo (puede haber múltiples archivos)
    # Cada entrada: (MovimientoCrudo, MovimientoCategorizado, cuenta_str)
    todos_aceptados: list[tuple] = []
    pendientes: list[dict] = []
    salir_solicitado = False

    # --- Procesar cada archivo ---
    for archivo in archivos:
        if salir_solicitado:
            break

        archivo_nombre = Path(archivo).name

        # 1. Detectar parser
        parser_banco = _obtener_parser_y_banco(archivo, banco)
        if parser_banco is None:
            continue
        parser_obj, banco_key = parser_banco

        if verbose:
            consola.print(f"\n[bold]{archivo_nombre}[/bold]  [dim]banco={banco_key}[/dim]")

        # 2. Parsear
        try:
            movimientos_crudos = parser_obj.parsear(archivo)
        except Exception as e:
            consola.print(f"[red]Error al parsear {archivo_nombre}:[/red] {e}")
            continue

        consola.print(
            f"\n[bold]{archivo_nombre}[/bold]  "
            f"[dim]{len(movimientos_crudos)} movimiento(s) leídos[/dim]"
        )

        # 3. Determinar cuenta
        cuenta_archivo = _determinar_cuenta(cuenta, banco_key, config, datos_maestros)
        if not cuenta_archivo:
            continue

        if verbose:
            consola.print(f"  [dim]Cuenta: {cuenta_archivo}[/dim]")

        # 4. Filtrar por marcador
        movimientos_crudos, descartados = gestor_marcadores.filtrar_movimientos(
            movimientos_crudos, cuenta_archivo, desde=fecha_desde
        )
        if descartados:
            consola.print(f"  [dim]Descartados {descartados} movimiento(s) ya importados.[/dim]")

        if not movimientos_crudos:
            consola.print(f"  [yellow]Sin movimientos nuevos.[/yellow]")
            continue

        consola.print(f"  [dim]{len(movimientos_crudos)} movimiento(s) a procesar.[/dim]")

        # 5. Categorizar (con o sin interactividad)
        # Usamos índice explícito para poder volver al movimiento anterior.
        # snapshots[i] = (len(todos_aceptados), len(pendientes)) justo antes de procesar i,
        # lo que permite deshacer el efecto de procesar i-1 al pedir "volver".
        snapshots: list[tuple[int, int]] = []
        idx = 0
        forzar_interactivo = False   # True tras un "volver" para no auto-aceptar
        while idx < len(movimientos_crudos):
            mov_crudo = movimientos_crudos[idx]

            # Guardar snapshot la primera vez que llegamos a este índice
            if idx == len(snapshots):
                snapshots.append((len(todos_aceptados), len(pendientes)))

            sugerencia = categorizador.categorizar(mov_crudo, cuenta_archivo)

            if not sugerencia.requiere_confirmacion and not forzar_interactivo:
                # Capa 1 (alta confianza) → aceptar automáticamente
                todos_aceptados.append((mov_crudo, sugerencia, cuenta_archivo))
                if verbose:
                    consola.print(
                        f"  [green]✓[/green] {mov_crudo.concepto[:50]}  "
                        f"→ {sugerencia.categoria1}"
                    )
                idx += 1
                continue

            forzar_interactivo = False

            if dry_run:
                # En dry-run: aceptar la sugerencia tal cual para mostrarla en el resumen
                todos_aceptados.append((mov_crudo, sugerencia, cuenta_archivo))
                idx += 1
                continue

            if no_interactivo:
                # Sin interactividad → guardar en pendientes
                pendientes.append({
                    "archivo": archivo_nombre,
                    "cuenta": cuenta_archivo,
                    "fecha": str(mov_crudo.fecha),
                    "concepto": mov_crudo.concepto,
                    "importe": str(mov_crudo.importe),
                    "concepto_original": mov_crudo.concepto_original,
                })
                idx += 1
                continue

            # Flujo interactivo
            resultado = _procesar_interactivo(
                mov_crudo, sugerencia, datos_maestros, gestor_reglas
            )

            if resultado == "saltar":
                idx += 1
                continue

            if resultado == "volver":
                if idx > 0:
                    # Restaurar estado previo al movimiento anterior y reprocesarlo
                    snap_ac, snap_pend = snapshots[idx - 1]
                    del todos_aceptados[snap_ac:]
                    del pendientes[snap_pend:]
                    del snapshots[idx:]  # el snapshot de idx se regenerará al volver
                    idx -= 1
                    forzar_interactivo = True  # mostrar TUI aunque sea alta confianza
                else:
                    consola.print("  [dim]Ya estás en el primer movimiento.[/dim]")
                continue

            if resultado == "salir":
                salir_solicitado = True
                break

            if isinstance(resultado, list):
                # Movimiento dividido: varias partes categorizadas
                for cat_parte in resultado:
                    todos_aceptados.append((mov_crudo, cat_parte, cuenta_archivo))
            else:
                todos_aceptados.append((mov_crudo, resultado, cuenta_archivo))
            idx += 1

    # --- Agrupar ---
    movs_cat = [cat for (_, cat, _) in todos_aceptados]
    agrupados = agrupar_movimientos(movs_cat)

    # --- Expandir cuotas hipotecarias ---
    from presupuesto.hipoteca import expandir_hipotecas
    agrupados = expandir_hipotecas(agrupados, ruta_xlsx, datos_maestros)

    # --- Dry-run: resumen y salir ---
    if dry_run:
        mostrar_resumen(agrupados)
        if exportar and agrupados:
            _exportar_csv(agrupados, todos_aceptados, exportar)
        consola.print("\n[yellow]--dry-run activo: no se ha escrito nada.[/yellow]")
        if pendientes:
            consola.print(
                f"[dim]Se habrían guardado {len(pendientes)} pendientes.[/dim]"
            )
        sin_regla = [m for m in agrupados if m.confianza in ("baja", "ninguna")]
        if sin_regla:
            n_guardados = _guardar_sin_regla(sin_regla)
            consola.print(
                f"  [dim]{n_guardados} concepto(s) sin regla guardados → "
                f"`presupuesto reglas revisar`[/dim]"
            )
        return

    if not agrupados and not pendientes:
        consola.print("[yellow]No hay movimientos para importar.[/yellow]")
        return

    if not agrupados:
        _guardar_pendientes(pendientes)
        return

    # --- Detectar duplicados + revisión final (con opción de volver) ---
    from presupuesto.tui_revision import TUIRevisionDuplicados, TUIRevisionFinal

    duplicados = detectar_duplicados(agrupados, ruta_xlsx)
    agrupados_sin_dups = agrupados  # referencia inicial

    while True:
        # Pantalla de duplicados
        if duplicados:
            tui_dups = TUIRevisionDuplicados(duplicados)
            excluidos_idx = tui_dups.run()
            excluir_ids = {id(duplicados[i][0]) for i in excluidos_idx}
            agrupados_sin_dups = [m for m in agrupados if id(m) not in excluir_ids]
        else:
            agrupados_sin_dups = agrupados

        if not agrupados_sin_dups:
            consola.print("[yellow]Todos los movimientos fueron excluidos.[/yellow]")
            return

        # Pantalla de revisión final
        tui_final = TUIRevisionFinal(agrupados_sin_dups, datos_maestros)
        resultado_final = tui_final.run()
        if resultado_final == "volver":
            continue   # volver a la pantalla de duplicados
        if not resultado_final:
            consola.print("[dim]Importación cancelada.[/dim]")
            return
        break  # confirmado

    agrupados = agrupados_sin_dups

    if exportar:
        _exportar_csv(agrupados, todos_aceptados, exportar)

    if pendientes:
        consola.print(
            f"[yellow]{len(pendientes)} movimiento(s) sin categorizar "
            "quedarán en pendientes.[/yellow]"
        )

    try:
        escritor = EscritorDatos(ruta_xlsx)
        n_escritos = escritor.escribir(agrupados)
    except Exception as e:
        consola.print(f"[red]Error al escribir en el xlsx:[/red] {e}")
        ruta_guardada = _guardar_recovery(agrupados, ruta_xlsx)
        consola.print(
            f"[yellow]Los {len(agrupados)} movimiento(s) se han guardado para recuperación.[/yellow]\n"
            f"  Cierra el archivo xlsx y ejecuta:  [bold]presupuesto recuperar[/bold]\n"
            f"  (fichero: {ruta_guardada})"
        )
        return

    _RUTA_RECOVERY.unlink(missing_ok=True)   # limpiar recovery si existía
    consola.print(f"\n[green]✓ {n_escritos} fila(s) escritas en presupuesto.xlsx.[/green]")

    # --- Actualizar marcadores y revisiones ---
    from presupuesto.duplicados import GestorRevisiones
    gestor_revisiones = GestorRevisiones()
    hoy = date.today()

    max_fechas: dict[str, date] = defaultdict(lambda: date.min)
    for mov_crudo, _, cuenta_m in todos_aceptados:
        if mov_crudo.fecha > max_fechas[cuenta_m]:
            max_fechas[cuenta_m] = mov_crudo.fecha
    for cuenta_m, fecha_m in max_fechas.items():
        gestor_marcadores.actualizar_marcador(cuenta_m, fecha_m)
        gestor_revisiones.registrar_revision(cuenta_m, hoy)
        if verbose:
            consola.print(f"  [dim]Marcador actualizado: {cuenta_m} → {fecha_m}[/dim]")
            consola.print(f"  [dim]Revisión registrada:  {cuenta_m} → {hoy}[/dim]")

    # --- Guardar pendientes si los hay ---
    if pendientes:
        _guardar_pendientes(pendientes)


def _crear_gestor_reglas():
    """Devuelve un GestorReglas inicializado con la ruta del config."""
    from presupuesto.config import cargar_config
    from presupuesto.reglas import GestorReglas

    config = cargar_config()
    ruta = config.get("archivo_reglas", "~/.config/presupuesto/reglas.json")
    return GestorReglas(ruta)


# ---------------------------------------------------------------------------
# Helpers del comando importar
# ---------------------------------------------------------------------------

def _obtener_ruta_xlsx() -> Path | None:
    """Devuelve la ruta al presupuesto.xlsx validada, o None si no está configurado."""
    from presupuesto.config import cargar_config, obtener_archivo_presupuesto

    config = cargar_config()
    ruta = obtener_archivo_presupuesto(config)
    if not ruta:
        consola.print(
            "[bold red]Error:[/bold red] presupuesto.xlsx no configurado.\n"
            "  Configúralo con: "
            "[bold]presupuesto config --set-archivo /ruta/presupuesto.xlsx[/bold]"
        )
        return None
    if not ruta.exists():
        consola.print(
            f"[bold red]Error:[/bold red] Archivo no encontrado: [dim]{ruta}[/dim]\n"
            "  Comprueba la ruta con: [bold]presupuesto config[/bold]"
        )
        return None
    return ruta


def _cargar_datos_maestros():
    """Carga DatosMaestros desde el xlsx configurado, o None si falla."""
    ruta = _obtener_ruta_xlsx()
    if ruta is None:
        return None
    from presupuesto.maestro import DatosMaestros
    try:
        return DatosMaestros(ruta)
    except KeyError as e:
        consola.print(
            f"[bold red]Error:[/bold red] No se encontró la hoja {e} en el archivo.\n"
            "  Comprueba que el archivo es un presupuesto.xlsx válido."
        )
        return None
    except Exception as e:
        consola.print(f"[bold red]Error al leer el Maestro:[/bold red] {e}")
        return None


def _obtener_parser_y_banco(
    archivo: str, banco_forzado: str | None
) -> tuple | None:
    """Devuelve (parser, banco_key) o None si no se reconoce el archivo."""
    from presupuesto.parsers import BANCO_A_PARSER, PARSER_A_BANCO, detectar_parser

    if banco_forzado:
        clave = banco_forzado.lower().replace("-", "_")
        cls = BANCO_A_PARSER.get(clave)
        if cls is None:
            bancos = ", ".join(BANCO_A_PARSER)
            consola.print(
                f"[red]Banco no reconocido:[/red] '{banco_forzado}'. "
                f"Valores válidos: {bancos}"
            )
            return None
        return cls(), clave

    parser = detectar_parser(archivo)
    if parser is None:
        consola.print(
            f"[red]No se reconoce el formato de:[/red] {Path(archivo).name}\n"
            "  Usa [bold]--banco[/bold] para forzar el banco."
        )
        return None
    banco_key = PARSER_A_BANCO.get(type(parser), "")
    return parser, banco_key


def _determinar_cuenta(
    cuenta_forzada: str | None,
    banco_key: str,
    config: dict,
    datos_maestros,
) -> str | None:
    """Devuelve la cuenta a usar, preguntando al usuario si es necesario."""
    from presupuesto.config import obtener_cuenta_defecto

    if cuenta_forzada:
        return cuenta_forzada

    cuenta_defecto = obtener_cuenta_defecto(config, banco_key)
    if cuenta_defecto:
        return cuenta_defecto

    # No hay cuenta configurada → preguntar
    cuentas = datos_maestros.cuentas
    if not cuentas:
        consola.print("[red]Error:[/red] No hay cuentas definidas en el Maestro.")
        return None

    consola.print(f"\n[yellow]No hay cuenta por defecto para '{banco_key}'.[/yellow]")
    for i, c in enumerate(cuentas, 1):
        consola.print(f"  [dim]{i:2d}.[/dim] {c}")
    try:
        entrada = consola.input("\n  Selecciona el número de cuenta: ").strip()
        n = int(entrada)
        if 1 <= n <= len(cuentas):
            return cuentas[n - 1]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    consola.print("[yellow]Cuenta no válida. Saltando archivo.[/yellow]")
    return None


def _procesar_interactivo(
    mov_crudo,
    sugerencia,
    datos_maestros,
    gestor_reglas,
) -> object:
    """Flujo interactivo para un movimiento que requiere confirmación.

    Returns:
        MovimientoCategorizado        — aceptado/editado por el usuario.
        list[MovimientoCategorizado]  — si el usuario dividió el movimiento.
        "saltar"                      — saltar este movimiento.
        "salir"                       — detener la importación.
        "volver"                      — volver al movimiento anterior.
    """
    from presupuesto.interactivo import (
        mostrar_movimiento,
        pedir_categorizacion,
        preguntar_guardar_regla,
    )
    from presupuesto.tui_dividir import TUIDividir

    consola.rule()
    mostrar_movimiento(mov_crudo, sugerencia)

    # ── Ofrecer dividir ───────────────────────────────────────────────────────
    if click.confirm("  ¿Dividir este movimiento?", default=False):
        partes = TUIDividir(mov_crudo).run()
        if partes is None:
            consola.print("  [dim]División cancelada.[/dim]")
        else:
            cats: list = []
            for i, (importe_parte, desc_parte) in enumerate(partes):
                consola.print(
                    f"\n  [bold]Parte {i + 1}/{len(partes)}[/bold]  "
                    f"{'[red]' if importe_parte < 0 else '[green]'}"
                    f"{importe_parte:+.2f}€"
                    f"{'[/red]' if importe_parte < 0 else '[/green]'}"
                    + (f"  {desc_parte}" if desc_parte else "")
                )
                sug_parte = dataclasses.replace(
                    sugerencia,
                    importe=importe_parte,
                    concepto_original=(
                        f"{mov_crudo.concepto_original or mov_crudo.concepto}"
                        + (f" [{desc_parte}]" if desc_parte else f" [parte {i + 1}]")
                    ),
                )
                resultado_parte = pedir_categorizacion(datos_maestros, sug_parte)
                if resultado_parte in ("saltar", "salir", "volver"):
                    return resultado_parte
                cat_parte = dataclasses.replace(
                    sug_parte,
                    **resultado_parte,
                    confianza="alta",
                    fuente="manual",
                    requiere_confirmacion=False,
                )
                cats.append(cat_parte)
            return cats

    # ── Flujo normal (sin división) ───────────────────────────────────────────
    resultado = pedir_categorizacion(datos_maestros, sugerencia)

    if resultado in ("saltar", "salir", "volver"):
        return resultado

    # El usuario rellenó los campos → actualizar el MovimientoCategorizado
    cat_final = dataclasses.replace(
        sugerencia,
        **resultado,
        confianza="alta",
        fuente="manual",
        requiere_confirmacion=False,
    )

    # Ofrecer guardar como regla
    regla = preguntar_guardar_regla(mov_crudo.concepto, resultado, cuenta=sugerencia.cuenta)
    if regla:
        gestor_reglas.añadir(
            patron=regla["patron"],
            tipo=regla["tipo"],
            campos=regla["campos"],
            cuenta=regla.get("cuenta", ""),
        )
        cuenta_info = f" [{regla['cuenta']}]" if regla.get("cuenta") else ""
        consola.print(f"  [green]Regla guardada:[/green] '{regla['patron']}'{cuenta_info}")

    return cat_final


def _exportar_csv(agrupados, todos_aceptados, ruta_csv: str) -> None:
    """Exporta el resultado de la categorización a un CSV.

    Incluye el concepto original completo (del movimiento crudo) y la confianza.
    Si un movimiento agrupado representa varios movimientos crudos, se expande
    una fila por cada movimiento crudo original.
    """
    import csv

    # Mapa concepto_original → confianza desde los movimientos categorizados
    # (antes de agrupar, cada MovimientoCategorizado tiene su concepto_original)
    # todos_aceptados: list of (MovimientoCrudo, MovimientoCategorizado, cuenta)
    filas: list[dict] = []
    for mov_crudo, mov_cat, _ in todos_aceptados:
        filas.append({
            "concepto_original": mov_crudo.concepto_original or mov_crudo.concepto,
            "fecha":             str(mov_crudo.fecha),
            "mes":               mov_cat.mes,
            "año":               mov_cat.año,
            "importe":           float(mov_crudo.importe),
            "categoria1":        mov_cat.categoria1,
            "categoria2":        mov_cat.categoria2,
            "categoria3":        mov_cat.categoria3,
            "entidad":           mov_cat.entidad,
            "proveedor":         mov_cat.proveedor,
            "tipo_gasto":        mov_cat.tipo_gasto,
            "cuenta":            mov_cat.cuenta,
            "banco":             mov_cat.banco,
            "confianza":         mov_cat.confianza,
            "fuente":            mov_cat.fuente,
        })

    if not filas:
        consola.print("[yellow]No hay movimientos para exportar.[/yellow]")
        return

    campos = list(filas[0].keys())
    ruta = Path(ruta_csv)
    try:
        with ruta.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
            writer.writeheader()
            writer.writerows(filas)
        consola.print(
            f"[green]✓ {len(filas)} movimiento(s) exportados a:[/green] {ruta}"
        )
    except OSError as e:
        consola.print(f"[red]Error al exportar CSV:[/red] {e}")


def _guardar_sin_regla(movimientos) -> int:
    """Guarda movimientos de baja/ninguna confianza en sin_regla.json.

    Deduplica por concepto_original para evitar entradas repetidas entre
    varias ejecuciones de --dry-run. Devuelve el número de entradas nuevas.
    """
    _RUTA_SIN_REGLA.parent.mkdir(parents=True, exist_ok=True)
    existentes: list[dict] = []
    if _RUTA_SIN_REGLA.exists():
        try:
            existentes = json.loads(_RUTA_SIN_REGLA.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existentes = []

    conceptos_existentes = {e.get("concepto_original", "") for e in existentes}

    nuevas: list[dict] = []
    for m in movimientos:
        clave = m.concepto_original or ""
        if clave in conceptos_existentes:
            continue
        conceptos_existentes.add(clave)
        nuevas.append({
            "concepto_original": clave,
            "importe": float(m.importe),
            "mes": m.mes,
            "año": m.año,
            "cuenta": m.cuenta,
            "confianza": m.confianza,
            "sugerencia": {
                "categoria1": m.categoria1,
                "categoria2": m.categoria2,
                "categoria3": m.categoria3,
                "entidad":    m.entidad,
                "proveedor":  m.proveedor,
                "tipo_gasto": m.tipo_gasto,
            },
        })

    if nuevas:
        existentes.extend(nuevas)
        _RUTA_SIN_REGLA.write_text(
            json.dumps(existentes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return len(nuevas)


def _guardar_recovery(agrupados: list, ruta_xlsx: str) -> Path:
    """Guarda los movimientos categorizados en recovery.json para poder reintentarlos."""
    from datetime import datetime
    _RUTA_RECOVERY.parent.mkdir(parents=True, exist_ok=True)
    movs = []
    for m in agrupados:
        d = dataclasses.asdict(m)
        d["importe"] = str(d["importe"])
        movs.append(d)
    datos = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ruta_xlsx": str(ruta_xlsx),
        "movimientos": movs,
    }
    _RUTA_RECOVERY.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return _RUTA_RECOVERY


def _cargar_recovery() -> tuple[list, str] | None:
    """Carga los movimientos de recovery.json. Devuelve (movimientos, ruta_xlsx) o None."""
    if not _RUTA_RECOVERY.exists():
        return None
    from decimal import Decimal
    from presupuesto.categorizar import MovimientoCategorizado
    datos = json.loads(_RUTA_RECOVERY.read_text(encoding="utf-8"))
    movs = []
    for d in datos["movimientos"]:
        d["importe"] = Decimal(d["importe"])
        movs.append(MovimientoCategorizado(**d))
    return movs, datos["ruta_xlsx"]


def _guardar_pendientes(pendientes: list[dict]) -> None:
    """Añade los movimientos pendientes al fichero pendientes.json."""
    _RUTA_PENDIENTES.parent.mkdir(parents=True, exist_ok=True)
    existentes: list[dict] = []
    if _RUTA_PENDIENTES.exists():
        try:
            existentes = json.loads(_RUTA_PENDIENTES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existentes = []
    existentes.extend(pendientes)
    _RUTA_PENDIENTES.write_text(
        json.dumps(existentes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    consola.print(
        f"  [yellow]{len(pendientes)} movimiento(s) guardado(s) en "
        f"pendientes.json[/yellow]  ({_RUTA_PENDIENTES})"
    )


@click.group("reglas")
def cmd_reglas():
    """Gestiona las reglas de categorización automática."""


def _tabla_reglas(reglas: list, indices_originales: list[int] | None = None) -> "Table":
    """Construye una tabla rich con las reglas dadas.

    Si se pasa `indices_originales`, la primera columna muestra el índice
    original en la lista completa (útil en modo filtrado).
    """
    titulo = f"Reglas de categorización ({len(reglas)})"
    tabla = Table(title=titulo, show_lines=False, highlight=True)
    tabla.add_column("#", style="dim", justify="right", no_wrap=True)
    tabla.add_column("Patrón", style="cyan", no_wrap=True)
    tabla.add_column("Tipo", style="dim")
    tabla.add_column("Categoría 1")
    tabla.add_column("Categoría 2")
    tabla.add_column("Categoría 3", style="dim")
    tabla.add_column("Proveedor")
    tabla.add_column("Tipo gasto", style="dim")

    for pos, r in enumerate(reglas):
        num = str(indices_originales[pos] + 1) if indices_originales else str(pos + 1)
        c = r["campos"]
        tabla.add_row(
            num,
            r["patron"],
            r["tipo"],
            c.get("categoria1", ""),
            c.get("categoria2", ""),
            c.get("categoria3", ""),
            c.get("proveedor", ""),
            c.get("tipo_gasto", ""),
        )
    return tabla


@cmd_reglas.command("listar")
@click.option("-i", "--interactivo", is_flag=True, help="Modo interactivo: navega y borra reglas.")
@click.option("-f", "--filtro", default="", metavar="TEXTO", help="Filtrar por patrón o categoría.")
def reglas_listar(interactivo, filtro):
    """Lista las reglas de categorización en una tabla.

    En modo interactivo (-i) puedes navegar por las reglas y borrar
    las que ya no sean útiles. Escribe el número de una regla para
    marcarla/desmarcarla, 'd' para borrar las marcadas, 'f' para
    cambiar el filtro, o 'q' para salir.
    """
    gestor = _crear_gestor_reglas()

    if not interactivo:
        # --- Modo simple: mostrar tabla y salir ---
        todas = gestor.listar()
        if not todas:
            consola.print("[yellow]No hay reglas definidas.[/yellow]")
            return
        if filtro:
            filtro_l = filtro.lower()
            todas = [r for r in todas if filtro_l in r["patron"].lower()
                     or filtro_l in r["campos"].get("categoria1", "").lower()
                     or filtro_l in r["campos"].get("proveedor", "").lower()]
        consola.print(_tabla_reglas(todas))
        return

    # --- Modo interactivo ---
    marcadas: set[int] = set()  # índices originales marcados para borrar
    filtro_activo = filtro.lower()

    while True:
        todas = gestor.listar()
        if not todas:
            consola.print("[yellow]No quedan reglas.[/yellow]")
            break

        # Aplicar filtro
        if filtro_activo:
            pares = [
                (i, r) for i, r in enumerate(todas)
                if filtro_activo in r["patron"].lower()
                or filtro_activo in r["campos"].get("categoria1", "").lower()
                or filtro_activo in r["campos"].get("proveedor", "").lower()
            ]
        else:
            pares = list(enumerate(todas))

        indices_vis = [i for i, _ in pares]
        reglas_vis = [r for _, r in pares]

        # Redibujar pantalla
        consola.clear()
        if filtro_activo:
            consola.print(f"[dim]Filtro activo:[/dim] [cyan]{filtro_activo}[/cyan]  "
                          f"[dim]({len(reglas_vis)} de {len(todas)} reglas)[/dim]\n")

        # Marcar visualmente las seleccionadas
        reglas_display = []
        for i, r in zip(indices_vis, reglas_vis):
            if i in marcadas:
                # Clonar con el patrón decorado para indicar selección
                r_marcada = dict(r)
                r_marcada["patron"] = f"[bold red]✗ {r['patron']}[/bold red]"
                reglas_display.append(r_marcada)
            else:
                reglas_display.append(r)

        consola.print(_tabla_reglas(reglas_display, indices_vis))

        if marcadas:
            consola.print(
                f"\n[bold red]{len(marcadas)} regla(s) marcada(s) para borrar.[/bold red]"
            )

        consola.print(
            "\n[dim]Nº[/dim] marcar/desmarcar · "
            "[dim]d[/dim] borrar marcadas · "
            "[dim]f <texto>[/dim] filtrar · "
            "[dim]f[/dim] quitar filtro · "
            "[dim]q[/dim] salir"
        )

        try:
            entrada = consola.input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            consola.print("\n[dim]Saliendo.[/dim]")
            break

        if not entrada:
            continue

        # Salir
        if entrada.lower() == "q":
            break

        # Borrar marcadas
        if entrada.lower() == "d":
            if not marcadas:
                consola.print("[yellow]No hay reglas marcadas.[/yellow]")
                continue
            patrones = [todas[i]["patron"] for i in sorted(marcadas)]
            consola.print("\nReglas a borrar:")
            for p in patrones:
                consola.print(f"  [red]✗[/red] {p}")
            if click.confirm("\n¿Confirmar borrado?", default=False):
                for patron in patrones:
                    gestor.eliminar(patron)
                eliminadas = len(marcadas)
                marcadas.clear()
                consola.print(f"[green]{eliminadas} regla(s) eliminada(s).[/green]")
            else:
                consola.print("[dim]Cancelado.[/dim]")
            continue

        # Cambiar filtro: "f texto" o "f" (quitar filtro)
        if entrada.lower().startswith("f"):
            resto = entrada[1:].strip()
            filtro_activo = resto.lower()
            marcadas.clear()  # limpiar selección al cambiar filtro
            continue

        # Marcar/desmarcar por número
        try:
            num = int(entrada)
        except ValueError:
            consola.print("[red]Entrada no reconocida.[/red]")
            continue

        if num < 1 or num > len(todas):
            consola.print(f"[red]Número fuera de rango (1-{len(todas)}).[/red]")
            continue

        idx_original = num - 1
        if idx_original in marcadas:
            marcadas.discard(idx_original)
        else:
            marcadas.add(idx_original)


@cmd_reglas.command("debug")
@click.argument("archivo", type=click.Path(exists=True))
@click.option("--banco", help="Forzar banco (n26, openbank, kutxabank, bbva, ing, abanca).")
@click.option("--cuenta", help="Forzar cuenta destino.")
def reglas_debug(archivo, banco, cuenta):
    """Muestra qué regla categoriza cada movimiento de un extracto.

    Útil para auditar las reglas actuales: indica si cada movimiento
    fue categorizado por una regla, por similitud con el historial o si
    quedó sin match.

    Para los movimientos sin match muestra el concepto y la ruta al
    fichero de reglas, y permite recargar y volver a evaluar sin
    reiniciar el programa (tecla 'r' en el prompt).

    Tras crear una regla en el editor externo pulsa 'r' para confirmar
    que el concepto ahora hace match.
    """
    from rich import box
    from rich.table import Table

    from presupuesto.categorizar import Categorizador
    from presupuesto.config import cargar_config
    from presupuesto.maestro import DatosMaestros

    ruta_xlsx = _obtener_ruta_xlsx()
    if ruta_xlsx is None:
        return

    try:
        datos_maestros = DatosMaestros(ruta_xlsx)
    except Exception as e:
        consola.print(f"[red]Error al leer el Maestro:[/red] {e}")
        return

    gestor = _crear_gestor_reglas()
    config = cargar_config()

    parser_banco = _obtener_parser_y_banco(archivo, banco)
    if parser_banco is None:
        return
    parser_obj, banco_key = parser_banco

    try:
        movimientos_crudos = parser_obj.parsear(archivo)
    except Exception as e:
        consola.print(f"[red]Error al parsear:[/red] {e}")
        return

    if not movimientos_crudos:
        consola.print("[yellow]No se encontraron movimientos en el archivo.[/yellow]")
        return

    cuenta_archivo = _determinar_cuenta(cuenta, banco_key, config, datos_maestros)
    if not cuenta_archivo:
        return

    categorizador = Categorizador(datos_maestros, gestor)
    categorizador.cargar_historial(ruta_xlsx)

    # --- Categorizar todos los movimientos ---
    resultados: list[tuple] = []
    for mov in movimientos_crudos:
        cat = categorizador.categorizar(mov, cuenta_archivo)
        resultados.append((mov, cat))

    # --- Tabla de resultados ---
    _COLOR = {"alta": "green", "media": "yellow", "baja": "yellow", "ninguna": "red"}

    tabla = Table(
        title=f"Debug de reglas — {Path(archivo).name}  ({cuenta_archivo})",
        box=box.SIMPLE_HEAD,
        show_lines=False,
        padding=(0, 1),
    )
    tabla.add_column("Concepto", no_wrap=False, max_width=48)
    tabla.add_column("Importe", justify="right", no_wrap=True)
    tabla.add_column("Fuente", no_wrap=True)
    tabla.add_column("Cat1", no_wrap=True)
    tabla.add_column("Cat2", no_wrap=True)
    tabla.add_column("Conf.", no_wrap=True)

    for mov, cat in resultados:
        c = _COLOR.get(cat.confianza, "")
        tabla.add_row(
            mov.concepto[:48],
            f"{mov.importe:+.2f}€",
            f"[{c}]{cat.fuente}[/{c}]",
            cat.categoria1 or "[dim]—[/dim]",
            cat.categoria2 or "[dim]—[/dim]",
            f"[{c}]{cat.confianza}[/{c}]",
        )

    consola.print()
    consola.print(tabla)

    n_regla   = sum(1 for _, c in resultados if c.confianza == "alta")
    n_hist    = sum(1 for _, c in resultados if c.confianza in ("media", "baja"))
    n_ninguna = sum(1 for _, c in resultados if c.confianza == "ninguna")
    consola.print(
        f"  [green]{n_regla} con regla[/green]  "
        f"[yellow]{n_hist} con historial[/yellow]  "
        f"[red]{n_ninguna} sin match[/red]"
    )

    # --- Flujo interactivo para todos los movimientos ---
    consola.print(
        f"\n[bold]Revisión interactiva ({len(resultados)} movimientos):[/bold]  "
        f"[dim]r[/dim]=recargar y re-evaluar  "
        f"[dim]s[/dim]=siguiente  "
        f"[dim]q[/dim]=salir\n"
    )
    consola.print(f"  Reglas en: [bold]{gestor.ruta}[/bold]\n")

    from presupuesto.reglas import describir_match as _describir_match

    def _fmt_coincide(info: dict) -> str:
        coincide = info["coincide"]
        if isinstance(coincide, list):
            return "  +  ".join(f'[bold]"{x}"[/bold]' for x in coincide)
        return f'[bold]"{coincide}"[/bold]'

    def _mostrar_todas_matches(concepto: str, cuenta: str) -> None:
        """Muestra la regla que aplica y las demás que también coinciden."""
        todas = gestor.buscar_todas_con_match(concepto, cuenta=cuenta)
        if not todas:
            consola.print("    [red]Sin match.[/red]")
            return
        for i, regla in enumerate(todas):
            info = _describir_match(regla, concepto)
            if info is None:
                continue
            campos = regla["campos"]
            if i == 0:
                consola.print(
                    f"    [green]▶ aplica:[/green]  "
                    f"[cyan]{regla['patron']}[/cyan]  [dim]({regla['tipo']})[/dim]"
                    + (f"  [dim][cuenta: {regla['cuenta']}][/dim]" if regla.get("cuenta") else "")
                )
                consola.print(f"      [dim]busca:[/dim]    {info['busca']}")
                consola.print(f"      [dim]encontró:[/dim] {_fmt_coincide(info)}")
                consola.print(
                    f"      [dim]resultado:[/dim] [green]"
                    f"{campos.get('categoria1','')} / {campos.get('categoria2','')}"
                    f" · {campos.get('tipo_gasto','')}[/green]"
                )
            else:
                consola.print(
                    f"\n    [yellow bold]⚠ también coincide #{i}:[/yellow bold]  "
                    f"[yellow]{regla['patron']}[/yellow]  [dim]({regla['tipo']})[/dim]"
                    + (f"  [dim][cuenta: {regla['cuenta']}][/dim]" if regla.get("cuenta") else "")
                )
                consola.print(f"      [dim]busca:[/dim]    {info['busca']}")
                consola.print(f"      [dim]encontró:[/dim] {_fmt_coincide(info)}")
                consola.print(
                    f"      [dim]resultado:[/dim] [yellow]"
                    f"{campos.get('categoria1','')} / {campos.get('categoria2','')}"
                    f" · {campos.get('tipo_gasto','')}[/yellow]"
                )

    def _mostrar_entrada(idx: int) -> None:
        mov, cat = resultados[idx]
        consola.rule(f"[dim]{idx + 1}/{len(resultados)}[/dim]")
        c = _COLOR.get(cat.confianza, "")
        bullet = {"alta": "[green]●[/green]", "media": "[yellow]●[/yellow]",
                  "baja": "[yellow]●[/yellow]", "ninguna": "[red]●[/red]"}.get(cat.confianza, "●")
        consola.print(
            f"  {bullet} [bold]{mov.concepto}[/bold]"
            f"  [dim]{mov.importe:+.2f}€[/dim]"
        )
        if mov.concepto_original and mov.concepto_original != mov.concepto:
            consola.print(f"    [dim]original: {mov.concepto_original}[/dim]")
        if cat.confianza == "alta":
            _mostrar_todas_matches(mov.concepto, cuenta_archivo)
        elif cat.confianza in ("media", "baja"):
            consola.print(f"    [{c}]{cat.fuente}[/{c}]  → {cat.categoria1} / {cat.categoria2}")
        else:
            consola.print("    [red]sin match[/red]")
        consola.print(
            "  [dim]s[/dim] siguiente  "
            "[dim]v[/dim] volver  "
            "[dim]r[/dim] recargar  "
            "[dim]q[/dim] salir"
        )

    idx = 0
    while idx < len(resultados):
        _mostrar_entrada(idx)
        try:
            accion = click.getchar()
        except (EOFError, KeyboardInterrupt):
            consola.print("\n[dim]Saliendo.[/dim]")
            return

        if accion in ("q", "\x03"):   # q o Ctrl-C
            return
        if accion == "s":
            idx += 1
        elif accion == "v":
            if idx > 0:
                idx -= 1
            else:
                consola.print("  [dim]Ya estás en el primero.[/dim]")
        elif accion == "r":
            n = gestor.recargar()
            consola.print(f"  [dim]Reglas recargadas: {n} reglas.[/dim]")
            # re-evaluar este movimiento con las reglas nuevas
            mov, cat = resultados[idx]
            from presupuesto.categorizar import Categorizador
            cat2 = Categorizador(categorizador._maestros, gestor)
            resultados[idx] = (mov, cat2.categorizar(mov, cuenta_archivo))
            # no avanzar idx → volvemos a mostrar la entrada actualizada

    consola.print()


@cmd_reglas.command("exportar")
@click.argument("archivo", type=click.Path())
def reglas_exportar(archivo):
    """Exporta las reglas actuales a un fichero JSON."""
    gestor = _crear_gestor_reglas()
    gestor.exportar(archivo)
    consola.print(f"[green]Reglas exportadas a:[/green] {archivo} ({gestor.total()} reglas)")


@cmd_reglas.command("importar")
@click.argument("archivo", type=click.Path(exists=True))
@click.option("--reemplazar", is_flag=True, help="Reemplazar todas las reglas existentes.")
def reglas_importar(archivo, reemplazar):
    """Importa reglas desde un fichero JSON (fusiona por defecto)."""
    gestor = _crear_gestor_reglas()
    if reemplazar:
        if not click.confirm(f"¿Reemplazar las {gestor.total()} reglas actuales con las de '{archivo}'?"):
            return
        total = gestor.importar_reemplazar(archivo)
        consola.print(f"[green]Reglas reemplazadas:[/green] {total} reglas cargadas.")
    else:
        añadidas = gestor.importar_fusionar(archivo)
        consola.print(f"[green]Reglas fusionadas:[/green] {añadidas} nuevas reglas añadidas.")


@cmd_reglas.command("revisar")
def reglas_revisar():
    """Revisa los conceptos sin regla detectados en el último --dry-run.

    Para cada concepto muestra la sugerencia de categorización y permite
    crear una regla que se añade a reglas.json. Los conceptos procesados
    se eliminan del fichero.
    """
    from presupuesto.interactivo import _sugerir_patron  # noqa: PLC2701

    if not _RUTA_SIN_REGLA.exists():
        consola.print("[yellow]No hay conceptos sin regla pendientes de revisar.[/yellow]")
        consola.print("[dim]Ejecuta primero: presupuesto importar ... --dry-run[/dim]")
        return

    try:
        entradas: list[dict] = json.loads(_RUTA_SIN_REGLA.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        consola.print(f"[red]Error al leer sin_regla.json:[/red] {e}")
        return

    if not entradas:
        consola.print("[yellow]No hay conceptos pendientes.[/yellow]")
        return

    gestor = _crear_gestor_reglas()
    pendientes = list(entradas)
    procesadas: list[dict] = []

    consola.print(
        f"\n[bold]{len(pendientes)} concepto(s) sin regla para revisar.[/bold]  "
        "[dim]Enter[/dim] crear regla · "
        "[dim]s[/dim] saltar · "
        "[dim]d[/dim] descartar · "
        "[dim]q[/dim] salir\n"
    )

    for entrada in pendientes:
        concepto = entrada.get("concepto_original", "")
        sugerencia = entrada.get("sugerencia", {})
        confianza = entrada.get("confianza", "ninguna")
        importe = entrada.get("importe", 0.0)
        mes = entrada.get("mes", "")
        año = entrada.get("año", "")

        # Mostrar el concepto
        from rich.panel import Panel
        from rich.table import Table as RTable
        grid = RTable.grid(padding=(0, 2))
        grid.add_column(style="dim", no_wrap=True)
        grid.add_column()
        grid.add_row("Concepto", concepto)
        color_imp = "red" if importe < 0 else "green"
        grid.add_row("Importe",  f"[{color_imp}]{importe:+.2f}[/{color_imp}]")
        grid.add_row("Período",  f"{mes} {año}")
        grid.add_row("Confianza", confianza)
        if any(sugerencia.values()):
            grid.add_row("Sugerencia", (
                f"{sugerencia.get('categoria1','')} > "
                f"{sugerencia.get('categoria2','')} | "
                f"{sugerencia.get('tipo_gasto','')}"
            ))
        consola.rule()
        consola.print(Panel(grid, border_style="blue", padding=(0, 1)))

        try:
            resp = consola.input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            consola.print("\n[dim]Saliendo.[/dim]")
            break

        if resp == "q":
            break
        if resp == "d":
            # Descartar: no crear regla, eliminar del fichero
            procesadas.append(entrada)
            consola.print("  [dim]Descartado.[/dim]")
            continue
        if resp == "s":
            consola.print("  [dim]Saltado (permanece en la lista).[/dim]")
            continue

        # Crear regla (Enter o cualquier otra cosa)
        patron_sugerido = _sugerir_patron(concepto)
        consola.print(
            f"\n  Patrón sugerido: [cyan]{patron_sugerido}[/cyan]  "
            "[dim](Enter para aceptar o escribe otro)[/dim]"
        )
        try:
            patron_entrada = consola.input("  Patrón: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        patron = patron_entrada if patron_entrada else patron_sugerido

        tipo = click.prompt(
            "  Tipo de match",
            type=click.Choice(["contains", "startswith", "regex"]),
            default="contains",
            show_choices=True,
        )

        # Mostrar y confirmar campos de la sugerencia
        consola.print("\n  [dim]Campos (Enter para aceptar, escribe para cambiar):[/dim]")
        campos_finales: dict[str, str] = {}
        for campo in ("categoria1", "categoria2", "categoria3", "entidad", "proveedor", "tipo_gasto"):
            valor_actual = sugerencia.get(campo, "")
            try:
                entrada_campo = consola.input(
                    f"  {campo} [{valor_actual or '—'}]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                campos_finales[campo] = valor_actual
                continue
            campos_finales[campo] = entrada_campo if entrada_campo else valor_actual

        gestor.añadir(patron=patron, tipo=tipo, campos=campos_finales)
        consola.print(f"  [green]✓ Regla '{patron}' guardada.[/green]")
        procesadas.append(entrada)

    # Eliminar del fichero las entradas procesadas (creadas o descartadas)
    if procesadas:
        conceptos_procesados = {e.get("concepto_original", "") for e in procesadas}
        restantes = [e for e in entradas if e.get("concepto_original", "") not in conceptos_procesados]
        _RUTA_SIN_REGLA.write_text(
            json.dumps(restantes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        consola.print(
            f"\n[green]{len(procesadas)} entrada(s) procesadas.[/green]  "
            f"[dim]{len(restantes)} restante(s).[/dim]"
        )


@cmd_reglas.command("resetear")
def reglas_resetear():
    """Restaura las reglas iniciales del paquete (pide confirmación)."""
    gestor = _crear_gestor_reglas()
    if not click.confirm(
        f"¿Restaurar reglas iniciales? Se perderán las {gestor.total()} reglas actuales."
    ):
        return
    total = gestor.resetear()
    consola.print(f"[green]Reglas restauradas:[/green] {total} reglas iniciales cargadas.")


@click.command("config")
@click.option("--set-archivo", "archivo", default=None, metavar="RUTA",
              help="Establece la ruta del archivo presupuesto.xlsx.")
def cmd_config(archivo):
    """Muestra la configuración actual y permite ajustarla."""
    from presupuesto.config import (
        RUTA_CONFIG,
        cargar_config,
        establecer_archivo_presupuesto,
        obtener_archivo_presupuesto,
    )

    # Establecer archivo si se pasó la opción
    if archivo:
        establecer_archivo_presupuesto(archivo)
        consola.print(f"[green]archivo_presupuesto actualizado:[/green] {archivo}")

    config = cargar_config()
    ruta_xlsx = obtener_archivo_presupuesto(config)

    consola.print(f"\n[bold]Configuración[/bold] ([dim]{RUTA_CONFIG}[/dim])\n")

    # Tabla principal
    tabla = Table(show_header=False, box=None, padding=(0, 2))
    tabla.add_column(style="cyan")
    tabla.add_column()

    estado_xlsx = (
        f"[green]{ruta_xlsx}[/green]"
        if ruta_xlsx and ruta_xlsx.exists()
        else (
            f"[red]{ruta_xlsx} (no encontrado)[/red]"
            if ruta_xlsx
            else "[red]No configurado[/red]"
        )
    )
    tabla.add_row("archivo_presupuesto", estado_xlsx)
    tabla.add_row("archivo_reglas", config.get("archivo_reglas", ""))
    consola.print(tabla)

    # Cuentas por defecto
    consola.print("\n[bold]cuentas_defecto[/bold]")
    tabla_cuentas = Table(show_header=False, box=None, padding=(0, 2))
    tabla_cuentas.add_column(style="cyan")
    tabla_cuentas.add_column()
    for banco, cuenta in config.get("cuentas_defecto", {}).items():
        tabla_cuentas.add_row(banco, cuenta or "[dim](sin configurar)[/dim]")
    consola.print(tabla_cuentas)

    # Aviso si falta el archivo principal
    if not ruta_xlsx:
        consola.print(
            "\n[yellow]Tip:[/yellow] Configura el archivo con "
            "[bold]presupuesto config --set-archivo /ruta/presupuesto.xlsx[/bold]"
        )


@click.group("maestro")
def cmd_maestro():
    """Consulta los valores válidos del Maestro en presupuesto.xlsx.

    Útil para saber qué categorías, proveedores y cuentas puedes usar
    al categorizar movimientos o al escribir reglas.
    """


# ---------------------------------------------------------------------------
# Helpers de display para el Maestro
# ---------------------------------------------------------------------------

def _tabla_lista(titulo: str, valores: list[str], estilo: str = "") -> Table:
    """Tabla de una columna con una lista de valores."""
    t = Table(title=titulo, show_header=False, box=None, padding=(0, 1))
    t.add_column(style=estilo)
    for v in valores:
        t.add_row(v)
    return t


def _tabla_tres_columnas(
    titulo: str,
    col1: list[str], nombre1: str,
    col2: list[str], nombre2: str,
    col3: list[str], nombre3: str,
) -> Table:
    """Tabla de tres columnas para mostrar las categorías 1, 2 y 3 en paralelo."""
    alto = max(len(col1), len(col2), len(col3))
    t = Table(title=titulo, show_header=True, show_lines=False, padding=(0, 2))
    t.add_column(nombre1, style="cyan",  no_wrap=True)
    t.add_column(nombre2, style="green", no_wrap=True)
    t.add_column(nombre3, style="dim",   no_wrap=True)
    for i in range(alto):
        t.add_row(
            col1[i] if i < len(col1) else "",
            col2[i] if i < len(col2) else "",
            col3[i] if i < len(col3) else "",
        )
    return t


def _tabla_cuentas(claves: dict) -> Table:
    """Tabla Cuenta | Banco | Tipo de cuenta."""
    t = Table(title=f"Cuentas ({len(claves)})", show_lines=False, padding=(0, 2))
    t.add_column("Cuenta",          style="cyan",  no_wrap=True)
    t.add_column("Banco",           style="green", no_wrap=True)
    t.add_column("Tipo de cuenta",  style="dim",   no_wrap=True)
    for cuenta, (banco, tipo) in claves.items():
        t.add_row(cuenta, banco or "", tipo or "")
    return t


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------

@cmd_maestro.command("categorias")
def maestro_categorias():
    """Muestra las categorías 1, 2 y 3 válidas según el Maestro.

    Las tres listas son independientes: usar cualquier combinación es válido
    siempre que cada valor exista en su columna.
    """
    m = _cargar_datos_maestros()
    if m is None:
        return
    consola.print()
    consola.print(_tabla_tres_columnas(
        "Categorías",
        m.categorias1, "Categoría 1",
        m.categorias2, "Categoría 2",
        m.categorias3, "Categoría 3",
    ))
    consola.print(
        f"\n[dim]{len(m.categorias1)} cat1 · "
        f"{len(m.categorias2)} cat2 · "
        f"{len(m.categorias3)} cat3[/dim]"
    )


@cmd_maestro.command("proveedores")
@click.option("-f", "--filtro", default="", metavar="TEXTO",
              help="Filtrar proveedores que contengan este texto.")
def maestro_proveedores(filtro):
    """Muestra la lista de proveedores válidos según el Maestro.

    Usa --filtro para buscar entre los proveedores disponibles.
    """
    m = _cargar_datos_maestros()
    if m is None:
        return

    proveedores = m.proveedores
    if filtro:
        proveedores = [p for p in proveedores if filtro.lower() in p.lower()]
        if not proveedores:
            consola.print(
                f"[yellow]Sin proveedores que contengan '[bold]{filtro}[/bold]'.[/yellow]"
            )
            return

    mitad = (len(proveedores) + 1) // 2
    t = Table(
        title=f"Proveedores ({len(proveedores)})",
        show_header=False, box=None, padding=(0, 2),
    )
    t.add_column(style="cyan", no_wrap=True)
    t.add_column(style="cyan", no_wrap=True)
    col_izq, col_der = proveedores[:mitad], proveedores[mitad:]
    for i in range(mitad):
        t.add_row(col_izq[i], col_der[i] if i < len(col_der) else "")
    consola.print()
    if filtro:
        consola.print(f"[dim]Filtro:[/dim] [cyan]{filtro}[/cyan]")
    consola.print(t)


@cmd_maestro.command("cuentas")
def maestro_cuentas():
    """Muestra las cuentas configuradas con su banco y tipo de cuenta.

    Esta tabla proviene de la hoja 'Claves' del presupuesto.xlsx y determina
    qué banco y tipo de cuenta se asignan automáticamente a cada movimiento.
    """
    m = _cargar_datos_maestros()
    if m is None:
        return
    claves = m.claves_cuentas()
    if not claves:
        consola.print("[yellow]No hay cuentas definidas en la hoja 'Claves'.[/yellow]")
        return
    consola.print()
    consola.print(_tabla_cuentas(claves))


@cmd_maestro.command("todo")
def maestro_todo():
    """Muestra todos los valores válidos del Maestro de una sola vez.

    Incluye: categorías, tipos de gasto, entidades, proveedores y cuentas.
    """
    m = _cargar_datos_maestros()
    if m is None:
        return

    consola.print()

    # Categorías
    consola.print(_tabla_tres_columnas(
        "Categorías",
        m.categorias1, "Categoría 1",
        m.categorias2, "Categoría 2",
        m.categorias3, "Categoría 3",
    ))

    # Tipos de gasto + Entidades en paralelo
    consola.print()
    t_lateral = Table(show_header=False, box=None, padding=(0, 4))
    t_lateral.add_column()
    t_lateral.add_column()

    tg = Table(title=f"Tipos de gasto ({len(m.tipos_gasto)})",
               show_header=False, box=None, padding=(0, 1))
    tg.add_column(style="yellow", no_wrap=True)
    for v in m.tipos_gasto:
        tg.add_row(v)

    ent = Table(title=f"Entidades ({len(m.entidades)})",
                show_header=False, box=None, padding=(0, 1))
    ent.add_column(style="magenta", no_wrap=True)
    for v in m.entidades:
        ent.add_row(v)

    t_lateral.add_row(tg, ent)
    consola.print(t_lateral)

    # Proveedores
    consola.print()
    proveedores = m.proveedores
    mitad = (len(proveedores) + 1) // 2
    col_izq, col_der = proveedores[:mitad], proveedores[mitad:]
    t_prov = Table(
        title=f"Proveedores ({len(proveedores)})",
        show_header=False, box=None, padding=(0, 2),
    )
    t_prov.add_column(style="cyan", no_wrap=True)
    t_prov.add_column(style="cyan", no_wrap=True)
    for i in range(mitad):
        t_prov.add_row(col_izq[i], col_der[i] if i < len(col_der) else "")
    consola.print(t_prov)

    # Cuentas
    consola.print()
    consola.print(_tabla_cuentas(m.claves_cuentas()))


@click.command("recuperar")
def cmd_recuperar():
    """Reintenta escribir en xlsx los movimientos guardados tras un fallo anterior."""
    resultado = _cargar_recovery()
    if resultado is None:
        consola.print("[dim]No hay movimientos pendientes de recuperación.[/dim]")
        return

    agrupados, ruta_xlsx = resultado
    from datetime import datetime
    datos_raw = json.loads(_RUTA_RECOVERY.read_text(encoding="utf-8"))
    ts = datos_raw.get("timestamp", "desconocido")
    consola.print(
        f"[yellow]Recuperación:[/yellow] {len(agrupados)} movimiento(s) del {ts}\n"
        f"  → [bold]{ruta_xlsx}[/bold]"
    )
    if not click.confirm("\n¿Intentar escribir ahora?", default=True):
        consola.print("[dim]Cancelado. El fichero recovery.json se mantiene.[/dim]")
        return

    try:
        from presupuesto.escritor import EscritorDatos
        escritor = EscritorDatos(ruta_xlsx)
        n_escritos = escritor.escribir(agrupados)
    except Exception as e:
        consola.print(f"[red]Error al escribir en el xlsx:[/red] {e}")
        consola.print("[dim]El fichero recovery.json se mantiene para el próximo intento.[/dim]")
        return

    _RUTA_RECOVERY.unlink(missing_ok=True)
    consola.print(f"\n[green]✓ {n_escritos} fila(s) escritas en presupuesto.xlsx.[/green]")


cli.add_command(cmd_importar)
cli.add_command(cmd_recuperar)
cli.add_command(cmd_reglas)
cli.add_command(cmd_config)
cli.add_command(cmd_maestro)

from presupuesto.cmd_actualizar import cmd_actualizar  # noqa: E402
cli.add_command(cmd_actualizar)

from presupuesto.cmd_cerrar import cmd_cerrar  # noqa: E402
cli.add_command(cmd_cerrar)

from presupuesto.cmd_saldos import cmd_saldos  # noqa: E402
cli.add_command(cmd_saldos)

from presupuesto.cmd_añadir import cmd_añadir  # noqa: E402
cli.add_command(cmd_añadir)

from presupuesto.cmd_vista import cmd_vista  # noqa: E402
cli.add_command(cmd_vista)

from presupuesto.cmd_estado import cmd_estado  # noqa: E402
cli.add_command(cmd_estado)

