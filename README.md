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

**Fase 5** — Alertas de stock automáticas y manuales. Inventario por producto; historial de compras por lote en Stock.

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

## Actualización

Para actualizar en otro ordenador, copie la carpeta del proyecto y vuelva a ejecutar `pip install -r requirements.txt`.
