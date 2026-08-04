# Breakfast Management

Aplicación local para gestionar el desayuno de un hotel boutique.

## Requisitos

- Python 3.10 o superior
- pip

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

Desde la raíz del proyecto:

```bash
streamlit run app/main.py
```

La aplicación se abrirá en el navegador (por defecto en `http://localhost:8501`).

## Estado actual

**Pre-Fase 14** — Adaptaciones: autocompletado en tiempo real, Excel formateado con tablas, huéspedes en desayuno e historial de compras semanal.

## Estructura de carpetas

```
app/
  main.py           # Punto de entrada
  pages/            # Pantallas de la aplicación
  ui/               # Tema, estilos y componentes reutilizables
  core/             # Modelos, servicios y persistencia (fases futuras)
  data/             # Datos mock (mock_data.py)
exports/            # Archivos exportados
logs/               # Registros de actividad
```

## Tests

Ver [docs/testing.md](docs/testing.md). Comando canónico:

```text
python run_tests.py
```
