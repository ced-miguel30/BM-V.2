"""Textos marcadores de las dos carpetas sustituibles del hotel (BM-CODIGO / BM-DATOS)."""

from __future__ import annotations

BM_CODIGO_MARKER_NAME = "BM-CODIGO.txt"
BM_DATOS_MARKER_NAME = "BM-DATOS.txt"

BM_CODIGO_MARKER_TEXT = (
    "Carpeta de aplicacion (BM-CODIGO).\n"
    "\n"
    "Sustituir COMPLETA al actualizar la version (exe + _internal).\n"
    "No borrar ni mezclar con BM-DATOS.\n"
    "El acceso directo debe apuntar a BM-Launcher.exe dentro de esta carpeta.\n"
    "\n"
    "Ruta tipica: C:\\Apps\\BM-V2\\\n"
    "Datos productivos: ver BM-DATOS.txt en %%LOCALAPPDATA%%\\BM-V2-local\\\n"
)

BM_DATOS_MARKER_TEXT = (
    "Carpeta de datos del hotel (BM-DATOS).\n"
    "\n"
    "Sustituir COMPLETA al llevar/traer la base (casa <-> hotel).\n"
    "Incluye: data\\datos_hotel.json, data\\documentos\\, backups\\, exports\\, logs\\.\n"
    "No mezclar con una actualizacion de codigo.\n"
    "\n"
    "Ruta tipica (un PC / exe): %%LOCALAPPDATA%%\\BM-V2-local\\\n"
    "Variable: BM_INSTANCE_ROOT\n"
)
