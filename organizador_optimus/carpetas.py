"""Ubicación real de las carpetas de Windows (Escritorio, Documentos, Descargas...).

En muchos PCs el Escritorio y Documentos están redirigidos a OneDrive
(p. ej. C:\\Users\\x\\OneDrive\\Escritorio), así que nunca se asume
"C:\\Users\\x\\Desktop": se pregunta a Windows con SHGetKnownFolderPath.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# GUIDs de las "Known Folders" de Windows
_KNOWN = {
    "escritorio": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documentos": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "descargas": "{374DE290-123F-4565-9164-39C4925E467B}",
    "imagenes": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "musica": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
}

# Nombres alternativos para buscar en perfiles de otras cuentas
_ALTERNATIVAS = {
    "escritorio": ["OneDrive/Escritorio", "OneDrive/Desktop", "Desktop", "Escritorio"],
    "documentos": ["OneDrive/Documentos", "OneDrive/Documents", "Documents", "Documentos"],
    "descargas": ["Downloads", "Descargas"],
    "imagenes": ["OneDrive/Imágenes", "OneDrive/Pictures", "Pictures", "Imágenes"],
    "videos": ["Videos", "Vídeos"],
    "musica": ["Music", "Música"],
}


def _known_folder(guid: str) -> Path | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    u = uuid.UUID(guid)
    g = GUID(u.fields[0], u.fields[1], u.fields[2],
             (wintypes.BYTE * 8).from_buffer_copy(u.bytes[8:]))
    ptr = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr)) != 0:
        return None
    try:
        return Path(ptr.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ptr)


@dataclass
class CarpetasUsuario:
    """Carpetas de una cuenta de Windows."""
    cuenta: str
    perfil: Path
    escritorio: Path | None
    documentos: Path
    descargas: Path | None
    imagenes: Path | None
    videos: Path | None
    musica: Path | None


def _buscar_en_perfil(perfil: Path, clave: str) -> Path | None:
    for rel in _ALTERNATIVAS[clave]:
        p = perfil / rel
        if p.is_dir():
            return p
    return None


def carpetas_actuales() -> CarpetasUsuario:
    """Carpetas de la cuenta que está usando la app."""
    perfil = Path.home()
    rutas = {}
    for clave, guid in _KNOWN.items():
        rutas[clave] = _known_folder(guid) or _buscar_en_perfil(perfil, clave)
    documentos = rutas["documentos"] or (perfil / "Documents")
    return CarpetasUsuario(
        cuenta=os.environ.get("USERNAME") or perfil.name,
        perfil=perfil,
        escritorio=rutas["escritorio"],
        documentos=documentos,
        descargas=rutas["descargas"],
        imagenes=rutas["imagenes"],
        videos=rutas["videos"],
        musica=rutas["musica"],
    )


_PERFILES_SISTEMA = {"public", "default", "default user", "all users", "defaultapppool", "wdagutilityaccount"}


def otras_cuentas() -> list[CarpetasUsuario]:
    """Otras cuentas de Windows del PC cuyas carpetas se pueden leer y escribir.

    Normalmente requiere ejecutar la app como administrador.
    """
    actual = Path.home().resolve()
    raiz = actual.parent
    cuentas = []
    try:
        perfiles = list(raiz.iterdir())
    except OSError:
        return cuentas
    for perfil in perfiles:
        try:
            if (not perfil.is_dir() or perfil.name.lower() in _PERFILES_SISTEMA
                    or perfil.resolve() == actual):
                continue
            documentos = _buscar_en_perfil(perfil, "documentos")
            if documentos is None or not os.access(documentos, os.W_OK):
                continue
            cuentas.append(CarpetasUsuario(
                cuenta=perfil.name,
                perfil=perfil,
                escritorio=_buscar_en_perfil(perfil, "escritorio"),
                documentos=documentos,
                descargas=_buscar_en_perfil(perfil, "descargas"),
                imagenes=_buscar_en_perfil(perfil, "imagenes"),
                videos=_buscar_en_perfil(perfil, "videos"),
                musica=_buscar_en_perfil(perfil, "musica"),
            ))
        except OSError:
            continue
    return cuentas


def datos_app() -> Path:
    """Carpeta donde la app guarda su configuración e historial."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "OrganizadorOptimus"
    p.mkdir(parents=True, exist_ok=True)
    return p
