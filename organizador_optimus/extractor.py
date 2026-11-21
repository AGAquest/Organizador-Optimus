"""Extrae texto de documentos para entender de qué tratan."""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

MAX_CARACTERES = 20000   # suficiente para clasificar, rápido de leer
MAX_PAGINAS_PDF = 5

logging.getLogger("pypdf").setLevel(logging.ERROR)   # PDFs dañados no deben llenar la consola


def _pdf(ruta: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        lector = PdfReader(str(ruta))
        if lector.is_encrypted:
            try:
                lector.decrypt("")
            except Exception:
                return ""
        partes = []
        for pagina in lector.pages[:MAX_PAGINAS_PDF]:
            partes.append(pagina.extract_text() or "")
            if sum(map(len, partes)) > MAX_CARACTERES:
                break
        return "\n".join(partes)
    except Exception:
        return ""


def _xml_de_zip(ruta: Path, patron: str) -> str:
    """Texto de documentos Office (docx, xlsx, pptx, odt...), que son zips con XML."""
    try:
        with zipfile.ZipFile(ruta) as z:
            textos = []
            for nombre in z.namelist():
                if re.fullmatch(patron, nombre):
                    xml = z.read(nombre).decode("utf-8", errors="ignore")
                    textos.append(re.sub(r"<[^>]+>", " ", xml))
                    if sum(map(len, textos)) > MAX_CARACTERES:
                        break
            return " ".join(textos)
    except Exception:
        return ""


def _texto_plano(ruta: Path) -> str:
    try:
        with open(ruta, "rb") as f:
            datos = f.read(MAX_CARACTERES)
        for cod in ("utf-8", "latin-1"):
            try:
                return datos.decode(cod)
            except UnicodeDecodeError:
                continue
    except OSError:
        pass
    return ""


def extraer_texto(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        texto = _pdf(ruta)
    elif ext == ".docx":
        texto = _xml_de_zip(ruta, r"word/(document|header\d*|footer\d*)\.xml")
    elif ext == ".pptx":
        texto = _xml_de_zip(ruta, r"ppt/slides/slide\d+\.xml")
    elif ext == ".xlsx":
        texto = _xml_de_zip(ruta, r"xl/sharedStrings\.xml")
    elif ext in (".odt", ".ods", ".odp"):
        texto = _xml_de_zip(ruta, r"content\.xml")
    elif ext in (".txt", ".md", ".csv", ".rtf"):
        texto = _texto_plano(ruta)
    else:
        texto = ""
    return texto[:MAX_CARACTERES]
