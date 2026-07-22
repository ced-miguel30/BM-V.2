"""Repositorio de lectura sobre datos en memoria."""

from datetime import date, time

from app.core.models import (
    AlertaOperativa,
    AppData,
    MotivoMerma,
    Producto,
    Receta,
    RegistroDesayuno,
    RegistroMerma,
    TipoAlerta,
    Usuario,
)
from app.core.services.formatting import formato_moneda


class DataRepository:
    """Acceso centralizado a los datos mock/temporales."""

    def __init__(self, data: AppData) -> None:
        self._data = data

    @property
    def data(self) -> AppData:
        return self._data

    def get_usuario_actual(self) -> Usuario | None:
        for usuario in self._data.usuarios:
            if usuario.id == self._data.usuario_actual_id:
                return usuario
        return self._data.usuarios[0] if self._data.usuarios else None

    def get_producto(self, producto_id: str) -> Producto | None:
        return next((p for p in self._data.productos if p.id == producto_id), None)

    def get_receta(self, receta_id: str) -> Receta | None:
        return next((r for r in self._data.recetas if r.id == receta_id), None)

    def recetas_ordenadas(self) -> list[Receta]:
        return sorted(self._data.recetas, key=lambda r: r.nombre.lower())

    def get_nombre_producto(self, producto_id: str) -> str:
        producto = self.get_producto(producto_id)
        return producto.nombre if producto else "Desconocido"

    def get_simbolo_moneda(self) -> str:
        if self._data.configuracion:
            return self._data.configuracion.simbolo_moneda
        return "€"

    def formato_precio(self, valor: float) -> str:
        return formato_moneda(valor, self.get_simbolo_moneda())

    def stock_total_producto(self, producto_id: str) -> float:
        return sum(l.cantidad_restante for l in self._data.lotes if l.producto_id == producto_id)

    def alertas_activas(self) -> list[AlertaOperativa]:
        return [a for a in self._data.alertas if a.activa]

    def alertas_por_tipo(self, tipo: TipoAlerta) -> list[AlertaOperativa]:
        return [a for a in self.alertas_activas() if a.tipo == tipo]

    def desayuno_registrado_hoy(self) -> bool:
        hoy = date.today()
        return any(d.fecha == hoy for d in self._data.desayunos)

    def coste_consumo_mes(self) -> float:
        hoy = date.today()
        inicio = hoy.replace(day=1)
        return sum(
            d.coste_total for d in self._data.desayunos if inicio <= d.fecha <= hoy
        )

    def coste_merma_mes(self) -> float:
        hoy = date.today()
        inicio = hoy.replace(day=1)
        return sum(
            m.coste_total for m in self._data.mermas if inicio <= m.fecha <= hoy
        )

    def coste_expiracion_mes(self) -> float:
        hoy = date.today()
        inicio = hoy.replace(day=1)
        total = 0.0
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= hoy:
                for linea in merma.lineas:
                    if linea.motivo == MotivoMerma.EXPIRACION:
                        total += linea.coste
        return total

    def coste_total_mes(self) -> float:
        return self.coste_consumo_mes() + self.coste_merma_mes() + self.coste_expiracion_mes()

    def _periodo_mes_actual(self) -> tuple[date, date]:
        hoy = date.today()
        return hoy.replace(day=1), hoy

    def coste_consumo_periodo(self, inicio: date, fin: date) -> float:
        return sum(
            d.coste_total for d in self._data.desayunos if inicio <= d.fecha <= fin
        )

    def coste_merma_periodo(self, inicio: date, fin: date) -> float:
        total = 0.0
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                for linea in merma.lineas:
                    if linea.motivo != MotivoMerma.EXPIRACION:
                        total += linea.coste
        return total

    def coste_expiracion_periodo(self, inicio: date, fin: date) -> float:
        total = 0.0
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                for linea in merma.lineas:
                    if linea.motivo == MotivoMerma.EXPIRACION:
                        total += linea.coste
        return total

    def coste_total_periodo(self, inicio: date, fin: date) -> float:
        return (
            self.coste_consumo_periodo(inicio, fin)
            + self.coste_merma_periodo(inicio, fin)
            + self.coste_expiracion_periodo(inicio, fin)
        )

    def registros_expiracion_periodo(self, inicio: date, fin: date) -> int:
        n = 0
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                n += sum(1 for l in merma.lineas if l.motivo == MotivoMerma.EXPIRACION)
        return n

    def evolucion_diaria(self, inicio: date, fin: date) -> list[dict]:
        from datetime import timedelta

        if inicio > fin:
            inicio, fin = fin, inicio

        datos: dict[date, dict] = {}
        cursor = inicio
        while cursor <= fin:
            datos[cursor] = {
                "fecha": cursor,
                "consumo": 0.0,
                "merma": 0.0,
                "expiracion": 0.0,
            }
            cursor += timedelta(days=1)

        for desayuno in self._data.desayunos:
            if inicio <= desayuno.fecha <= fin:
                datos[desayuno.fecha]["consumo"] += desayuno.coste_total

        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                exp = sum(l.coste for l in merma.lineas if l.motivo == MotivoMerma.EXPIRACION)
                datos[merma.fecha]["expiracion"] += exp
                datos[merma.fecha]["merma"] += merma.coste_total - exp

        return [
            {
                **datos[d],
                "total": datos[d]["consumo"] + datos[d]["merma"] + datos[d]["expiracion"],
            }
            for d in sorted(datos.keys())
        ]

    def top_productos_costosos_periodo(
        self, inicio: date, fin: date, n: int = 5,
    ) -> list[dict]:
        costes: dict[str, float] = {}
        for desayuno in self._data.desayunos:
            if inicio <= desayuno.fecha <= fin:
                for linea in desayuno.lineas:
                    costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                for linea in merma.lineas:
                    costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        ordenado = sorted(costes.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "producto": self.get_nombre_producto(pid),
                "coste": coste,
                "coste_fmt": self.formato_precio(coste),
            }
            for pid, coste in ordenado[:n]
        ]

    def top_productos_menos_costosos_periodo(
        self, inicio: date, fin: date, n: int = 5,
    ) -> list[dict]:
        costes: dict[str, float] = {}
        for desayuno in self._data.desayunos:
            if inicio <= desayuno.fecha <= fin:
                for linea in desayuno.lineas:
                    costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        for merma in self._data.mermas:
            if inicio <= merma.fecha <= fin:
                for linea in merma.lineas:
                    costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        if not costes:
            return []
        ordenado = sorted(costes.items(), key=lambda x: x[1])
        return [
            {
                "producto": self.get_nombre_producto(pid),
                "coste": coste,
                "coste_fmt": self.formato_precio(coste),
            }
            for pid, coste in ordenado[:n]
        ]

    def productos_stock_bajo(self) -> list[tuple[Producto, float]]:
        resultado = []
        for producto in self._data.productos:
            if producto.stock_minimo is None:
                continue
            stock = self.stock_total_producto(producto.id)
            if 0 < stock <= producto.stock_minimo:
                resultado.append((producto, stock))
        return resultado

    def productos_stock_negativo(self) -> list[tuple[Producto, float]]:
        resultado = []
        for producto in self._data.productos:
            stock = self.stock_total_producto(producto.id)
            if stock < 0:
                resultado.append((producto, stock))
        return resultado

    def productos_stock_cero(self) -> list[Producto]:
        return [
            p for p in self._data.productos if self.stock_total_producto(p.id) == 0
        ]

    def lotes_proximos_expirar(self, dias: int = 5) -> list[dict]:
        hoy = date.today()
        resultado = []
        for lote in self._data.lotes:
            if lote.fecha_expiracion and lote.cantidad_restante > 0:
                dias_restantes = (lote.fecha_expiracion - hoy).days
                if 0 <= dias_restantes <= dias:
                    resultado.append({
                        "lote": lote,
                        "producto": self.get_nombre_producto(lote.producto_id),
                        "dias": dias_restantes,
                    })
        return resultado

    def desayunos_ordenados(self) -> list[RegistroDesayuno]:
        return sorted(
            self._data.desayunos,
            key=lambda d: (d.fecha, d.hora or time.min),
            reverse=True,
        )

    def mermas_ordenadas(self) -> list[RegistroMerma]:
        return sorted(
            self._data.mermas,
            key=lambda m: (m.fecha, m.hora or time.min),
            reverse=True,
        )

    def consumo_por_producto(self) -> list[dict]:
        totales: dict[str, float] = {}
        for desayuno in self._data.desayunos:
            for linea in desayuno.lineas:
                totales[linea.producto_id] = totales.get(linea.producto_id, 0) + linea.cantidad
        resultado = []
        for pid, cantidad in sorted(totales.items(), key=lambda x: x[1], reverse=True):
            resultado.append({
                "producto": self.get_nombre_producto(pid),
                "cantidad": cantidad,
            })
        return resultado

    def top_productos_costosos(self, n: int = 5) -> list[dict]:
        costes: dict[str, float] = {}
        for desayuno in self._data.desayunos:
            for linea in desayuno.lineas:
                costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        for merma in self._data.mermas:
            for linea in merma.lineas:
                costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste
        ordenado = sorted(costes.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "producto": self.get_nombre_producto(pid),
                "coste": coste,
                "coste_fmt": self.formato_precio(coste),
            }
            for pid, coste in ordenado[:n]
        ]

    def top_productos_menos_costosos(self, n: int = 5) -> list[dict]:
        todos = self.top_productos_costosos(n=len(self._data.productos) + 10)
        return list(reversed(todos[-n:])) if todos else []
