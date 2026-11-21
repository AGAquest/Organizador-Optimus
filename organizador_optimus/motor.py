"""Ejecuta el plan, guarda un historial de cada ejecución y permite deshacer.

La app nunca borra archivos: solo los mueve, y cada movimiento queda anotado.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .carpetas import datos_app
from .planificador import Movimiento


def carpeta_historial() -> Path:
    p = datos_app() / "historial"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Resumen:
    movidos: int = 0
    errores: list[tuple[str, str]] = field(default_factory=list)
    archivo_historial: Path | None = None


def _mover(origen: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        raise FileExistsError(f"ya existe {destino}")
    shutil.move(str(origen), str(destino))


def ejecutar(movimientos: list[Movimiento], progreso: Callable[[str], None] | None = None,
             historial_dir: Path | None = None) -> Resumen:
    progreso = progreso or (lambda _m: None)
    historial_dir = historial_dir or carpeta_historial()
    marca = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archivo = historial_dir / f"{marca}.jsonl"
    resumen = Resumen(archivo_historial=archivo)
    with open(archivo, "a", encoding="utf-8") as log:
        for i, m in enumerate(movimientos, 1):
            progreso(f"[{i}/{len(movimientos)}] {m.origen.name}")
            try:
                if not m.origen.exists():
                    raise FileNotFoundError("el archivo ya no está")
                _mover(m.origen, m.destino)
            except PermissionError:
                resumen.errores.append((str(m.origen), "está abierto en otro programa"))
                continue
            except OSError as e:
                resumen.errores.append((str(m.origen), str(e)))
                continue
            resumen.movidos += 1
            log.write(json.dumps({
                "origen": str(m.origen), "destino": str(m.destino), "accion": m.accion,
                "categoria": m.categoria, "persona": m.persona, "cuenta": m.cuenta,
                "hora": time.time(),
            }, ensure_ascii=False) + "\n")
            log.flush()
    if resumen.movidos == 0:
        archivo.unlink(missing_ok=True)
        resumen.archivo_historial = None
    return resumen


def historiales(historial_dir: Path | None = None) -> list[Path]:
    """Ejecuciones anteriores que se pueden deshacer, de la más nueva a la más vieja."""
    historial_dir = historial_dir or carpeta_historial()
    return sorted(historial_dir.glob("*.jsonl"), reverse=True)


def deshacer(archivo: Path, progreso: Callable[[str], None] | None = None) -> Resumen:
    """Devuelve cada archivo de una ejecución a donde estaba."""
    progreso = progreso or (lambda _m: None)
    resumen = Resumen()
    registros = []
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            registros.append(json.loads(linea))
    for r in reversed(registros):
        origen, destino = Path(r["origen"]), Path(r["destino"])
        progreso(f"Devolviendo {destino.name}")
        try:
            if not destino.exists():
                raise FileNotFoundError("el archivo ya no está donde se dejó")
            _mover(destino, origen)
            resumen.movidos += 1
            _limpiar_vacias(destino.parent)
        except OSError as e:
            resumen.errores.append((str(destino), str(e)))
    archivo.rename(archivo.with_suffix(".deshecho"))
    return resumen


RAICES_APP = {"organizador optimus", "archivados"}


def _limpiar_vacias(carpeta: Path, niveles: int = 4) -> None:
    """Quita carpetas que quedaron vacías al deshacer, solo dentro de las carpetas de la app."""
    for _ in range(niveles):
        if carpeta.name.lower() in RAICES_APP:
            return
        if not any(p.name.lower() in RAICES_APP for p in carpeta.parents):
            return
        try:
            if any(carpeta.iterdir()):
                return
            carpeta.rmdir()
        except OSError:
            return
        carpeta = carpeta.parent
