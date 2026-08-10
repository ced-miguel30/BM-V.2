# Browser E2E (Playwright)

## Requisitos

```text
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

## Ejecución

```text
python run_browser_tests.py
```

No forma parte de ``python run_tests.py`` (suite canónica de dominio).

## Aislamiento

- ``BM_TEST_ISOLATION=1``
- ``BM_DEMO_FILE`` → JSON temporal (fixture ``tests/browser/fixtures_minimos.py``)
- Demo canónico no se modifica; ``assert_demo_intact()`` en cada test

## Cobertura actual

| Área | Estado |
|------|--------|
| Login OK / KO / logout | OK |
| Dirección / Admin / Restaurante | OK |
| Terminal Restaurante / Inventario | OK |
| Nav Stock / Recetas / Caducidad / Historial | OK |
| Persistencia JSON fixture + reload | OK |
| Confirmar Desayuno (cesta UI) | SKIP — selectores de confirmación no estabilizados (P2 automation) |
| Compra completa + adjunto | Parcial (navegación Stock/Compras) |
| Backup/restore UI | Pendiente (humano / siguiente iteración) |

## Artefactos

``tests/browser/_artifacts/`` (gitignored): logs Streamlit y screenshots en fallo.
