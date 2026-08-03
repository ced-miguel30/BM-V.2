"""Fase 4H — exportación semanal vía AppContext.

Ejecutar:

    py -m unittest tests.test_fase4h_exportacion -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import AppData, Usuario, RolUsuario
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import (
    ConfiguracionExportacionModulo,
    exportar_periodo,
)


class TestFase4HExportacion(unittest.TestCase):
    def test_exportar_registra_actividad_via_contexto(self) -> None:
        data = AppData(
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
        )
        ctx = build_app_context(
            uow=InMemoryUnitOfWork(data),
            clock=FixedClock(datetime(2026, 7, 30, 16, 45, 0)),
            actor=Actor(id="u01", nombre="Ana", rol="Admin"),
        )

        def _regs(inicio: date, hasta: datetime):
            return [
                RegistroExportable(
                    fecha=date(2026, 7, 28),
                    hora=None,
                    tipo="Test",
                    identificador="t1",
                    usuario="Ana",
                    columnas=["A"],
                    filas=[["x"]],
                    resumen=[],
                ),
            ]

        config = ConfiguracionExportacionModulo(
            tipo="fase4h_test",
            titulo_documento="Prueba 4H",
            obtener_registros=_regs,
        )
        with tempfile.TemporaryDirectory() as tmp:
            resultado = exportar_periodo(
                config,
                date(2026, 7, 27),
                datetime(2026, 7, 30, 16, 45, 0),
                automatica=False,
                fecha_exportacion=date(2026, 7, 30),
                carpeta_exports=Path(tmp),
                ctx=ctx,
            )
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(len(data.actividades), 1)
        act = data.actividades[0]
        self.assertEqual(act.accion, "Exportación")
        self.assertEqual(act.usuario, "Ana")
        self.assertEqual(act.modulo, "fase4h_test")
        self.assertEqual(act.resultado, "Correcto")
        self.assertEqual(act.tipo_exportacion, "Manual")
        self.assertEqual(act.fecha_hora, datetime(2026, 7, 30, 16, 45, 0))


if __name__ == "__main__":
    unittest.main()
