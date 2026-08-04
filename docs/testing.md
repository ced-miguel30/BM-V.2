# Ejecución de tests (Fase A1 — cierre)

## Arquitectura de aislamiento

1. **Principal:** cada test que persiste usa `TemporaryDirectory`,
   `isolated_persist`, `InMemoryUnitOfWork` o `patch` local (restaurado al salir).
2. **Red de seguridad:** `BM_TEST_ISOLATION=1` hace que `save_json` /
   `delete_demo_files` rechacen la ruta canónica resuelta de
   `data/demo/datos_hotel.json`. No neutraliza la persistencia: falla en
   intento de escritura real.
3. **`tests/__init__.py`:** solo activa la variable de entorno al importar el
   paquete `tests`. No monkeypatchea funciones.

## Suite canónica

```text
python run_tests.py
```

`run_tests.py` establece `BM_TEST_ISOLATION=1` e importa el paquete `tests`.

Equivalente:

```text
$env:BM_TEST_ISOLATION="1"   # PowerShell
python -m unittest discover -s tests -t . -v
```

```text
python -m unittest discover -s tests -v
```

Sin `-t .` el paquete `tests` puede no cargarse: conviene exportar
`BM_TEST_ISOLATION=1` manualmente o usar `run_tests.py`.

## Pytest (opcional)

```text
$env:BM_TEST_ISOLATION="1"
python -m pytest tests -q
```

Si pytest importa `tests` como paquete, la env se activa vía `__init__.py`.
