"""Decide la categoría de un documento y a qué persona pertenece, según su contenido."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PUNTAJE_MINIMO = 2      # menos que esto => "Otros"
PESO_NOMBRE = 3         # una palabra en el nombre del archivo vale más que en el texto
TOPE_REPETICIONES = 3   # una palabra repetida 50 veces no debe dominar


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar 'Liquidación' con 'liquidacion'."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    # separa palabras pegadas por _ - . en nombres de archivo
    return re.sub(r"[_\-.]+", " ", texto)


def _patron(palabra: str) -> re.Pattern:
    p = re.escape(normalizar(palabra).strip()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){p}(?![a-z0-9])")


@dataclass
class Resultado:
    categoria: str
    puntaje: int
    persona: str | None
    motivo: str


class Clasificador:
    def __init__(self, categorias: dict[str, dict], personas: list[dict]):
        self._reglas = []
        for nombre, datos in categorias.items():
            palabras = [(w, _patron(w), 1 + w.count(" ")) for w in datos.get("palabras", [])]
            self._reglas.append((nombre, palabras))
        self._personas = []
        for p in personas:
            nombre = (p.get("nombre") or "").strip()
            if not nombre:
                continue
            textos = [nombre] + [a for a in p.get("alias", []) if a.strip()]
            patrones = [_patron(t) for t in textos]
            ruts = {self._solo_rut(r) for r in p.get("rut", []) if self._solo_rut(r)}
            self._personas.append((nombre, patrones, ruts))

    @staticmethod
    def _solo_rut(rut: str) -> str:
        return re.sub(r"[^0-9k]", "", rut.lower())

    def categoria(self, nombre_archivo: str, texto: str) -> tuple[str, int, str]:
        nom = normalizar(nombre_archivo)
        txt = normalizar(texto)
        mejor, mejor_puntos, mejor_hits = "Otros", 0, []
        for categoria, palabras in self._reglas:
            puntos, hits = 0, []
            for palabra, patron, bono in palabras:
                en_nombre = len(patron.findall(nom))
                en_texto = min(len(patron.findall(txt)), TOPE_REPETICIONES) if txt else 0
                p = (min(en_nombre, 1) * PESO_NOMBRE + en_texto) * bono
                if p:
                    puntos += p
                    hits.append(palabra)
            if puntos > mejor_puntos:
                mejor, mejor_puntos, mejor_hits = categoria, puntos, hits
        if mejor_puntos < PUNTAJE_MINIMO:
            return "Otros", mejor_puntos, "sin palabras clave suficientes"
        return mejor, mejor_puntos, "palabras: " + ", ".join(mejor_hits[:5])

    def persona(self, nombre_archivo: str, texto: str) -> str | None:
        if not self._personas:
            return None
        base = normalizar(nombre_archivo + " " + texto)
        digitos = re.sub(r"[.\s]", "", (nombre_archivo + " " + texto).lower())
        ruts_texto = {self._solo_rut(m) for m in re.findall(r"\d{7,8}-?[\dk]", digitos)}
        mejor, mejor_hits = None, 0
        for nombre, patrones, ruts in self._personas:
            hits = sum(len(p.findall(base)) for p in patrones)
            hits += 10 * len(ruts & ruts_texto)   # el RUT es casi una prueba
            if hits > mejor_hits:
                mejor, mejor_hits = nombre, hits
        return mejor

    def clasificar(self, nombre_archivo: str, texto: str) -> Resultado:
        cat, pts, motivo = self.categoria(nombre_archivo, texto)
        return Resultado(cat, pts, self.persona(nombre_archivo, texto), motivo)
