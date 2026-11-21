"""Ventana principal (Tkinter, viene incluido con Python: no requiere instalar nada)."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import APP_NAME, __version__, config, motor, programar
from .carpetas import carpetas_actuales, otras_cuentas
from .planificador import Movimiento
from .servicio import armar_plan

MARCA_SI, MARCA_NO = "☑", "☐"


def _abrir_carpeta(ruta: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(ruta))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(ruta)])


def _texto_corto(ruta: Path, base: Path | None = None) -> str:
    if base:
        try:
            return str(ruta.relative_to(base))
        except ValueError:
            pass
    return str(ruta)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1150x680")
        self.minsize(900, 520)
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        try:
            self._icono = tk.PhotoImage(file=str(base / "assets" / "icono.png"))
            self.iconphoto(True, self._icono)
        except tk.TclError:
            pass
        self.cfg = config.cargar()
        self.cu = carpetas_actuales()
        self.cola: queue.Queue = queue.Queue()
        self.movimientos: dict[str, Movimiento] = {}
        self.marcados: dict[str, bool] = {}
        self.ocupado = False

        estilo = ttk.Style(self)
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        estilo.configure("Accion.TButton", font=("Segoe UI", 10, "bold"))

        self._cabecera()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._pestana_ordenar(nb)
        self._pestana_personas(nb)
        self._pestana_ajustes(nb)
        self._pestana_historial(nb)

        self.estado = tk.StringVar(value="Listo. Presiona «Analizar» para ver qué se puede ordenar.")
        barra = ttk.Frame(self)
        barra.pack(fill="x", padx=10, pady=(0, 8))
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=160)
        self.progreso.pack(side="right")
        ttk.Label(barra, textvariable=self.estado).pack(side="left")
        self.after(100, self._revisar_cola)

    # ------------------------------------------------------------------ cabecera
    def _cabecera(self):
        f = ttk.Frame(self)
        f.pack(fill="x", padx=10, pady=8)
        ttk.Label(f, text=APP_NAME, style="Titulo.TLabel").pack(side="left")
        info = f"Cuenta: {self.cu.cuenta}    Documentos: {self.cu.documentos}"
        ttk.Label(f, text=info, foreground="#555").pack(side="left", padx=20)

    # ------------------------------------------------------------------ ordenar
    def _pestana_ordenar(self, nb: ttk.Notebook):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="  Ordenar  ")
        botones = ttk.Frame(f)
        botones.pack(fill="x", pady=(0, 6))
        self.btn_analizar = ttk.Button(botones, text="🔍 Analizar", command=self.analizar)
        self.btn_analizar.pack(side="left")
        self.btn_ordenar = ttk.Button(botones, text="✅ Ordenar marcados", style="Accion.TButton",
                                      command=self.ordenar, state="disabled")
        self.btn_ordenar.pack(side="left", padx=6)
        ttk.Button(botones, text="Marcar todo", command=lambda: self._marcar_todo(True)).pack(side="left", padx=(20, 2))
        ttk.Button(botones, text="Desmarcar todo", command=lambda: self._marcar_todo(False)).pack(side="left")
        ttk.Button(botones, text="↩ Deshacer última vez", command=self.deshacer_ultima).pack(side="right")
        ttk.Button(botones, text="📂 Abrir carpeta ordenada",
                   command=self._abrir_destino).pack(side="right", padx=6)

        cols = ("ok", "accion", "archivo", "destino", "categoria", "persona", "motivo")
        cont = ttk.Frame(f)
        cont.pack(fill="both", expand=True)
        self.tabla = ttk.Treeview(cont, columns=cols, show="headings", selectmode="extended")
        titulos = {"ok": "", "accion": "Acción", "archivo": "Archivo", "destino": "Irá a",
                   "categoria": "Categoría", "persona": "Persona", "motivo": "Por qué"}
        anchos = {"ok": 30, "accion": 120, "archivo": 240, "destino": 320, "categoria": 130,
                  "persona": 90, "motivo": 220}
        for c in cols:
            self.tabla.heading(c, text=titulos[c])
            self.tabla.column(c, width=anchos[c], anchor="center" if c == "ok" else "w",
                              stretch=c not in ("ok",))
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=sb.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tabla.bind("<Button-1>", self._clic_tabla)
        self.tabla.bind("<space>", self._espacio_tabla)
        self.tabla.bind("<Double-1>", self._doble_clic)
        self.tabla.tag_configure("no", foreground="#999")
        ttk.Label(f, foreground="#555",
                  text="Clic en ☑ para incluir/excluir · Espacio cambia los seleccionados · "
                       "Doble clic abre la carpeta del archivo. Nada se borra: todo se puede deshacer.").pack(anchor="w", pady=(6, 0))

    def _clic_tabla(self, ev):
        if self.tabla.identify_region(ev.x, ev.y) == "cell" and self.tabla.identify_column(ev.x) == "#1":
            iid = self.tabla.identify_row(ev.y)
            if iid:
                self._alternar([iid])
                return "break"

    def _espacio_tabla(self, _ev):
        self._alternar(list(self.tabla.selection()))
        return "break"

    def _doble_clic(self, ev):
        iid = self.tabla.identify_row(ev.y)
        if iid in self.movimientos:
            m = self.movimientos[iid]
            _abrir_carpeta(m.origen.parent if m.origen.exists() else m.destino.parent)

    def _alternar(self, iids):
        for iid in iids:
            self._poner_marca(iid, not self.marcados.get(iid, False))
        self._actualizar_contador()

    def _poner_marca(self, iid, valor: bool):
        self.marcados[iid] = valor
        self.tabla.set(iid, "ok", MARCA_SI if valor else MARCA_NO)
        self.tabla.item(iid, tags=() if valor else ("no",))

    def _marcar_todo(self, valor: bool):
        for iid in self.movimientos:
            self._poner_marca(iid, valor)
        self._actualizar_contador()

    def _actualizar_contador(self):
        n = sum(self.marcados.values())
        self.btn_ordenar.configure(state="normal" if n and not self.ocupado else "disabled",
                                   text=f"✅ Ordenar marcados ({n})")

    def _abrir_destino(self):
        d = self.cu.documentos / self.cfg["carpeta_destino"]
        d.mkdir(parents=True, exist_ok=True)
        _abrir_carpeta(d)

    # ------------------------------------------------------------------ tareas en segundo plano
    def _en_segundo_plano(self, trabajo, al_terminar):
        self.ocupado = True
        self.btn_analizar.configure(state="disabled")
        self.btn_ordenar.configure(state="disabled")
        self.progreso.start(12)

        def correr():
            try:
                res = trabajo(lambda msg: self.cola.put(("estado", msg)))
                self.cola.put(("fin", (al_terminar, res, None)))
            except Exception as e:  # noqa: BLE001
                self.cola.put(("fin", (al_terminar, None, e)))

        threading.Thread(target=correr, daemon=True).start()

    def _revisar_cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "estado":
                    self.estado.set(dato)
                elif tipo == "fin":
                    al_terminar, res, err = dato
                    self.ocupado = False
                    self.progreso.stop()
                    self.btn_analizar.configure(state="normal")
                    self._actualizar_contador()
                    if err:
                        messagebox.showerror(APP_NAME, f"Ocurrió un error:\n{err}")
                        self.estado.set("Error.")
                    else:
                        al_terminar(res)
        except queue.Empty:
            pass
        self.after(100, self._revisar_cola)

    # ------------------------------------------------------------------ acciones
    def analizar(self):
        self._guardar_ajustes(silencioso=True)
        self.tabla.delete(*self.tabla.get_children())
        self.movimientos.clear()
        self.marcados.clear()
        cfg = dict(self.cfg)
        self._en_segundo_plano(lambda prog: armar_plan(cfg, prog), self._mostrar_plan)

    def _mostrar_plan(self, plan):
        base = self.cu.perfil
        for i, m in enumerate(plan.movimientos):
            iid = str(i)
            self.movimientos[iid] = m
            nombre = ("📁 " if m.es_carpeta else "") + m.origen.name
            self.tabla.insert("", "end", iid=iid, values=(
                MARCA_SI, m.accion, nombre, _texto_corto(m.destino.parent, base),
                m.categoria, m.persona or "—", m.motivo))
            self._poner_marca(iid, m.sugerido)
        self._actualizar_contador()
        revisar = sum(1 for m in plan.movimientos if not m.sugerido)
        if revisar:
            messagebox.showinfo(APP_NAME, f"{revisar} carpetas quedaron DESMARCADAS (proyectos de código o "
                                          "programas). Moverlas puede romper accesos o rutas: márcalas solo "
                                          "si estás seguro.")
        if plan.movimientos:
            self.estado.set(f"{len(plan.movimientos)} elementos para ordenar · "
                            f"{len(plan.omitidos)} se dejan donde están (accesos directos, en uso, recientes).")
        else:
            self.estado.set(f"Todo está en orden. {len(plan.omitidos)} archivos se dejan donde están.")

    def ordenar(self):
        elegidos = [self.movimientos[i] for i, ok in self.marcados.items() if ok]
        if not elegidos:
            return
        if not messagebox.askyesno(APP_NAME, f"¿Mover {len(elegidos)} archivos?\n\n"
                                             "No se borra nada y puedes deshacerlo después."):
            return
        self._en_segundo_plano(lambda prog: motor.ejecutar(elegidos, prog), self._fin_ordenar)

    def _fin_ordenar(self, r: motor.Resumen):
        for iid, ok in list(self.marcados.items()):
            if ok:
                self.tabla.delete(iid)
                self.movimientos.pop(iid, None)
                self.marcados.pop(iid, None)
        self._actualizar_contador()
        self._cargar_historial()
        msg = f"Listo: {r.movidos} archivos ordenados."
        if r.errores:
            msg += f"\n\nNo se pudieron mover {len(r.errores)}:\n" + "\n".join(
                f"• {Path(o).name}: {e}" for o, e in r.errores[:10])
        self.estado.set(f"{r.movidos} archivos ordenados.")
        messagebox.showinfo(APP_NAME, msg)

    def deshacer_ultima(self):
        hs = motor.historiales()
        if not hs:
            messagebox.showinfo(APP_NAME, "No hay nada que deshacer.")
            return
        self._deshacer(hs[0])

    def _deshacer(self, archivo: Path):
        if not messagebox.askyesno(APP_NAME, f"¿Devolver los archivos de la ejecución {archivo.stem} "
                                             "a donde estaban?"):
            return
        self._en_segundo_plano(lambda prog: motor.deshacer(archivo, prog), self._fin_deshacer)

    def _fin_deshacer(self, r: motor.Resumen):
        self._cargar_historial()
        msg = f"Se devolvieron {r.movidos} archivos."
        if r.errores:
            msg += f"\n{len(r.errores)} no se pudieron devolver (quizás los moviste o borraste)."
        self.estado.set(msg)
        messagebox.showinfo(APP_NAME, msg)

    # ------------------------------------------------------------------ personas
    def _pestana_personas(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="  Personas  ")
        ttk.Label(f, wraplength=1000, justify="left", text=(
            "Si varias personas usan esta cuenta, agrégalas aquí. Cuando un documento menciona su "
            "nombre, un alias o su RUT, se guarda en su carpeta: Documentos\\Organizador Optimus\\<Persona>\\...\n"
            "Si cada persona tiene su propia cuenta de Windows, actívalo en Ajustes → «Ordenar también otras cuentas».")
        ).pack(anchor="w", pady=(0, 8))

        cont = ttk.Frame(f)
        cont.pack(fill="both", expand=True)
        self.tabla_personas = ttk.Treeview(cont, columns=("nombre", "alias", "rut"), show="headings", height=8)
        for c, t, w in (("nombre", "Nombre (carpeta)", 200), ("alias", "Alias / otros nombres", 400),
                        ("rut", "RUT", 200)):
            self.tabla_personas.heading(c, text=t)
            self.tabla_personas.column(c, width=w)
        self.tabla_personas.pack(side="left", fill="both", expand=True)
        self.tabla_personas.bind("<<TreeviewSelect>>", self._persona_seleccionada)

        form = ttk.LabelFrame(f, text="Persona", padding=8)
        form.pack(fill="x", pady=8)
        self.p_nombre, self.p_alias, self.p_rut = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for fila, (txt, var, ayuda) in enumerate((
                ("Nombre:", self.p_nombre, "Ej: Alejandro"),
                ("Alias:", self.p_alias, "Separados por coma. Ej: Alejandro Gonzalez, Jandi"),
                ("RUT:", self.p_rut, "Separados por coma. Ej: 12.345.678-9"))):
            ttk.Label(form, text=txt).grid(row=fila, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=var, width=60).grid(row=fila, column=1, sticky="w", padx=6)
            ttk.Label(form, text=ayuda, foreground="#777").grid(row=fila, column=2, sticky="w")
        bf = ttk.Frame(form)
        bf.grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Button(bf, text="Agregar / actualizar", command=self._guardar_persona).pack(side="left")
        ttk.Button(bf, text="Quitar", command=self._quitar_persona).pack(side="left", padx=6)

        pd = ttk.Frame(f)
        pd.pack(fill="x")
        ttk.Label(pd, text="Documentos sin persona detectada van a la carpeta de:").pack(side="left")
        self.persona_def = tk.StringVar(value=self.cfg.get("persona_por_defecto", ""))
        self.combo_def = ttk.Combobox(pd, textvariable=self.persona_def, width=25)
        self.combo_def.pack(side="left", padx=6)
        ttk.Label(pd, text="(vacío = carpeta común)", foreground="#777").pack(side="left")
        self._cargar_personas()

    def _cargar_personas(self):
        self.tabla_personas.delete(*self.tabla_personas.get_children())
        for i, p in enumerate(self.cfg.get("personas", [])):
            self.tabla_personas.insert("", "end", iid=str(i), values=(
                p["nombre"], ", ".join(p.get("alias", [])), ", ".join(p.get("rut", []))))
        self.combo_def["values"] = [""] + [p["nombre"] for p in self.cfg.get("personas", [])]

    def _persona_seleccionada(self, _ev):
        sel = self.tabla_personas.selection()
        if sel:
            p = self.cfg["personas"][int(sel[0])]
            self.p_nombre.set(p["nombre"])
            self.p_alias.set(", ".join(p.get("alias", [])))
            self.p_rut.set(", ".join(p.get("rut", [])))

    def _guardar_persona(self):
        nombre = self.p_nombre.get().strip()
        if not nombre:
            messagebox.showwarning(APP_NAME, "Escribe al menos el nombre.")
            return
        if any(c in nombre for c in '\\/:*?"<>|'):
            messagebox.showwarning(APP_NAME, 'El nombre no puede tener \\ / : * ? " < > |')
            return
        persona = {"nombre": nombre,
                   "alias": [a.strip() for a in self.p_alias.get().split(",") if a.strip()],
                   "rut": [r.strip() for r in self.p_rut.get().split(",") if r.strip()]}
        personas = self.cfg.setdefault("personas", [])
        for i, p in enumerate(personas):
            if p["nombre"].lower() == nombre.lower():
                personas[i] = persona
                break
        else:
            personas.append(persona)
        config.guardar(self.cfg)
        self._cargar_personas()
        for v in (self.p_nombre, self.p_alias, self.p_rut):
            v.set("")

    def _quitar_persona(self):
        sel = self.tabla_personas.selection()
        if sel:
            del self.cfg["personas"][int(sel[0])]
            config.guardar(self.cfg)
            self._cargar_personas()

    # ------------------------------------------------------------------ ajustes
    def _pestana_ajustes(self, nb):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text="  Ajustes  ")
        self.vars: dict[str, tk.Variable] = {}

        qf = ttk.LabelFrame(f, text="Qué revisar", padding=8)
        qf.pack(fill="x", pady=(0, 8))
        cuentas_extra = otras_cuentas()
        opciones = [
            ("revisar_escritorio", f"Escritorio  ({self.cu.escritorio or 'no encontrado'})"),
            ("revisar_descargas", f"Descargas  ({self.cu.descargas or 'no encontrado'})"),
            ("buscar_pdfs_en_perfil", "Buscar PDFs en todo mi perfil y llevarlos a Documentos "
                                      "(no toca proyectos, programas ni lo que ya está en Documentos)"),
            ("incluir_otras_cuentas", "Ordenar también otras cuentas de Windows de este PC "
                                      f"({', '.join(c.cuenta for c in cuentas_extra) or 'requiere abrir la app como administrador'})"),
            ("ordenar_carpetas", "Ordenar también las carpetas del Escritorio y Descargas "
                                 "(se mueven enteras; los SDK como flutter nunca se tocan)"),
            ("carpetas_en_auto", "En el modo automático, mover también carpetas (si no, solo desde esta ventana)"),
            ("mover_multimedia", "Llevar fotos, videos y música sin uso a sus bibliotecas (Imágenes, Videos, Música)"),
            ("subcarpeta_por_anio", "Separar documentos por año dentro de cada categoría"),
        ]
        for clave, texto in opciones:
            v = tk.BooleanVar(value=bool(self.cfg.get(clave)))
            self.vars[clave] = v
            ttk.Checkbutton(qf, text=texto, variable=v).pack(anchor="w", pady=1)

        nf = ttk.LabelFrame(f, text="Archivos no ocupados", padding=8)
        nf.pack(fill="x", pady=(0, 8))
        ttk.Label(nf, text="Considerar «no ocupado» un archivo sin abrir ni modificar en").pack(side="left")
        v = tk.IntVar(value=int(self.cfg["dias_inactivo"]))
        self.vars["dias_inactivo"] = v
        ttk.Spinbox(nf, from_=1, to=3650, textvariable=v, width=6).pack(side="left", padx=4)
        ttk.Label(nf, text="días → se mueven a «Archivados» (nunca se borran).").pack(side="left")

        af = ttk.LabelFrame(f, text="Ordenar automáticamente", padding=8)
        af.pack(fill="x", pady=(0, 8))
        self.frecuencia = tk.StringVar(value="DAILY")
        for val, txt in (("DAILY", "Cada día"), ("WEEKLY", "Cada semana"), ("ONLOGON", "Al iniciar sesión")):
            ttk.Radiobutton(af, text=txt, value=val, variable=self.frecuencia).pack(side="left", padx=4)
        ttk.Label(af, text="  Hora:").pack(side="left")
        self.hora = tk.StringVar(value="13:00")
        ttk.Entry(af, textvariable=self.hora, width=6).pack(side="left", padx=4)
        ttk.Button(af, text="Activar", command=self._programar).pack(side="left", padx=8)
        ttk.Button(af, text="Desactivar", command=self._desprogramar).pack(side="left")
        self.lbl_prog = ttk.Label(af, foreground="#555")
        self.lbl_prog.pack(side="left", padx=10)
        self._refrescar_programado()

        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=8)
        ttk.Button(bf, text="💾 Guardar ajustes", command=self._guardar_ajustes).pack(side="left")
        ttk.Button(bf, text="Editar categorías y palabras clave (config.json)",
                   command=lambda: _abrir_carpeta(config.ruta_config().parent)).pack(side="left", padx=8)

    def _guardar_ajustes(self, silencioso: bool = False):
        for clave, v in self.vars.items():
            try:
                self.cfg[clave] = v.get()
            except tk.TclError:
                pass
        if hasattr(self, "persona_def"):
            self.cfg["persona_por_defecto"] = self.persona_def.get().strip()
        config.guardar(self.cfg)
        if not silencioso:
            self.estado.set("Ajustes guardados.")

    def _programar(self):
        self._guardar_ajustes(silencioso=True)
        ok, msg = programar.programar(self.frecuencia.get(), self.hora.get().strip() or "13:00")
        (messagebox.showinfo if ok else messagebox.showerror)(APP_NAME, msg or "Listo")
        self._refrescar_programado()

    def _desprogramar(self):
        ok, msg = programar.quitar()
        (messagebox.showinfo if ok else messagebox.showerror)(APP_NAME, msg or "Listo")
        self._refrescar_programado()

    def _refrescar_programado(self):
        self.lbl_prog.configure(text="Estado: activado ✔" if programar.esta_programado() else "Estado: desactivado")

    # ------------------------------------------------------------------ historial
    def _pestana_historial(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="  Historial  ")
        ttk.Label(f, text="Cada vez que se ordena queda registrado aquí. Puedes deshacer cualquier ejecución.").pack(anchor="w")
        self.lista_hist = tk.Listbox(f, height=15, font=("Consolas", 10))
        self.lista_hist.pack(fill="both", expand=True, pady=6)
        bf = ttk.Frame(f)
        bf.pack(fill="x")
        ttk.Button(bf, text="↩ Deshacer seleccionada", command=self._deshacer_sel).pack(side="left")
        ttk.Button(bf, text="Abrir carpeta de historial",
                   command=lambda: _abrir_carpeta(motor.carpeta_historial())).pack(side="left", padx=6)
        self._cargar_historial()

    def _cargar_historial(self):
        self._hist = motor.historiales()
        self.lista_hist.delete(0, "end")
        for h in self._hist:
            try:
                n = sum(1 for linea in h.read_text(encoding="utf-8").splitlines() if linea.strip())
            except OSError:
                n = 0
            self.lista_hist.insert("end", f"{h.stem.replace('_', '  ')}    {n} archivos movidos")

    def _deshacer_sel(self):
        sel = self.lista_hist.curselection()
        if sel:
            self._deshacer(self._hist[sel[0]])


def iniciar():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # texto nítido en pantallas HD
        except Exception:
            pass
    App().mainloop()
