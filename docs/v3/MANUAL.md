# Manual de uso de BM

## Restaurante y recepción

| Qué | Dónde | Cuándo |
|-----|-------|--------|
| Desayuno, bebidas, buffet, comida o cena | **Importar Excel** (la plantilla de siempre) o **Registrar consumo** | Cada día |
| Algo que se tira | **Registrar consumo** → Merma (con motivo) | Al momento |
| Producto que caduca pronto | **Caducidades** → al final, *Usado* o *Tirar* (pasa a merma solo) | Al abrirlo / recibirlo |
| Contar un almacén | **Recuento** (móvil o tablet): elegir ubicación y escribir lo que hay | Cuando lo pida Dirección |
| Ventas del TPV | **Ventas TPV** → Subir PDF (uno o varios días; repetir un día no duplica) | Cada día |

El personal operativo no ve costes. Lo contado en un recuento pasa a ser el stock real.

## Administración

- **Semanal:** BC → *Movimientos de producto* → Abrir en Excel → **Importar de BC**. Actualiza precios y
  recalcula todos los costes (también los de días pasados).
- **Tras el inventario de fin de mes en BC:** importar movimientos otra vez; revisar **Control de stock**.
- **Precios de compra → Precios a revisar en BC:** errores de unidad o importe en facturas. BM no los usa
  mientras tanto; corregirlos en BC y reimportar.
- **Ventas TPV → Pendientes:** asignar cada artículo nuevo a su receta o producto (una vez).
- **Recetas:** mantener las fichas completas; un food cost muy bajo suele ser una ficha incompleta.

## Dirección

- **Panel:** coste por servicio, food cost del TPV (sin IGIC) frente al objetivo, tendencia de 12 meses y avisos.
- **Rentabilidad por plato:** estrellas, caballos de batalla, enigmas y perros, con la acción recomendada.
- **Control de stock:** lo que salió sin registrarse, por producto, ubicación y mes.
- **Configuración:** usuarios, objetivo de food cost, IGIC, centros de consumo, ubicaciones,
  atajos del Excel, recetas del día, copias de seguridad y registro de actividad.

## Cómo se calcula el coste

1. Cada compra de BC es un lote con su precio real.
2. Los consumos registrados gastan los lotes por orden de entrada (FIFO).
3. Cada inventario (de BC o recuento de BM) fija el stock real; la diferencia queda en Control de stock.
4. Albaranes aún sin facturar o precios disparatados se valoran con el último precio fiable (*Provisional*).

En **Consumos**, cada línea muestra de qué albarán sale su coste.
