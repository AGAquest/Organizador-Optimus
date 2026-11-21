"""Configuración del usuario, guardada en %APPDATA%\\OrganizadorOptimus\\config.json."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .carpetas import datos_app

# Categorías de documentos y sus palabras clave (pensadas para Chile).
# "peso" de una palabra = cuántos puntos suma si aparece en el texto.
# Las que aparecen en el NOMBRE del archivo valen el doble.
CATEGORIAS_POR_DEFECTO: dict[str, dict] = {
    "Facturas y Boletas": {
        "palabras": ["factura electrónica", "factura", "boleta electrónica", "boleta",
                     "sii", "iva", "neto", "total a pagar", "rut emisor", "nota de crédito",
                     "guía de despacho", "folio"],
    },
    "Bancos y Finanzas": {
        "palabras": ["cartola", "estado de cuenta", "banco", "transferencia", "comprobante de pago",
                     "tarjeta de crédito", "crédito hipotecario", "cuenta corriente", "cuenta vista",
                     "cuentarut", "bancoestado", "santander", "bci", "scotiabank", "itaú",
                     "inversión", "fondos mutuos", "dividendo"],
    },
    "Trabajo": {
        "palabras": ["liquidación de sueldo", "liquidación de remuneraciones", "contrato de trabajo",
                     "finiquito", "afp", "previred", "cotizaciones", "remuneración", "empleador",
                     "trabajador", "anexo de contrato", "vacaciones", "horas extra", "liquidación",
                     "sueldo", "contrato", "empresa"],
    },
    "Curriculum": {
        "palabras": ["curriculum vitae", "currículum", "curriculum", "cv", "experiencia laboral",
                     "formación académica", "habilidades", "referencias laborales"],
    },
    "Estudios": {
        "palabras": ["universidad", "instituto", "certificado de alumno regular", "alumno regular",
                     "asignatura", "evaluación", "guía", "tarea", "informe", "avance", "prueba",
                     "certamen", "profesor", "semestre", "carrera", "malla curricular", "curso",
                     "tesis", "duoc", "inacap", "liceo", "colegio", "apuntes", "ejercicios",
                     "programación", "progra", "clase", "certificado de título", "notas"],
    },
    "Identidad y Personales": {
        "palabras": ["cédula de identidad", "carnet", "pasaporte", "registro civil",
                     "certificado de nacimiento", "certificado de matrimonio", "antecedentes",
                     "clave única", "licencia de conducir", "cédula", "firma"],
    },
    "Salud": {
        "palabras": ["receta", "examen", "fonasa", "isapre", "licencia médica", "diagnóstico",
                     "clínica", "hospital", "laboratorio", "bono", "paciente", "médico",
                     "vacuna", "cesfam"],
    },
    "Hogar y Servicios": {
        "palabras": ["contrato de arriendo", "arriendo", "boleta de luz", "enel", "cge",
                     "aguas andinas", "esval", "essbio", "metrogas", "abastible", "lipigas",
                     "gastos comunes", "internet", "movistar", "entel", "vtr", "wom", "claro"],
    },
    "Vehiculo": {
        "palabras": ["permiso de circulación", "soap", "revisión técnica", "patente",
                     "padrón", "seguro automotriz", "vehículo"],
    },
    "Legal": {
        "palabras": ["notaría", "notario", "poder simple", "escritura", "demanda", "tribunal",
                     "juzgado", "declaración jurada", "mandato", "abogado"],
    },
    "Manuales y Guias": {
        "palabras": ["manual", "instrucciones", "guía de usuario", "user guide", "datasheet",
                     "especificaciones", "armado", "instalación"],
    },
    "Libros": {
        "palabras": ["isbn", "capítulo", "editorial", "prólogo", "chapter", "libro",
                     "libros", "novela", "ebook"],
    },
}

# Extensiones -> tipo de archivo
EXTENSIONES_POR_DEFECTO: dict[str, list[str]] = {
    "documento": [".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md",
                  ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp"],
    "libro": [".epub", ".mobi", ".azw", ".azw3", ".djvu"],
    "imagen": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".tif", ".tiff", ".svg", ".raw"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"],
    "musica": [".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"],
    "comprimido": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
    "instalador": [".exe", ".msi", ".msix", ".appx", ".iso"],
}

CONFIG_POR_DEFECTO: dict = {
    # Días sin modificar/abrir para considerar un archivo "no ocupado"
    "dias_inactivo": 30,
    # No tocar archivos modificados hace menos de estos minutos (pueden estar en uso)
    "minutos_gracia": 10,
    # Carpetas a revisar (solo archivos sueltos, no entra a subcarpetas)
    "revisar_escritorio": True,
    "revisar_descargas": True,
    # Ordenar también carpetas del Escritorio/Descargas (se mueven enteras, nunca se desarman)
    "ordenar_carpetas": True,
    # En el modo automático (tarea programada) mover también carpetas. Por defecto no: las
    # carpetas se ordenan solo desde la ventana, donde se pueden revisar antes.
    "carpetas_en_auto": False,
    # Buscar PDFs sueltos en todo el perfil del usuario (excluye AppData, proyectos, etc.)
    "buscar_pdfs_en_perfil": False,
    # Ordenar también las cuentas de otras personas del PC (requiere administrador)
    "incluir_otras_cuentas": False,
    # Carpeta raíz dentro de Documentos donde se ordena todo
    "carpeta_destino": "Organizador Optimus",
    # Nombre de la carpeta para archivos no ocupados
    "carpeta_archivados": "Archivados",
    # Ordenar documentos por año dentro de cada categoría
    "subcarpeta_por_anio": True,
    # Mover imágenes / videos / música a sus bibliotecas de Windows
    "mover_multimedia": True,
    # Personas que usan el PC: se detectan por nombre, alias o RUT dentro del documento
    # Ej: {"nombre": "Alejandro", "alias": ["Alejandro Gonzalez", "jandi"], "rut": ["12.345.678-9"]}
    "personas": [],
    # Carpeta para documentos de la cuenta sin persona detectada ("" = sin carpeta de persona)
    "persona_por_defecto": "",
    "categorias": CATEGORIAS_POR_DEFECTO,
    "extensiones": EXTENSIONES_POR_DEFECTO,
    # Nombres de archivo/carpeta que nunca se tocan
    "ignorar": ["desktop.ini", "thumbs.db", "Organizador Optimus"],
}


def ruta_config() -> Path:
    return datos_app() / "config.json"


def cargar(ruta: Path | None = None) -> dict:
    ruta = ruta or ruta_config()
    cfg = copy.deepcopy(CONFIG_POR_DEFECTO)
    if ruta.exists():
        try:
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
            cfg.update(guardado)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def guardar(cfg: dict, ruta: Path | None = None) -> None:
    ruta = ruta or ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
