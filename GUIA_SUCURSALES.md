# Sucursales: pedidos, entregas, tickets y vales

Actualizada el 4 de noviembre de 2026.

## Preparar una sucursal como administrador

1. Entra a **Sucursales** y crea una sucursal, o abre una existente.
2. En **Datos y comisión**, captura su porcentaje fijo de comisión. La comisión se calcula sobre el subtotal después de los descuentos. Las sucursales anteriores empiezan con 0 % para no inventar un porcentaje: revísalo antes de su primera entrega nueva.
3. En **Acceso de la sucursal**, elige un usuario, una contraseña inicial de al menos 10 caracteres y activa **Permitir acceso**.
4. Comparte esas credenciales con la persona. Ella entra por la misma pantalla de inicio de sesión y solo ve su información. Puede cambiar su contraseña desde el menú del usuario.

Para probar ambos lados en esta computadora, conserva el administrador en una ventana y abre la sucursal en una ventana privada. Por ahora la aplicación corre en localhost; el acceso desde otros equipos requiere configurar la red o el alojamiento.

## Hacer un pedido

La sucursal pulsa **Hacer pedido**, captura los artículos y puede mezclar varias zapaterías. El código es obligatorio; talla, color, descripción, notas y precio de referencia se capturan según corresponda.

- **Guardar borrador para después** conserva el pedido sin enviarlo a la lista de compras del administrador.
- **Enviar N artículos** lo manda al administrador y permite consultar el avance.
- Después de enviarlo ya no se modifica desde la cuenta de la sucursal. Si necesita cambiar algo, debe avisar al administrador.
- El precio de referencia no es el cobro definitivo. El precio y descuento reales se capturan al preparar la entrega.
- Cada renglón representa una unidad. Si se piden dos unidades iguales, agrega dos artículos.

El administrador también puede abrir una sucursal y pulsar **Hacer pedido** para capturar lo recibido por WhatsApp o en papel. Puede guardar sus propios borradores y enviarlos cuando estén listos.

## Comprar y recibir productos

En **Pedidos** hay filtros **Todos**, **Clientes del local** y **Sucursales**. Puedes filtrar por sucursal, tienda, estado o código.

Los artículos de sucursal avanzan así:

1. **Por comprar:** el pedido ya fue enviado.
2. **Marcar comprado:** ya se consiguió el producto.
3. **Ya llegó al local:** se recibió físicamente; queda **Recibido en local**.
4. **Preparar entrega:** se selecciona para entregarlo a la sucursal.
5. **Confirmar entrega y generar ticket:** queda **Entregado** y se registra el importe por cobrar.

Recibir un producto en el local todavía no genera deuda. Si faltan productos, permanecen pendientes: no es necesario esperar a que llegue todo para preparar una entrega parcial.

## Capturar precio y descuento, y generar el ticket

1. Abre la sucursal y marca los productos recibidos que vas a entregar. También puedes seleccionarlos en Pedidos después de filtrar una sucursal.
2. Pulsa **Preparar entrega de los seleccionados**.
3. Captura manualmente el **precio base del producto** y su **descuento (%)** en cada artículo. Usa 0 cuando no haya descuento.
4. La comisión se toma automáticamente de la configuración de esa sucursal.
5. Si hay vales, indica cuánto aplicar o pulsa **Usar los vales disponibles**. El sistema usa primero los más antiguos y conserva el sobrante.
6. Pulsa **Revisar entrega antes de confirmar**. Revisa productos, descuentos, comisión, vales, total y deuda anterior.
7. Confirma la entrega. El ticket se guarda para ambos usuarios y puede descargarse en PDF.

Ejemplo con comisión de 5 %:

| Concepto | Importe |
|---|---:|
| Precio base | $1,000.00 |
| Descuento de 30 % | −$300.00 |
| Importe neto del producto | $700.00 |
| Comisión de 5 % sobre el neto | $35.00 |
| Total de la entrega | $735.00 |

La comisión total se redondea a centavos sobre el subtotal neto. El ticket distribuye esos centavos entre los artículos para que el detalle sume exactamente el total.

Una preparación puede dejarse pendiente y continuarse después desde la ficha de la sucursal. **Cancelar preparación** libera los artículos para otra entrega y no genera cargos.

Un ticket confirmado conserva sus precios, descuentos y comisión; cambiar la configuración de la sucursal no altera su historial. Si otra persona cambia una preparación mientras la estás revisando, debes volver a revisarla antes de confirmar.

## Registrar pagos

El administrador puede registrar un pago dentro de un ticket específico. La sucursal ve cuánto se pagó y cuánto falta.

En la pestaña **Pagos** también hay un registro general. Se aplica primero a los tickets pendientes más antiguos y el sobrante a la deuda anterior. Si se distribuye entre varios tickets, el historial muestra la parte correspondiente a cada uno.

Solo el administrador puede anular pagos. La anulación restaura la deuda y conserva la constancia del movimiento.

## Devolver un producto y generar un vale

1. La sucursal abre un ticket y pulsa **Solicitar devolución** en el artículo. También está disponible desde su lista de pedidos entregados.
2. Escribe el motivo y envía la solicitud.
3. El administrador entra a **Sucursales → Devoluciones por revisar**.
4. Cuando recibe y acepta el producto, pulsa **Ya recibí el producto: generar vale**. Si no procede, puede rechazarlo explicando el motivo.

El vale es por el **importe neto del producto después del descuento, sin comisión**. En el ejemplo anterior sería de $700, aunque la entrega haya costado $735.

Solicitar la devolución no genera todavía un vale. La confirmación del administrador lo genera una sola vez y marca el artículo como devuelto.

La devolución conserva el ticket original y su deuda; el vale se descuenta en una **próxima entrega**. No se resta además del ticket original, porque eso descontaría el mismo importe dos veces. Esto también aplica si aún había pagos pendientes del ticket anterior.

## Usar y consultar los vales

La pestaña **Vales** muestra el folio, producto de origen, importe original, saldo disponible y tickets en los que se utilizó.

Ejemplo: si una nueva entrega suma $10,000 entre productos y comisión y se aplican $2,000 de vales, el nuevo ticket queda en $8,000. La deuda de tickets anteriores se muestra aparte.

- Se puede aplicar solo una parte del vale y conservar el resto.
- Nunca se aplica más de lo disponible ni más del total de la entrega.
- Preparar una entrega no consume el vale: se descuenta al confirmar el ticket.
- Dos entregas no pueden gastar el mismo saldo simultáneamente.
- Los vales son de la sucursal que devolvió el producto y no se transfieren a otra.

## Historial anterior

Los clientes, productos, saldos y pagos registrados antes de esta actualización se conservan. Los artículos antiguos siguen en la lista de la sucursal y los nuevos tickets se generan a partir de las nuevas entregas; no se inventaron tickets para operaciones anteriores.

Si una sucursal está desactivada, usa **Incluir desactivadas** para encontrarla y **Reactivar sucursal** desde su ficha. La desactivación conserva el historial y bloquea el acceso de esa persona.
