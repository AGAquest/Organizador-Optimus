"""Revisa las carpetas y arma un plan de movimientos (sin mover nada todavía)."""
from __future__ import annotations

import os
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from . import analisis_carpetas as ac
from .carpetas import CarpetasUsuario
from .clasificador import Clasificador
from .extractor import extraer_texto

# Nunca se mueven: accesos directos, temporales, descargas a medias
NUNCA_MOVER_EXT = {".lnk", ".url", ".ini", ".tmp", ".crdownload", ".part", ".partial",
                   ".download", ".opdownload", ".!ut", ".lock"}

# Si una carpeta contiene alguno de estos, es un proyecto/programa: no se buscan PDFs dentro
MARCAS_PROYECTO = {".git", "package.json", "pom.xml", "build.gradle", "Cargo.toml",
                   "node_modules", ".venv", "venv", "requirements.txt", ".idea", ".vscode",
                   "setup.py", "pyproject.toml", "Makefile", "CMakeLists.txt", "go.mod"}

# Carpetas del perfil que no se revisan al buscar PDFs
CARPETAS_EXCLUIDAS = {"appdata", "application data", "local settings", "saved games",
                      "searches", "links", "contacts", "favorites", "3d objects",
                      "virtualbox vms", "microsoft", "onedrive - personal", "$recycle.bin"}

MAX_PROFUNDIDAD_PDF = 6


@dataclass
class Movimiento:
    origen: Path
    destino: Path
    accion: str          # "Ordenar documento", "Archivar", "Multimedia", "Duplicado"
    categoria: str
    persona: str | None
    motivo: str
    cuenta: str
    es_carpeta: bool = False
    sugerido: bool = True    # False = se muestra desmarcado; el usuario decide


@dataclass
class Plan:
    movimientos: list[Movimiento] = field(default_factory=list)
    omitidos: list[tuple[Path, str]] = field(default_factory=list)
    errores: list[tuple[Path, str]] = field(default_factory=list)


def _oculto(ruta: Path, st: os.stat_result) -> bool:
    if ruta.name.startswith((".", "~$")):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & (getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)))


def _ultimo_uso(st: os.stat_result) -> float:
    """Fecha más reciente entre modificación y (en Windows) creación.

    No se usa la fecha de "último acceso": OneDrive, el antivirus y el indexador la
    actualizan solos, así que no indica si una persona usó el archivo.
    """
    marcas = [st.st_mtime]
    if sys.platform == "win32":
        marcas.append(st.st_ctime)   # en Windows ctime = fecha de creación (ej. cuando se descargó)
    return max(marcas)


class Planificador:
    def __init__(self, cfg: dict, progreso: Callable[[str], None] | None = None):
        self.cfg = cfg
        self.progreso = progreso or (lambda _m: None)
        self.clasificador = Clasificador(cfg["categorias"], cfg.get("personas", []))
        self._tipo_por_ext = {}
        for tipo, exts in cfg["extensiones"].items():
            for e in exts:
                self._tipo_por_ext[e.lower()] = tipo
        self._ignorar = {n.lower() for n in cfg.get("ignorar", [])}
        self._ignorar |= {cfg["carpeta_destino"].lower(), cfg["carpeta_archivados"].lower()}
        self._ahora = time.time()
        self._destinos_reservados: set[str] = set()

    # ---------- utilidades ----------
    def tipo(self, ruta: Path) -> str:
        return self._tipo_por_ext.get(ruta.suffix.lower(), "otro")

    def _libre(self, destino: Path, es_carpeta: bool = False) -> Path:
        """Si ya existe un archivo con ese nombre, usa 'nombre (2).ext', 'nombre (3).ext'..."""
        candidato, n = destino, 2
        # en carpetas no hay extensión ("Kit_v2.9.3" no debe partirse en el punto)
        base, ext = (destino.name, "") if es_carpeta else (destino.stem, destino.suffix)
        while candidato.exists() or str(candidato).lower() in self._destinos_reservados:
            candidato = destino.with_name(f"{base} ({n}){ext}")
            n += 1
        self._destinos_reservados.add(str(candidato).lower())
        return candidato

    @staticmethod
    def _mismo_contenido(a: Path, b: Path) -> bool:
        try:
            if a.stat().st_size != b.stat().st_size:
                return False
            with open(a, "rb") as fa, open(b, "rb") as fb:
                while True:
                    ca, cb = fa.read(1 << 20), fb.read(1 << 20)
                    if ca != cb:
                        return False
                    if not ca:
                        return True
        except OSError:
            return False

    def _raiz(self, cu: CarpetasUsuario) -> Path:
        return cu.documentos / self.cfg["carpeta_destino"]

    # ---------- qué archivos revisar ----------
    def _archivos_sueltos(self, carpeta: Path | None) -> Iterable[Path]:
        if not carpeta or not carpeta.is_dir():
            return []
        try:
            return [p for p in carpeta.iterdir() if p.is_file()]
        except OSError:
            return []

    def _carpetas_sueltas(self, carpeta: Path | None) -> Iterable[Path]:
        if not carpeta or not carpeta.is_dir():
            return []
        try:
            return [p for p in carpeta.iterdir() if p.is_dir() and not p.is_symlink()]
        except OSError:
            return []

    def _pdfs_en_perfil(self, cu: CarpetasUsuario) -> Iterable[Path]:
        """PDFs repartidos por el perfil que todavía no están en Documentos.

        No entra a Documentos (ya están guardados ahí), AppData, carpetas ocultas,
        ni carpetas de proyectos/programas (las que tienen .git, package.json, etc.).
        """
        no_entrar = {cu.documentos.resolve()}

        def recorrer(carpeta: Path, nivel: int):
            if nivel > MAX_PROFUNDIDAD_PDF:
                return
            try:
                hijos = list(carpeta.iterdir())
            except OSError:
                return
            if {h.name for h in hijos} & MARCAS_PROYECTO:
                return
            for h in hijos:
                try:
                    if h.is_symlink():
                        continue
                    if h.is_dir():
                        n = h.name.lower()
                        if (n.startswith((".", "$")) or n in CARPETAS_EXCLUIDAS
                                or n in self._ignorar or h.resolve() in no_entrar):
                            continue
                        yield from recorrer(h, nivel + 1)
                    elif h.suffix.lower() == ".pdf":
                        yield h
                except OSError:
                    continue

        yield from recorrer(cu.perfil, 0)

    # ---------- decisión por archivo ----------
    def _decidir(self, ruta: Path, cu: CarpetasUsuario, origen_nombre: str, plan: Plan) -> None:
        try:
            st = ruta.stat()
        except OSError as e:
            plan.errores.append((ruta, str(e)))
            return
        ext = ruta.suffix.lower()
        if ruta.name.lower() in self._ignorar or ext in NUNCA_MOVER_EXT:
            plan.omitidos.append((ruta, "acceso directo o archivo protegido"))
            return
        if _oculto(ruta, st):
            plan.omitidos.append((ruta, "archivo oculto o de sistema"))
            return
        if self._ahora - st.st_mtime < self.cfg["minutos_gracia"] * 60:
            plan.omitidos.append((ruta, "modificado recién (puede estar en uso)"))
            return

        dias_sin_uso = (self._ahora - _ultimo_uso(st)) / 86400
        inactivo = dias_sin_uso >= self.cfg["dias_inactivo"]
        anio = str(datetime.fromtimestamp(st.st_mtime).year)
        tipo = self.tipo(ruta)
        raiz = self._raiz(cu)

        if tipo in ("documento", "libro"):
            self.progreso(f"Leyendo {ruta.name}")
            if tipo == "libro":
                categoria, persona, motivo = "Libros", None, "formato de libro electrónico"
            else:
                r = self.clasificador.clasificar(ruta.stem, extraer_texto(ruta))
                categoria, persona, motivo = r.categoria, r.persona, r.motivo
            persona = persona or (self.cfg.get("persona_por_defecto") or None)
            destino_dir = raiz
            if persona:
                destino_dir = destino_dir / persona
            destino_dir = destino_dir / categoria
            if self.cfg.get("subcarpeta_por_anio") and categoria not in ("Libros", "Curriculum", "Identidad y Personales"):
                destino_dir = destino_dir / anio
            self._agregar(plan, ruta, destino_dir, "Ordenar documento", categoria, persona, motivo, cu, raiz)
            return

        if tipo in ("imagen", "video", "musica") and self.cfg.get("mover_multimedia") and inactivo:
            biblioteca = {"imagen": cu.imagenes, "video": cu.videos, "musica": cu.musica}[tipo]
            if biblioteca:
                self._agregar(plan, ruta, biblioteca / self.cfg["carpeta_destino"] / anio, "Multimedia",
                              tipo.capitalize(), None, f"sin uso hace {int(dias_sin_uso)} días", cu, raiz)
                return

        ya_descomprimido = tipo == "comprimido" and (ruta.parent / ruta.stem).is_dir()
        if inactivo or ya_descomprimido:
            motivo = ("ya está descomprimido al lado" if ya_descomprimido
                      else f"sin uso hace {int(dias_sin_uso)} días")
            archivados = self._carpeta_archivados(cu, origen_nombre)
            destino_dir = archivados / tipo.capitalize() / datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m")
            self._agregar(plan, ruta, destino_dir, "Archivar", tipo.capitalize(), None, motivo, cu, raiz)
            return

        plan.omitidos.append((ruta, f"en uso reciente (hace {int(dias_sin_uso)} días)"))

    def _decidir_carpeta(self, ruta: Path, cu: CarpetasUsuario, origen_nombre: str, plan: Plan) -> None:
        """Decide qué hacer con una carpeta completa (se mueve entera, nunca se desarma)."""
        try:
            st = ruta.stat()
        except OSError as e:
            plan.errores.append((ruta, str(e)))
            return
        if ruta.name.lower() in self._ignorar or _oculto(ruta, st):
            plan.omitidos.append((ruta, "carpeta protegida u oculta"))
            return
        self.progreso(f"Revisando carpeta {ruta.name}")
        ins = ac.inspeccionar(ruta)
        if ins.es_sdk:
            plan.omitidos.append((ruta, "herramienta instalada (SDK): moverla rompería los programas que la usan"))
            return
        if ins.total == 0:
            plan.omitidos.append((ruta, "carpeta vacía"))
            return
        ultima = ins.ultima_modificacion or st.st_mtime
        if self._ahora - ultima < self.cfg["minutos_gracia"] * 60:
            plan.omitidos.append((ruta, "tiene archivos modificados recién (puede estar en uso)"))
            return
        dias = int((self._ahora - ultima) / 86400)
        inactiva = dias >= self.cfg["dias_inactivo"]
        raiz = self._raiz(cu)
        nombre = ruta.name

        def agregar(destino_dir, accion, categoria, motivo, persona=None, sugerido=True):
            self._agregar(plan, ruta, destino_dir, accion, categoria, persona, motivo, cu, raiz,
                          es_carpeta=True, sugerido=sugerido)

        # 1. El nombre ya dice que son fotos / videos / música
        media = ac.tipo_media_por_nombre(nombre)
        if media is None:
            for t in ("imagen", "video", "musica"):
                if ac.proporcion(ins, t) >= 0.8:
                    media = t
        if media and self.cfg.get("mover_multimedia"):
            biblioteca = {"imagen": cu.imagenes, "video": cu.videos, "musica": cu.musica}[media]
            if biblioteca:
                agregar(biblioteca / self.cfg["carpeta_destino"], "Carpeta multimedia", media.capitalize(),
                        f"carpeta de {media} ({ins.total} archivos)")
                return

        # 2. El nombre coincide con una categoría (Universidad → Estudios, Libros → Libros...)
        cat_nombre, pts_nombre, _ = self.clasificador.categoria(nombre, "")
        es_proyecto = bool(ins.marcas) or ac.proporcion(ins, "codigo") >= 0.4
        # muchos .exe/.dll aunque también haya manuales o txt → es una carpeta de programas
        es_programa = (ac.proporcion(ins, "programa", "comprimido") >= 0.5
                       or ins.tipos["programa"] >= 20 or ac.proporcion(ins, "programa") >= 0.2)

        if cat_nombre != "Otros" and pts_nombre >= 3:
            persona = self.clasificador.persona(nombre, " ".join(ins.nombres[:100]))
            persona = persona or (self.cfg.get("persona_por_defecto") or None)
            destino = raiz / persona / cat_nombre if persona else raiz / cat_nombre
            agregar(destino, "Ordenar carpeta", cat_nombre, f"el nombre indica {cat_nombre}", persona)
            return

        # 3. Proyectos de código: se sugieren pero desmarcados (moverlos puede romper rutas del IDE/Docker)
        if es_proyecto:
            marcas = ", ".join(sorted(ins.marcas)[:3]) or "mayoría de archivos de código"
            agregar(raiz / "Proyectos", "Ordenar carpeta", "Proyectos",
                    f"proyecto de código ({marcas}); revisa antes de mover", sugerido=False)
            return

        # 4. Programas, instaladores, ISOs
        if es_programa:
            destino = (self._carpeta_archivados(cu, origen_nombre) / "Programas" if inactiva
                       else raiz / "Programas e Instaladores")
            agregar(destino, "Archivar" if inactiva else "Ordenar carpeta", "Programas",
                    f"contiene programas o instaladores (sin cambios hace {dias} días); revisa antes de mover",
                    sugerido=False)
            return

        # 5. Carpetas de documentos: se lee una muestra para entender el tema
        if ac.proporcion(ins, "doc") >= 0.5 or ins.tipos["doc"] >= 3:
            texto = " ".join(extraer_texto(d)[:4000] for d in ins.docs)
            r = self.clasificador.clasificar(nombre + " " + " ".join(ins.nombres[:100]), texto)
            persona = r.persona or (self.cfg.get("persona_por_defecto") or None)
            categoria = r.categoria if r.categoria != "Otros" else "Documentos varios"
            destino = raiz / persona / categoria if persona else raiz / categoria
            agregar(destino, "Ordenar carpeta", categoria, f"{ins.tipos['doc']} documentos; {r.motivo}", persona)
            return

        # 6. Lo demás: solo si no se usa hace tiempo
        if inactiva:
            agregar(self._carpeta_archivados(cu, origen_nombre) / "Carpetas", "Archivar", "Otros",
                    f"sin cambios hace {dias} días")
            return
        plan.omitidos.append((ruta, f"carpeta en uso (cambios hace {dias} días)"))

    def _carpeta_archivados(self, cu: CarpetasUsuario, origen_nombre: str) -> Path:
        # Lo de Descargas se archiva dentro de Descargas: así no se suben GB de basura a OneDrive
        if origen_nombre == "Descargas" and cu.descargas:
            return cu.descargas / self.cfg["carpeta_archivados"]
        return self._raiz(cu) / self.cfg["carpeta_archivados"] / origen_nombre

    def _agregar(self, plan: Plan, ruta: Path, destino_dir: Path, accion: str, categoria: str,
                 persona: str | None, motivo: str, cu: CarpetasUsuario, raiz: Path,
                 es_carpeta: bool = False, sugerido: bool = True) -> None:
        destino = destino_dir / ruta.name
        if es_carpeta:
            if destino.resolve() == ruta.resolve() or destino.resolve().is_relative_to(ruta.resolve()):
                return
            plan.movimientos.append(Movimiento(ruta, self._libre(destino, True), accion, categoria,
                                               persona, motivo, cu.cuenta, True, sugerido))
            return
        if destino.exists() and self._mismo_contenido(ruta, destino):
            destino_dir = raiz / self.cfg["carpeta_archivados"] / "Duplicados"
            destino = destino_dir / ruta.name
            accion, motivo = "Duplicado", "ya existe una copia idéntica ordenada"
        if destino.resolve() == ruta.resolve():
            return
        plan.movimientos.append(Movimiento(ruta, self._libre(destino), accion, categoria,
                                           persona, motivo, cu.cuenta))

    # ---------- entrada principal ----------
    def planificar(self, cuentas: list[CarpetasUsuario]) -> Plan:
        plan = Plan()
        for cu in cuentas:
            self.progreso(f"Revisando cuenta {cu.cuenta}")
            vistos: set[Path] = set()
            fuentes = []
            if self.cfg.get("revisar_escritorio"):
                fuentes.append(("Escritorio", self._archivos_sueltos(cu.escritorio)))
            if self.cfg.get("revisar_descargas"):
                fuentes.append(("Descargas", self._archivos_sueltos(cu.descargas)))
            if self.cfg.get("buscar_pdfs_en_perfil"):
                fuentes.append(("Perfil", self._pdfs_en_perfil(cu)))
            if self.cfg.get("ordenar_carpetas", True):
                if self.cfg.get("revisar_escritorio"):
                    fuentes.append(("Escritorio", self._carpetas_sueltas(cu.escritorio)))
                if self.cfg.get("revisar_descargas"):
                    fuentes.append(("Descargas", self._carpetas_sueltas(cu.descargas)))
            for nombre, archivos in fuentes:
                for ruta in archivos:
                    if ruta.is_dir():
                        self._decidir_carpeta(ruta, cu, nombre, plan)
                        continue
                    clave = ruta.resolve()
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    self._decidir(ruta, cu, nombre, plan)
        return plan
