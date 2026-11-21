import os
import time
from pathlib import Path

import pytest

from organizador_optimus import config, motor, planificador
from organizador_optimus.carpetas import CarpetasUsuario
from organizador_optimus.clasificador import Clasificador
from organizador_optimus.planificador import Planificador

VIEJO = time.time() - 90 * 86400


def _crear(ruta: Path, contenido: str = "x", viejo: bool = True) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    t = VIEJO if viejo else time.time() - 3600
    os.utime(ruta, (t, t))
    return ruta


@pytest.fixture(autouse=True)
def fecha_solo_modificacion(monkeypatch):
    """En Windows la fecha de creación de los archivos de prueba es "ahora" y no se puede
    cambiar con os.utime; para simular archivos viejos se usa solo la fecha de modificación."""
    monkeypatch.setattr(planificador, "_ultimo_uso", lambda st: st.st_mtime)


@pytest.fixture
def pc(tmp_path):
    perfil = tmp_path / "jandi"
    cu = CarpetasUsuario("jandi", perfil, perfil / "OneDrive/Escritorio", perfil / "OneDrive/Documentos",
                         perfil / "Downloads", perfil / "Pictures", perfil / "Videos", perfil / "Music")
    for p in (cu.escritorio, cu.documentos, cu.descargas, cu.imagenes, cu.videos, cu.musica):
        p.mkdir(parents=True)
    return cu


@pytest.fixture
def cfg():
    c = config.cargar(Path("/no/existe.json"))
    c["personas"] = [{"nombre": "Alejandro", "alias": ["Alejandro Gonzalez"], "rut": ["12.345.678-9"]},
                     {"nombre": "Maria", "alias": ["María Pérez"], "rut": []}]
    return c


def test_clasificador_categorias(cfg):
    c = Clasificador(cfg["categorias"], cfg["personas"])
    assert c.categoria("Liquidacion_sueldo_octubre", "")[0] == "Trabajo"
    assert c.categoria("doc1", "FACTURA ELECTRÓNICA N° 123 RUT EMISOR 76.111.111-1 IVA 19% Total a pagar")[0] == "Facturas y Boletas"
    assert c.categoria("Guia Pablo Progra", "Ejercicios de programación del curso")[0] == "Estudios"
    assert c.categoria("Carnet Delante0001", "")[0] == "Identidad y Personales"
    assert c.categoria("asdf", "hola mundo")[0] == "Otros"


def test_clasificador_personas(cfg):
    c = Clasificador(cfg["categorias"], cfg["personas"])
    assert c.persona("cartola", "Cliente: ALEJANDRO GONZALEZ") == "Alejandro"
    assert c.persona("certificado", "RUT 12345678-9") == "Alejandro"
    assert c.persona("receta", "Paciente: María Pérez") == "Maria"
    assert c.persona("receta", "Paciente: Pedro") is None


def test_plan_completo(pc, cfg):
    e, d = pc.escritorio, pc.descargas
    _crear(e / "Liquidacion sueldo.txt", "Liquidación de sueldo de Alejandro Gonzalez, AFP, previred")
    _crear(e / "Juego.lnk")
    _crear(e / "Juego.url")
    _crear(e / "nuevo.txt", "factura", viejo=False)            # reciente pero documento → se ordena
    _crear(d / "instalador.exe")                                 # viejo → archivar dentro de Descargas
    _crear(d / "foto.jpg")                                       # viejo → Imágenes
    _crear(e / "proyecto.zip")
    (e / "proyecto").mkdir()                                     # zip ya descomprimido
    _crear(d / "reciente.zip", viejo=False)                      # reciente → se queda
    _crear(d / "bajando.crdownload")

    plan = Planificador(cfg).planificar([pc])
    por_nombre = {m.origen.name: m for m in plan.movimientos}

    m = por_nombre["Liquidacion sueldo.txt"]
    assert m.persona == "Alejandro" and m.categoria == "Trabajo"
    assert m.destino.parent.parent == pc.documentos / "Organizador Optimus" / "Alejandro" / "Trabajo"
    assert "nuevo.txt" in por_nombre
    assert por_nombre["instalador.exe"].destino.is_relative_to(d / "Archivados")
    assert por_nombre["foto.jpg"].destino.is_relative_to(pc.imagenes)
    assert por_nombre["proyecto.zip"].accion == "Archivar"
    for n in ("Juego.lnk", "Juego.url", "reciente.zip", "bajando.crdownload"):
        assert n not in por_nombre


def test_ejecutar_y_deshacer(pc, cfg, tmp_path):
    a = _crear(pc.escritorio / "boleta.txt", "boleta electrónica sii iva total a pagar")
    b = _crear(pc.descargas / "programa.msi")
    plan = Planificador(cfg).planificar([pc])
    hist = tmp_path / "hist"
    hist.mkdir()
    r = motor.ejecutar(plan.movimientos, historial_dir=hist)
    assert r.movidos == 2 and not a.exists() and not b.exists()
    r2 = motor.deshacer(motor.historiales(hist)[0])
    assert r2.movidos == 2 and a.exists() and b.exists()
    # las carpetas vacías creadas por la app se limpian, Documentos sigue existiendo
    assert pc.documentos.exists()
    assert not (pc.documentos / "Organizador Optimus" / "Facturas y Boletas").exists()


def test_nombres_repetidos_y_duplicados(pc, cfg):
    destino = pc.documentos / "Organizador Optimus" / "Otros" / "2000"
    _crear(pc.escritorio / "nota.txt", "algo distinto")
    t = VIEJO
    destino.mkdir(parents=True)
    plan = Planificador({**cfg, "subcarpeta_por_anio": False}).planificar([pc])
    assert plan.movimientos[0].destino.name == "nota.txt"
    # mismo nombre pero distinto contenido ya ordenado → se renombra
    _crear(pc.documentos / "Organizador Optimus" / "Otros" / "nota.txt", "otro contenido")
    plan = Planificador({**cfg, "subcarpeta_por_anio": False}).planificar([pc])
    assert plan.movimientos[0].destino.name == "nota (2).txt"
    # copia idéntica → va a Duplicados
    _crear(pc.documentos / "Organizador Optimus" / "Otros" / "nota.txt", "algo distinto")
    plan = Planificador({**cfg, "subcarpeta_por_anio": False}).planificar([pc])
    assert plan.movimientos[0].accion == "Duplicado"
    assert t


def test_pdfs_en_perfil_respeta_proyectos(pc, cfg):
    cfg["buscar_pdfs_en_perfil"] = True
    _crear(pc.perfil / "Cosas" / "contrato de arriendo.pdf")
    _crear(pc.perfil / "mi-proyecto" / "package.json")
    _crear(pc.perfil / "mi-proyecto" / "docs" / "manual.pdf")
    _crear(pc.perfil / "AppData" / "x.pdf")
    _crear(pc.documentos / "ya guardado.pdf")
    plan = Planificador(cfg).planificar([pc])
    nombres = {m.origen.name for m in plan.movimientos}
    assert nombres == {"contrato de arriendo.pdf"}


def test_carpetas(pc, cfg):
    e = pc.escritorio
    _crear(e / "Universidad" / "6to Semestre" / "informe.docx")
    _crear(e / "Fotos" / "Celu" / "a.jpg")
    _crear(e / "mi-app" / "package.json", "{}")
    _crear(e / "mi-app" / "src" / "index.js")
    _crear(e / "flutter" / "bin" / "flutter.bat")
    _crear(e / "Kit_v2.9.3" / "setup.exe")
    _crear(e / "Kit_v2.9.3" / "driver.dll")
    _crear(e / "Papeles" / "cartola banco.pdf", "")
    _crear(e / "Papeles" / "estado de cuenta.pdf", "")
    _crear(e / "Papeles" / "transferencia.txt", "transferencia banco cuenta corriente")
    (e / "vacia").mkdir()
    for i in range(25):                       # caja de herramientas: muchos .exe y además manuales
        _crear(e / "USB tecnico" / f"tool{i}.exe")
    for i in range(40):
        _crear(e / "USB tecnico" / f"leeme{i}.txt")

    plan = Planificador(cfg).planificar([pc])
    m = {x.origen.name: x for x in plan.movimientos if x.es_carpeta}
    assert m["Universidad"].categoria == "Estudios" and m["Universidad"].sugerido
    assert m["Fotos"].destino.parent == pc.imagenes / "Organizador Optimus"
    assert m["mi-app"].categoria == "Proyectos" and not m["mi-app"].sugerido
    assert m["Kit_v2.9.3"].categoria == "Programas" and not m["Kit_v2.9.3"].sugerido
    assert m["Papeles"].categoria == "Bancos y Finanzas"
    assert m["USB tecnico"].categoria == "Programas" and not m["USB tecnico"].sugerido
    assert "flutter" not in m and "vacia" not in m
    # se mueven enteras y se pueden devolver
    r = motor.ejecutar([m["Universidad"]], historial_dir=pc.perfil)
    assert r.movidos == 1 and (m["Universidad"].destino / "6to Semestre" / "informe.docx").exists()
    motor.deshacer(motor.historiales(pc.perfil)[0])
    assert (e / "Universidad" / "6to Semestre" / "informe.docx").exists()
