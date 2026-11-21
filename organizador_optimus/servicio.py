"""Une todo: qué cuentas revisar, armar el plan y ejecutarlo."""
from __future__ import annotations

from typing import Callable

from .carpetas import CarpetasUsuario, carpetas_actuales, otras_cuentas
from .planificador import Plan, Planificador


def cuentas_a_revisar(cfg: dict) -> list[CarpetasUsuario]:
    cuentas = [carpetas_actuales()]
    if cfg.get("incluir_otras_cuentas"):
        cuentas += otras_cuentas()
    return cuentas


def armar_plan(cfg: dict, progreso: Callable[[str], None] | None = None) -> Plan:
    return Planificador(cfg, progreso).planificar(cuentas_a_revisar(cfg))
