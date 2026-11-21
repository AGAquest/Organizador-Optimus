"""Ordenado automático con el Programador de tareas de Windows (schtasks)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

NOMBRE_TAREA = "OrganizadorOptimus"


def _comando_app() -> str:
    if getattr(sys, "frozen", False):          # ejecutable .exe hecho con PyInstaller
        return f'"{sys.executable}" --auto'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    py = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{py}" -m organizador_optimus --auto'


def programar(frecuencia: str = "DAILY", hora: str = "13:00") -> tuple[bool, str]:
    """frecuencia: DAILY, WEEKLY u ONLOGON."""
    if sys.platform != "win32":
        return False, "La programación automática solo funciona en Windows."
    args = ["schtasks", "/Create", "/F", "/TN", NOMBRE_TAREA, "/TR", _comando_app(), "/SC", frecuencia]
    if frecuencia in ("DAILY", "WEEKLY"):
        args += ["/ST", hora]
    r = subprocess.run(args, capture_output=True, text=True, creationflags=0x08000000)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


def quitar() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Solo en Windows."
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", NOMBRE_TAREA],
                       capture_output=True, text=True, creationflags=0x08000000)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


def esta_programado() -> bool:
    if sys.platform != "win32":
        return False
    r = subprocess.run(["schtasks", "/Query", "/TN", NOMBRE_TAREA],
                       capture_output=True, text=True, creationflags=0x08000000)
    return r.returncode == 0
