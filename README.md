# Organizador Optimus

App de escritorio para Windows que ordena tu PC: deja limpios el **Escritorio** y **Descargas**, guarda los **PDF y documentos** en Documentos según **de qué tratan** y **de quién son**, y archiva lo que ya no usas. Gratis y de código abierto.

![icono](assets/icono.png)

## Qué hace

| Archivo | Qué pasa |
|---|---|
| PDF, Word, Excel, PowerPoint, TXT… | Lee el contenido y lo guarda en `Documentos\Organizador Optimus\<Persona>\<Categoría>\<Año>` |
| Libros (epub, mobi…) | `Documentos\Organizador Optimus\Libros` |
| Fotos, videos, música sin uso | A tus bibliotecas `Imágenes`, `Videos`, `Música` (subcarpeta `Organizador Optimus\<Año>`) |
| Zip ya descomprimido al lado | Se archiva |
| Cualquier otra cosa sin usar hace X días | `Archivados` (lo de Descargas se queda dentro de Descargas para no llenar OneDrive) |
| Accesos directos (`.lnk`, `.url`), descargas a medias, archivos ocultos o recién modificados | **Nunca se tocan** |
| Carpetas de estudios, trabajo, documentos | Se mueven **enteras** a su categoría (`Universidad` → Estudios) |
| Carpetas de fotos / videos / música | A su biblioteca de Windows |
| Proyectos de código y carpetas de programas | Se proponen **desmarcados**: tú decides |
| SDKs instalados (flutter, jdk, node, python…) | **Nunca se tocan** (moverlos rompe el PATH) |

**Categorías** (pensadas para Chile): Facturas y Boletas, Bancos y Finanzas, Trabajo, Curriculum, Estudios, Identidad y Personales, Salud, Hogar y Servicios, Vehículo, Legal, Manuales y Guías, Libros, Otros. Se pueden editar en `%APPDATA%\OrganizadorOptimus\config.json`.

### Varias personas en el PC
- **Cada uno con su cuenta de Windows**: cada cuenta se ordena en sus propias carpetas. Para ordenar todas desde una sola sesión, activa *Ajustes → Ordenar también otras cuentas* y abre la app como administrador.
- **Una cuenta compartida**: en la pestaña *Personas* agrega a cada uno con su nombre, alias y RUT. Si un documento los menciona, va a su carpeta (`...\Organizador Optimus\Maria\Salud\2026`).

### Seguro por diseño
- **Nunca borra nada**: solo mueve.
- **Vista previa**: primero muestra qué hará; tú marcas o desmarcas cada archivo.
- **Deshacer**: cada ejecución queda en el historial y se puede revertir completa.
- Si ya existe un archivo con el mismo nombre se renombra (`nombre (2).pdf`); si es una copia idéntica va a `Archivados\Duplicados`.
- Detecta las carpetas reales de Windows aunque estén en OneDrive (`OneDrive\Escritorio`, `OneDrive\Documentos`).
- Funciona sin internet; tus documentos no salen del PC.

## Uso

1. Descarga `OrganizadorOptimus.exe` desde [Releases](../../releases) (o compílalo, ver abajo).
2. Ábrelo → **Analizar** → revisa la lista → **Ordenar marcados**.
3. Opcional: en *Ajustes → Ordenar automáticamente* elige cada día / semana / al iniciar sesión.

Desde la terminal:

```
OrganizadorOptimus.exe --simular    # muestra el plan sin mover nada
OrganizadorOptimus.exe --auto       # ordena sin preguntar
OrganizadorOptimus.exe --deshacer   # deshace la última ejecución
```

## Compilar el .exe

Requisitos: Windows 10/11 y [Python 3.10+](https://www.python.org/downloads/) (marca *Add python.exe to PATH* al instalar).

```
build.bat
```

Crea `dist\OrganizadorOptimus.exe`. Para probar sin compilar: `iniciar.bat`.

## Estructura

```
organizador_optimus/
  carpetas.py      Carpetas reales de Windows (Known Folders, OneDrive) y otras cuentas
  config.py        Ajustes, categorías y palabras clave
  extractor.py     Texto de PDF, docx, xlsx, pptx, odt, txt
  clasificador.py  Categoría por palabras clave + detección de persona (nombre/alias/RUT)
  planificador.py  Decide qué mover y a dónde (sin mover nada)
  motor.py         Mueve, guarda historial y deshace
  programar.py     Tarea programada de Windows
  gui.py           Ventana (Tkinter)
tests/             Pruebas (pytest)
```

## Ideas para próximas versiones
- Clasificación con IA local (Ollama) como opción.
- OCR para PDFs escaneados (hoy se clasifican por nombre de archivo).
- Icono en la bandeja del sistema.

## Licencia
MIT
