"""Business Intelligence — respuestas basadas en reglas."""

from datetime import date, timedelta

from app.core.models import MotivoMerma, TipoAlerta
from app.core.services.data_service import get_repository


PREGUNTAS_SUGERIDAS = [
    ("anomalia", "¿Hay alguna anomalía de costes?"),
    ("mas_caro", "¿Qué es lo más caro de este mes?"),
    ("mas_merma", "¿Qué producto ha generado más merma?"),
    ("subiendo_coste", "¿Qué productos están subiendo de coste?"),
    ("revisar_semana", "¿Qué debería revisar esta semana?"),
]


def resumen_automatico() -> str:
    repo = get_repository()
    hoy = date.today()
    inicio = hoy.replace(day=1)

    total = repo.formato_precio(repo.coste_total_mes())
    top = repo.top_productos_costosos_periodo(inicio, hoy, 1)
    alertas = len(repo.alertas_activas())
    stock_bajo = len(repo.productos_stock_bajo())

    if top:
        producto_top = f"**{top[0]['producto']}** ({top[0]['coste_fmt']})"
    else:
        producto_top = "sin datos suficientes"

    return (
        f"Coste total del mes: **{total}**. "
        f"Producto más costoso: {producto_top}. "
        f"Alertas activas: **{alertas}**. "
        f"Productos con stock bajo: **{stock_bajo}**."
    )


def _merma_por_producto_mes() -> list[dict]:
    repo = get_repository()
    hoy = date.today()
    inicio = hoy.replace(day=1)
    costes: dict[str, float] = {}

    for merma in repo.data.mermas:
        if inicio <= merma.fecha <= hoy:
            for linea in merma.lineas:
                if linea.motivo != MotivoMerma.EXPIRACION:
                    costes[linea.producto_id] = costes.get(linea.producto_id, 0) + linea.coste

    return sorted(
        [
            {
                "producto": repo.get_nombre_producto(pid),
                "coste": coste,
                "coste_fmt": repo.formato_precio(coste),
            }
            for pid, coste in costes.items()
        ],
        key=lambda x: x["coste"],
        reverse=True,
    )


def responder_pregunta(pregunta_id: str) -> str:
    repo = get_repository()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    hace_7 = hoy - timedelta(days=7)
    hace_14 = hoy - timedelta(days=14)

    if pregunta_id == "anomalia":
        consumo = repo.coste_consumo_mes()
        merma = repo.coste_merma_mes()
        expiracion = repo.coste_expiracion_mes()
        total = consumo + merma + expiracion
        partes = []

        if total > 0 and merma / total > 0.25:
            partes.append(
                f"La merma representa el **{(merma / total) * 100:.0f}%** del coste total "
                f"({repo.formato_precio(merma)}), por encima del umbral habitual (~25%)."
            )
        if expiracion > merma and expiracion > 0:
            partes.append(
                f"La expiración ({repo.formato_precio(expiracion)}) supera la merma operativa "
                f"({repo.formato_precio(merma)}). Revise rotación y fechas de compra."
            )
        alertas_merma = [a for a in repo.alertas_activas() if a.tipo == TipoAlerta.MERMA_ELEVADA]
        if alertas_merma:
            partes.append(f"Alerta activa: **{alertas_merma[0].titulo}** — {alertas_merma[0].mensaje}")

        if not partes:
            return (
                f"No se detectan anomalías relevantes este mes. "
                f"Coste total: **{repo.formato_precio(total)}** "
                f"(consumo {repo.formato_precio(consumo)}, merma {repo.formato_precio(merma)}, "
                f"expiración {repo.formato_precio(expiracion)})."
            )
        return " ".join(partes)

    if pregunta_id == "mas_caro":
        top = repo.top_productos_costosos_periodo(inicio_mes, hoy, 3)
        if not top:
            return "No hay datos de costes por producto en el mes actual."
        lineas = [f"**{t['producto']}** — {t['coste_fmt']}" for t in top]
        return f"Los productos más costosos del mes son: {', '.join(lineas)}."

    if pregunta_id == "mas_merma":
        ranking = _merma_por_producto_mes()
        if not ranking:
            return "No hay registros de merma (excl. expiración) en el mes actual."
        lider = ranking[0]
        detalle = ", ".join(f"**{r['producto']}** ({r['coste_fmt']})" for r in ranking[:3])
        return f"El producto con más merma es **{lider['producto']}** ({lider['coste_fmt']}). Top 3: {detalle}."

    if pregunta_id == "subiendo_coste":
        reciente = repo.coste_total_periodo(hace_7, hoy)
        anterior = repo.coste_total_periodo(hace_14, hoy - timedelta(days=8))
        partes = []
        if anterior > 0:
            cambio = ((reciente - anterior) / anterior) * 100
            partes.append(
                f"El coste total de los últimos 7 días ({repo.formato_precio(reciente)}) "
                f"varía **{cambio:+.0f}%** respecto a la semana anterior ({repo.formato_precio(anterior)})."
            )
        top = repo.top_productos_costosos_periodo(hace_7, hoy, 3)
        if top:
            nombres = ", ".join(f"**{t['producto']}**" for t in top)
            partes.append(f"Mayor impacto reciente en: {nombres}.")
        return " ".join(partes) if partes else "No hay suficientes datos para comparar tendencias."

    if pregunta_id == "revisar_semana":
        puntos = []
        if not repo.desayuno_registrado_hoy():
            puntos.append("Registrar el **desayuno de hoy**.")
        for producto, stock in repo.productos_stock_bajo()[:3]:
            puntos.append(f"Reponer **{producto.nombre}** (stock: {stock:g} {producto.unidad.value}).")
        for producto in repo.productos_stock_cero()[:2]:
            puntos.append(f"Producto **agotado**: {producto.nombre}.")
        proximos = repo.lotes_proximos_expirar(5)
        for item in proximos[:3]:
            puntos.append(
                f"**{item['producto']}** expira en {item['dias']} día(s) "
                f"({item['lote'].fecha_expiracion.strftime('%d/%m/%Y') if item['lote'].fecha_expiracion else '—'})."
            )
        alertas = [a for a in repo.alertas_activas() if a.tipo == TipoAlerta.MANUAL][:2]
        for alerta in alertas:
            puntos.append(f"Alerta manual: **{alerta.titulo}**.")

        if not puntos:
            return "No hay puntos críticos esta semana. Operación dentro de parámetros normales."
        return "Prioridades:\n\n" + "\n".join(f"- {p}" for p in puntos)

    return "No reconozco la pregunta. Use una de las preguntas sugeridas."


def buscar_pregunta(texto: str) -> str | None:
    texto_norm = texto.strip().lower()
    for pid, pregunta in PREGUNTAS_SUGERIDAS:
        if texto_norm in pregunta.lower() or pregunta.lower() in texto_norm:
            return pid
    palabras_clave = {
        "anomalía": "anomalia",
        "anomalia": "anomalia",
        "caro": "mas_caro",
        "merma": "mas_merma",
        "subiendo": "subiendo_coste",
        "revisar": "revisar_semana",
        "semana": "revisar_semana",
    }
    for palabra, pid in palabras_clave.items():
        if palabra in texto_norm:
            return pid
    return None
