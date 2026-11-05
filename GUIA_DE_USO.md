# Guía de uso y estado actual

Actualizada el 4 de noviembre de 2026. Incluye pedidos múltiples y el nuevo flujo de sucursales.

Esta aplicación administra pedidos de calzado por catálogo y la deuda de cada cliente. El flujo principal es registrar al cliente, tomar su pedido, comprar el producto, entregarlo y registrar sus pagos.

## 1. Entrar

Con el servidor encendido, abre http://localhost:5000.

En la instalación local inicial:

- Usuario: `admin`
- Contraseña: `admin123`

La base local se preparó con siete zapaterías: Supershoes, Golden Shoes, Pakar, Andrea, Cklass, Price Shoes y BL Shoes. Los clientes y pedidos se registran desde la aplicación.

## 2. Qué está disponible

| Módulo | Qué puedes hacer | Estado de la revisión |
|---|---|---|
| Inicio / Dashboard | Ver cobros, ventas, deuda, pedidos por comprar/listos para entregar y alertas | Incluye cobros, deuda y ventas de clientes y sucursales |
| Clientes | Registrar, buscar, editar, consultar saldo e historial, agregar cargos y desactivar | Alta, consulta, cargos y anulaciones cubiertos por pruebas |
| Pedidos | Registrar, marcar comprado y entregado, consultar y buscar por código | Flujo básico comprobado con datos temporales |
| Abonos | Registrar pagos y consultar historial | Pago parcial y bloqueo de exceso comprobados |
| Sucursales | Acceso propio, borradores, pedidos, entregas, tickets/PDF, pagos, devoluciones y vales | Flujo completo comprobado con datos temporales |
| Reportes | Descargar resumen general y abonos por periodo | Generación de PDF comprobada |
| Zapaterías | Agregar y activar/desactivar catálogos como administrador | Pantalla comprobada; acciones presentes en el código |

Pasaron 48 pruebas automatizadas del servidor y dos recorridos en navegador con tamaño de celular, usando bases aisladas. Cubren pedidos, saldos, comisiones, vales, permisos, fechas, migraciones y operaciones simultáneas. Falta verificar PostgreSQL antes de producción y probarlo en un iPhone real.

## 3. Registrar un cliente

1. Entra a **Clientes** y abre el formulario de nuevo cliente.
2. Captura el nombre. Teléfono y dirección/referencia son opcionales.
3. Deja **Saldo inicial** en cero si empieza sin deuda. Si ya te debía dinero antes de usar el sistema, captura esa deuda aquí.
4. Guarda y revisa su ficha.

La ficha reúne saldo pendiente, datos del cliente, abonos, cargos manuales y pedidos. Puedes editar sus datos o iniciar un pedido o abono desde ahí.

El saldo inicial se registra también como cargo para dejar constancia. No lo uses para volver a cargar un pedido que después registrarás y entregarás: duplicarías la deuda.

## 4. Tomar, comprar y entregar un pedido

1. Entra a **Pedidos** y abre un nuevo pedido, o inicia uno desde la ficha del cliente.
2. Selecciona al cliente una sola vez. Captura la zapatería, código, precio y demás datos del primer artículo.
3. Pulsa **Agregar al pedido** para verlo en el resumen. Si necesitas más, pulsa **Agregar otro artículo**; cada uno puede ser de una zapatería distinta. Usa **Editar** o **Quitar** para ajustar el resumen.
4. Revisa el total y pulsa **Registrar N artículos**. También puedes registrar directamente el artículo que estés capturando con el botón final. Todos se guardan juntos; si hay un dato incorrecto, puedes corregirlo conservando la captura. Cada artículo queda **pendiente** y se compra y entrega por separado. Puedes capturar hasta 50 artículos por vez.
5. Cuando consigas un producto, abre su pedido y pulsa **Marcar como comprado**.
6. Cuando el cliente lo reciba, pulsa **Marcar como entregado** y confirma.

| Estado | Qué representa | Efecto sobre la deuda |
|---|---|---|
| Pendiente | El cliente pidió el artículo; falta comprarlo | No carga deuda |
| Comprado | Ya conseguiste el artículo; falta entregarlo | No carga deuda |
| Entregado | El cliente recibió el artículo | Suma el precio de venta al saldo |
| Cancelado | Se canceló antes de la entrega | No genera el cargo por entrega |
| Devuelto | Se registró la devolución de un artículo entregado | Revierte el cargo; los pagos previos se conservan como saldo a favor |

**La deuda nace al entregar, no al crear ni al comprar el pedido.** El sistema maneja la deuda total del cliente; los abonos no se asignan a un pedido específico.

Solo puedes editar pedidos pendientes. Puedes cancelar pendientes o comprados; los entregados tienen un flujo de devolución.

### Encontrar pedidos

- Al entrar a Pedidos, primero aparecen las zapaterías con su contador de pedidos activos.
- Selecciona una zapatería para consultar su lista y sus estados.
- Usa el buscador por código para localizar un producto; admite coincidencias parciales.
- Las vistas históricas muestran este mes por defecto. Amplía el periodo si buscas pedidos anteriores.
- La vista de entregados filtra por fecha de entrega; las demás vistas usan la fecha de creación.

## 5. Registrar pagos

1. Entra a **Abonos** o pulsa **Registrar abono** desde la ficha del cliente/pedido.
2. Busca al cliente.
3. Consulta su saldo y captura el monto recibido; agrega notas si hace falta.
4. Guarda. El pago reduce la deuda y queda en el historial.

No permite abonar si el cliente no debe ni pagar más de su saldo. Para liquidar de contado, primero entrega el pedido y después registra un abono por el saldo correspondiente.

El historial permite consultar por fecha y cliente; por defecto muestra los abonos del día. Solo el administrador puede anular un abono. La anulación vuelve a sumar su monto a la deuda una sola vez y conserva el registro, quién lo anuló y cuándo en la base de datos.

## 6. Agregar una deuda manual

Desde la ficha del cliente puedes registrar un **cargo** con monto y descripción. Sirve para una deuda que no proviene del flujo de entrega de un pedido.

El cargo aumenta el saldo. No agregues un cargo manual por un pedido que ya marcaste entregado: ese pedido ya cargó su precio automáticamente.

Solo el administrador puede anular cargos. Se conserva la auditoría y los pagos previos pueden dejar saldo a favor.

## 7. Sucursales / compradores mayoristas

El nuevo flujo tiene una [guía completa de sucursales](GUIA_SUCURSALES.md).

1. En **Sucursales**, crea o abre una. En **Datos y comisión**, configura su porcentaje fijo. En **Acceso de la sucursal**, crea su usuario y contraseña.
2. La sucursal entra a su propia cuenta y captura varios artículos. Puede guardar borrador o enviar el pedido. El administrador también puede capturarlo si llega por WhatsApp o en papel.
3. El administrador ve los artículos en **Pedidos → Sucursales**, los marca comprados y luego recibidos cuando llegan al local.
4. Selecciona los recibidos y pulsa **Preparar entrega**. Captura manualmente precio y descuento de cada producto; la comisión se calcula automáticamente sobre el subtotal neto.
5. Aplica vales si corresponde, revisa el total y pulsa **Confirmar entrega y generar ticket**. Hasta ese momento se carga el importe a la deuda. Ambos pueden ver el ticket y descargar PDF.
6. Registra pagos por ticket, o un pago general que se distribuye entre los tickets pendientes más antiguos.
7. Para devolver, la sucursal solicita la devolución. El administrador confirma la recepción física y genera un vale por el importe neto del producto, **sin comisión**.

El vale se conserva para una entrega futura; no se resta también del ticket anterior. Puede usarse parcialmente y el sobrante permanece disponible. Los tickets confirmados conservan sus datos históricos.

Para probar ambos accesos, usa una ventana normal para el administrador y una privada para la sucursal. Las cuentas solo ven su propia información.

## 8. Dashboard y reportes

El inicio muestra cobros, ventas de productos, comisiones de sucursales del mes, deuda, artículos pendientes/listos para entregar, deudores y alertas.

En **Reportes** puedes descargar:

- **Resumen General:** deuda, cobros, ventas y pedidos activos calculados al exportar.
- **Historial de Abonos:** pagos y total del periodo elegido con Desde/Hasta.

Pedidos también tiene una exportación PDF por zapatería con filtros propios de fecha y estado; no necesariamente coincide con todos los filtros de la lista.

Se comprobó la generación de los reportes PDF y de tickets de sucursales. Los tickets conservan precios, descuentos y comisión de cada entrega.

## 9. Recorrido sugerido para recordar el sistema

Usa nombres que reconozcas como pruebas, porque lo que captures en la aplicación local sí se guarda.

1. Crea **Cliente prueba**, con saldo inicial $0.
2. Crea un pedido de $500 en cualquier zapatería.
3. Comprueba que sigue debiendo $0 mientras está pendiente.
4. Márcalo comprado: la deuda sigue en $0.
5. Márcalo entregado: ahora debe $500.
6. Registra un abono de $200: debe quedar $300.
7. Revisa la ficha, el historial de abonos y el dashboard.
8. Exporta el resumen y los abonos del periodo.
9. Registra los $300 restantes: el saldo debe quedar en $0.

## 10. Cambios, devoluciones y saldo a favor de clientes locales

Desde un pedido entregado puedes registrar una devolución simple, un cambio de talla o uno por defecto. Los cambios crean un nuevo pedido pendiente; avánzalo cuando se compre y entregue la reposición.

Los pagos previos se conservan. Ejemplo: entregaste $100 y recibiste $40. Al devolver el artículo quedan $40 a favor; al entregar una reposición de $100 vuelve a quedar una deuda de $60. La ficha muestra **Saldo a favor** cuando corresponde.

El crédito se aplica a futuras entregas/cargos. Todavía no hay una función de devolución de dinero en efectivo.

## 11. Acceso, respaldos y pendientes

- En el menú del usuario ya puedes cambiar tu contraseña. Reemplaza la contraseña inicial.
- El administrador puede anular cargos/abonos; los ayudantes no pueden hacerlo. Las anulaciones se conservan en la base.
- Los importes muestran centavos. Los cortes de fecha y la hora visible usan America/Mexico_City.
- Dashboard y resumen incluyen sucursales; las comisiones se muestran aparte de las ventas de productos. Las sucursales pasan por comprado y recibido antes de generar el ticket de entrega.
- Ya hay tickets, vales y administración de accesos de sucursales. La administración general de empleados y los reembolsos en efectivo siguen pendientes.
- Se revisó el flujo en navegador con tamaño de celular. Falta probar iPhone real y PostgreSQL antes de un despliegue.

Para iniciar, actualizar y respaldar, consulta [README.md](README.md). [REVISION_PROYECTO.md](REVISION_PROYECTO.md) conserva el diagnóstico inicial y el cierre de las correcciones.
