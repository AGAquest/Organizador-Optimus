"""Mira dentro de una carpeta y decide qué es: estudios, fotos, proyecto de código, programa, SDK…"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

MAX_ARCHIVOS = 4000          # no recorrer carpetas gigantes completas
MAX_DOCS_LEIDOS = 6          # documentos que se leen para entender el tema

EXT_CODIGO = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".dart", ".cs", ".cpp", ".c", ".h",
              ".go", ".rs", ".php", ".rb", ".swift", ".html", ".css", ".scss", ".vue", ".ipynb",
              ".sql", ".sh", ".ps1", ".yaml", ".yml", ".toml", ".gradle", ".pyc"}
EXT_PROGRAMA = {".exe", ".msi", ".dll", ".sys", ".inf", ".cat", ".cab", ".bin", ".jar", ".iso",
                ".img", ".vhd", ".vmdk", ".apk"}
EXT_DOC = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls", ".xlsx", ".xlsm", ".xlsb",
           ".ods", ".csv", ".ppt", ".pptx", ".odp", ".epub", ".mobi"}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".tif", ".tiff", ".raw", ".svg"}
EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"}
EXT_MUSICA = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
EXT_COMPRIMIDO = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}

MARCAS_PROYECTO = {".git", "package.json", "pom.xml", "build.gradle", "cargo.toml", "node_modules",
                   ".venv", "venv", "requirements.txt", ".idea", ".vscode", "setup.py", "pyproject.toml",
                   "makefile", "cmakelists.txt", "go.mod", "pubspec.yaml", "docker-compose.yml",
                   "dockerfile", "manage.py", "composer.json", ".sln", "angular.json"}

# Herramientas instaladas (SDKs): moverlas rompe la variable PATH y los programas que las usan
NOMBRES_SDK = re.compile(r"^(flutter|android|android-sdk|sdk|jdk.*|jre.*|java|node(js)?|python\d*|go|"
                         r"gradle.*|apache-maven.*|maven|mingw.*|msys.*|cygwin.*|ffmpeg.*|platform-tools|"
                         r"anaconda\d*|miniconda\d*|dart-sdk|xampp|laragon|wamp.*)$", re.I)
EJECUTABLES_SDK = {"flutter", "flutter.bat", "java.exe", "node.exe", "python.exe", "go.exe", "dart.exe",
                   "adb.exe", "gradle", "gradle.bat", "mvn", "mvn.cmd", "ffmpeg.exe"}

# Nombres de carpeta que ya dicen qué son
NOMBRES_MEDIA = {
    "imagen": re.compile(r"\b(fotos?|im[aá]genes|pictures|photos|capturas|screenshots|wallpapers?|fondos)\b", re.I),
    "video": re.compile(r"\b(videos?|v[ií]deos|grabaciones|clips)\b", re.I),
    "musica": re.compile(r"\b(m[uú]sica|music|canciones|audios?)\b", re.I),
}


@dataclass
class Inspeccion:
    total: int = 0
    tipos: Counter = field(default_factory=Counter)   # codigo, programa, doc, imagen, video, musica, comprimido, otro
    marcas: set = field(default_factory=set)
    ultima_modificacion: float = 0.0
    nombres: list = field(default_factory=list)       # nombres de archivos (para clasificar por tema)
    docs: list = field(default_factory=list)          # algunos documentos para leer
    es_sdk: bool = False
    incompleta: bool = False                          # se cortó por ser demasiado grande


def _tipo(ext: str) -> str:
    if ext in EXT_CODIGO:
        return "codigo"
    if ext in EXT_PROGRAMA:
        return "programa"
    if ext in EXT_DOC:
        return "doc"
    if ext in EXT_IMAGEN:
        return "imagen"
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_MUSICA:
        return "musica"
    if ext in EXT_COMPRIMIDO or re.fullmatch(r"\.(z|r)\d\d", ext):
        return "comprimido"
    return "otro"


def inspeccionar(carpeta: Path) -> Inspeccion:
    ins = Inspeccion()
    if NOMBRES_SDK.match(carpeta.name):
        ins.es_sdk = True
    try:
        bin_dir = carpeta / "bin"
        if bin_dir.is_dir() and any(h.name.lower() in EJECUTABLES_SDK for h in bin_dir.iterdir()):
            ins.es_sdk = True
    except OSError:
        pass
    if ins.es_sdk:
        return ins

    pila = [(carpeta, 0)]
    while pila:
        actual, nivel = pila.pop()
        try:
            entradas = list(os.scandir(actual))
        except OSError:
            continue
        for e in entradas:
            nombre = e.name.lower()
            if nivel <= 2 and (nombre in MARCAS_PROYECTO or nombre.endswith(".sln")):
                ins.marcas.add(nombre)
            try:
                if e.is_dir(follow_symlinks=False):
                    if nombre in ("node_modules", ".git", "__pycache__", ".venv", "venv"):
                        continue
                    pila.append((Path(e.path), nivel + 1))
                elif e.is_file(follow_symlinks=False):
                    ins.total += 1
                    ext = os.path.splitext(nombre)[1]
                    t = _tipo(ext)
                    ins.tipos[t] += 1
                    ins.ultima_modificacion = max(ins.ultima_modificacion, e.stat().st_mtime)
                    if len(ins.nombres) < 300:
                        ins.nombres.append(os.path.splitext(e.name)[0])
                    if t == "doc" and len(ins.docs) < MAX_DOCS_LEIDOS and ext in (".pdf", ".docx", ".txt", ".pptx", ".xlsx"):
                        ins.docs.append(Path(e.path))
            except OSError:
                continue
            if ins.total >= MAX_ARCHIVOS:
                ins.incompleta = True
                return ins
    return ins


def proporcion(ins: Inspeccion, *tipos: str) -> float:
    return sum(ins.tipos[t] for t in tipos) / ins.total if ins.total else 0.0


def tipo_media_por_nombre(nombre: str) -> str | None:
    for tipo, patron in NOMBRES_MEDIA.items():
        if patron.search(nombre):
            return tipo
    return None
