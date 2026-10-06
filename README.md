# BM · Royal Marina — Control F&B e inventario

Aplicación web del hotel para **consumo, inventario, stock y coste** del restaurante y de los
departamentos. Business Central (BC) sigue siendo contabilidad y compras: BM importa de BC y nunca
se registra el mismo hecho dos veces.

- Un PC del hotel hace de **servidor**; los demás PCs, tablets y móviles entran por navegador.
- Datos en un único fichero SQLite, con copia de seguridad automática diaria.
- Costes **FIFO con precios reales de compra de BC**, anclados a cada inventario; cada línea de coste
  se puede rastrear hasta su albarán.

## Puesta en marcha en el servidor

```powershell
powershell -ExecutionPolicy Bypass -File instalar\instalar.ps1
```

Ver [docs/v3/INSTALACION.md](docs/v3/INSTALACION.md). Manual de uso por perfiles:
[docs/v3/MANUAL.md](docs/v3/MANUAL.md). Hoja de ruta: [docs/v3/HOJA_DE_RUTA.md](docs/v3/HOJA_DE_RUTA.md).

## Desarrollo

| Parte | Dónde | Comando |
|-------|-------|---------|
| Servidor (FastAPI + SQLite) | `bm/` | `python -m bm.servidor` |
| Interfaz (React + Mantine) | `web/` | `npm run dev` (proxy a :8000) · `npm run build` → `bm/static` |
| Tests | `bm/tests/` | `python -m unittest discover -s bm/tests -t .` |
| Carga inicial (BC + BM v2) | `bm/importar.py` | `python -m bm.importar --help` |

El build de la interfaz (`bm/static`) se versiona: el servidor del hotel solo necesita Python.
La versión anterior (v2, Flet/Streamlit) sigue en la rama `main`.
