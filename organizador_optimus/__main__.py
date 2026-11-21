"""Punto de entrada.

    OrganizadorOptimus.exe              abre la ventana
    OrganizadorOptimus.exe --simular    muestra qué haría, sin mover nada
    OrganizadorOptimus.exe --auto       ordena sin preguntar (lo usa la tarea programada)
    OrganizadorOptimus.exe --deshacer   deshace la última ejecución
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import APP_NAME, __version__, config, motor
from .carpetas import datos_app
from .servicio import armar_plan


def _consola(texto: str) -> None:
    try:
        print(texto)
    except (UnicodeEncodeError, AttributeError, OSError):
        pass   # en el .exe sin consola no hay stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="OrganizadorOptimus", description=APP_NAME)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--simular", action="store_true", help="mostrar el plan sin mover nada")
    g.add_argument("--auto", action="store_true", help="ordenar sin preguntar")
    g.add_argument("--deshacer", action="store_true", help="deshacer la última ejecución")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    if not (args.simular or args.auto or args.deshacer):
        from .gui import iniciar
        iniciar()
        return 0

    logging.basicConfig(filename=datos_app() / "registro.log", level=logging.INFO,
                        format="%(asctime)s %(message)s", encoding="utf-8")
    cfg = config.cargar()

    if args.deshacer:
        hs = motor.historiales()
        if not hs:
            _consola("No hay nada que deshacer.")
            return 0
        r = motor.deshacer(hs[0])
        _consola(f"Devueltos {r.movidos} archivos. Errores: {len(r.errores)}")
        logging.info("deshacer %s: %d devueltos, %d errores", hs[0].name, r.movidos, len(r.errores))
        return 0

    plan = armar_plan(cfg)
    if args.simular:
        for m in plan.movimientos:
            marca = "" if m.sugerido else "  [revisar]"
            _consola(f"[{m.accion}] {m.origen}\n    -> {m.destino}   ({m.motivo}){marca}")
        _consola(f"\n{len(plan.movimientos)} movimientos, {len(plan.omitidos)} omitidos.")
        return 0

    # Sin nadie mirando solo se hace lo seguro: nada que la app marque como "revisar antes"
    elegidos = [m for m in plan.movimientos
                if m.sugerido and (not m.es_carpeta or cfg.get("carpetas_en_auto"))]
    r = motor.ejecutar(elegidos)
    logging.info("auto: %d movidos, %d errores", r.movidos, len(r.errores))
    for origen, err in r.errores:
        logging.info("  error %s: %s", origen, err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
