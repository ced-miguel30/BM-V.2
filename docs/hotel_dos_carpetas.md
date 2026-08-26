# Dos carpetas sustituibles — hotel (código + datos)

En el hotel solo hay que conocer **dos carpetas**. El acceso directo al `.exe` **no cambia** al actualizar versión o al traer/llevar la base.

| Marca | Ruta en ESTE PC | Qué es | Al actualizar |
|-------|-----------------|--------|---------------|
| **BM-CODIGO** (desarrollo) | `C:\Users\User\Desktop\HOTEL\BM V.2\` | Código fuente / Cursor | Editas aquí; empaquetas y despliegas |
| **BM-CODIGO** (exe hotel) | `C:\Apps\BM-V2\` | `BM-Launcher.exe` + `_internal\` | Sustituir **entera** por la nueva versión |
| **BM-DATOS** | `C:\Users\User\AppData\Local\BM-V2-local\` | Toda la base operativa | Sustituir/copiar **entera** (casa ↔ hotel); **nunca** mezclar con un update de código |

Resumen visible: `C:\Users\User\Desktop\HOTEL\LEEME_DOS_CARPETAS.txt`.

Marcadores en disco: `BM-CODIGO.txt` y `BM-DATOS.txt` (los crea el runtime del exe o `deploy\windows\marcar_carpetas_hotel.cmd`).

```
BM-CODIGO\BM-Launcher.exe  →  BM_INSTANCE_ROOT (= BM-DATOS)
                              └─ data\datos_hotel.json
                              ├─ data\documentos\
                              ├─ backups\
                              ├─ exports\
                              └─ logs\
```

## Checklist — actualizar versión (solo código)

1. Cerrar BM en todos los PCs.
2. Renombrar o borrar `C:\Apps\BM-V2` (opcional: dejar `BM-V2.bak`).
3. Copiar la nueva carpeta de build (`dist\BM-Launcher\` → `C:\Apps\BM-V2\`).
4. Abrir el **mismo** acceso directo → `C:\Apps\BM-V2\BM-Launcher.exe`.
5. Comprobar que siguen los datos de siempre (misma carpeta BM-DATOS).

**No** tocar `%LOCALAPPDATA%\BM-V2-local\` en este paso.

## Checklist — llevar / traer la base (solo datos)

1. Cerrar BM.
2. En el origen: ZIP o copia de la carpeta **BM-DATOS** completa (`%LOCALAPPDATA%\BM-V2-local\`).
3. En el destino: reemplazar esa carpeta entera (mismo nombre / misma ruta, o ajustar `BM_INSTANCE_ROOT`).
4. Abrir el mismo exe.

**No** copiar `datos_hotel.json` dentro de `_internal` ni del repo.

## Multi-PC

BM-DATOS puede ser una UNC compartida (`BM_INSTANCE_ROOT` / config de cliente). BM-CODIGO sigue siendo local en cada PC. Ver [`operations_multi_pc.md`](operations_multi_pc.md).

## Script de marcadores

```bat
deploy\windows\marcar_carpetas_hotel.cmd
deploy\windows\marcar_carpetas_hotel.cmd "C:\Apps\BM-V2" "%LOCALAPPDATA%\BM-V2-local"
```

## Variables

| Variable | Rol |
|----------|-----|
| `BM_INSTANCE_ROOT` | Raíz BM-DATOS |
| `BM_DEMO_FILE` | JSON efectivo (`…\data\datos_hotel.json`); el exe lo fija el runtime hook |

Default del exe (sin env previo): `%LOCALAPPDATA%\BM-V2-local` — **independiente** de la ruta de BM-CODIGO, para que sustituir el código no “pierda” los datos.
