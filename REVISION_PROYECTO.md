# Revisión para retomar el proyecto — 3 de noviembre de 2026

> Este documento conserva el diagnóstico anterior a las correcciones. Consulta el cierre al final y README.md para el estado actualizado.

El proyecto tiene un MVP amplio implementado y flujos básicos funcionales. Requiere corregir saldos y validaciones antes de usarlo como registro confiable del negocio.

## Estado actual

- Flask con blueprints, SQLAlchemy, Flask-Login, CSRF y Jinja/Bootstrap.
- Clientes: alta/edición, búsqueda, saldo inicial, cargos, historial, alertas y desactivación.
- Pedidos: alta/edición, compra, entrega con cargo automático, cancelación, devolución y reposición por talla/defecto.
- Abonos: registro, rechazo de pagos mayores al saldo, historial y eliminación con reversión.
- Sucursales: alta/edición, pedidos semanales, descuento, entrega y abonos. El flujo real de tickets sigue pendiente según CLAUDE.md.
- Dashboard y reportes PDF implementados.
- Último commit registrado: 11 de abril de 2026. Railway figura como destino, pero no hay URL configurada; no se verificó producción.

## Comprobaciones realizadas

Se creó `.venv` y se instalaron las dependencias. Las pruebas usaron SQLite en memoria y datos ficticios; no se ejecutó seed.py ni se utilizó una base real.

- Sintaxis correcta en los 19 archivos Python.
- Acceso sin sesión redirige al login.
- 17 vistas principales respondieron HTTP 200 con sesión de administrador.
- Pedido pendiente → comprado → entregado: cargo correcto.
- Abono parcial y rechazo de abono superior al saldo: correctos.
- Pedido de sucursal de $200 con descuento de 10 %: cargo de $180; después de abonar $80 quedó $100.
- Las tres exportaciones devolvieron contenido con firma PDF y HTTP 200. No se inspeccionó su aspecto visual.

No hay una suite de pruebas versionada. No se comprobaron interfaz móvil, concurrencia, PostgreSQL ni despliegue. CSRF se desactivó exclusivamente en la aplicación de prueba para aislar los flujos; falta comprobar ese recorrido con tokens.

## Hallazgos prioritarios

1. **Cambios/devoluciones pierden el crédito de pagos previos.** `Cuenta.aplicar_abono` limita el saldo mínimo a cero (`app/models.py:97`); se reutiliza al devolver (`app/pedidos/routes.py:350`) y eliminar cargos (`app/clientes/routes.py:229`). Reproducido: entregar $100, abonar $40, cambiar por talla y entregar la reposición deja $100 de deuda en lugar de $60 si no hubo reembolso. Definir crédito/reembolso y movimientos reversibles.

2. **Validación insuficiente de montos y referencias.** Reproducido: `saldo_inicial=inf` crea una cuenta con saldo infinito (`app/clientes/routes.py:66`). Rechazar valores no finitos en todas las entradas monetarias. Un pedido con cliente inexistente se guarda en SQLite y después falla al leer el nombre (`app/pedidos/routes.py:171-184`). Validar existencia, estado activo, tipo cliente/sucursal y zapatería antes de guardar. PostgreSQL puede rechazar la referencia, pero falta manejar el error.

3. **Dinero con Float y saldo mutable.** Conviene Numeric/Decimal con precisión explícita. Las operaciones actuales leen y reescriben el saldo sin bloqueo ni actualización atómica; existe riesgo de redondeos y pérdida de movimientos simultáneos. La concurrencia no se probó.

4. **Métricas con alcance inconsistente.** Dashboard y resumen incluyen abonos/cuentas de sucursales, pero ventas y pedidos solo usan `Pedido`, omitiendo `PedidoSucursal` (`app/dashboard/routes.py:18-47`, `app/reportes/routes.py:34-55`). Separar o integrar ambos explícitamente. El top deudores también enlaza sucursales a la ficha de cliente regular.

5. **Autenticación y configuración.** Reproducido: login con `next=https://example.org` redirige fuera de la aplicación (`app/auth/routes.py:22`). Validar destino. El seed crea una contraseña conocida; no existe la pantalla de cambio que anuncia CLAUDE.md. Producción debe exigir SECRET_KEY propia; ahora hay una pública por defecto. `run.py` activa debug y escucha en todas las interfaces: reservarlo para desarrollo y definir arranque de producción.

## Pendientes adicionales

- Se guardan fechas UTC con `datetime.utcnow()` y se comparan con `date.today()` sin conversión uniforme a la zona del negocio; puede desfasar cobros diarios.
- Históricos de pedidos filtran fecha de creación incluso al consultar entregados; un pedido antiguo entregado este mes puede quedar fuera. Acordar la fecha que representa cada vista.
- No hay migraciones: `db.create_all()` crea tablas faltantes, pero no actualiza columnas existentes.
- requirements.txt no fija versiones; la instalación actual puede diferir del entorno original.
- Definir permisos de eliminación de abonos/cargos: cualquier usuario autenticado puede hacerlo y el registro se borra físicamente. Conservar auditoría de anulaciones.
- CLAUDE.md omite el modelo Cargo y marca sucursales completas aunque deja tickets pendiente.

## Orden recomendado

1. Acordar reglas de cambios, devoluciones, crédito y reembolsos; corregir saldos con pruebas de esos casos.
2. Cerrar validaciones, permisos y autenticación.
3. Incorporar migraciones, precisión monetaria, versiones reproducibles y respaldos antes de migrar datos reales.
4. Unificar métricas y zona horaria; verificar PostgreSQL, móvil y aspecto de PDF.
5. Completar tickets de sucursales y preparar despliegue.

La revisión no cambia la lógica ni corrige estos hallazgos. El entorno y el script de comprobación quedaron dentro de `.venv`, ignorado por Git.


## Cierre de correcciones — 3 de noviembre de 2026

Se corrigieron los hallazgos reproducidos: crédito en cambios/devoluciones y anulación de cargos, importes no finitos, referencias de pedidos y redirecciones externas de login. Se incorporaron Numeric/Decimal, centavos visibles, anulaciones auditadas solo por administrador, bloqueo de cuenta por cliente, cambio de contraseña, logout con POST/CSRF, clave local aleatoria, cortes y visualización en hora del negocio, métricas de sucursales y filtro por fecha de entrega en la vista de entregados.

Se añadieron migraciones 0001/0002, dependencias fijadas, backup-db y documentación operativa. Pasaron 25 pruebas automatizadas, incluyendo migración de una base nueva y otra con datos previos, así como dos pagos simultáneos. La base local se respaldó y migró sin registrar datos de prueba del negocio.

Pendientes deliberados: tickets de sucursales, gestión de usuarios, reembolsos en efectivo; verificación en PostgreSQL/producción y revisión visual móvil/PDF. El saldo a favor se conserva para futuros cargos; no equivale a registrar un reembolso.


## Ampliación de sucursales — 4 de noviembre de 2026

Implementado el portal con acceso aislado por sucursal, pedidos múltiples con borradores/envío, bandeja unificada, recepción y preparación de entregas con precio/descuento manuales, comisión fija por sucursal, revisión y ticket histórico/PDF. Devoluciones aprobadas al recibir físicamente el producto generan vales por el neto sin comisión, con saldo, uso parcial y trazabilidad por ticket. Los pagos se asignan a tickets y las anulaciones conservan auditoría. Ver GUIA_SUCURSALES.md.

Migración 0003 aplicada tras respaldo, sin importar el Excel ni sembrar datos ficticios en la base local. Pasaron 48 pruebas de servidor, incluidas migración con registros referenciados, aislamiento de cuentas y consumo simultáneo de vales; también dos recorridos en navegador móvil (pedidos locales y sucursales). Continúa pendiente la validación de PostgreSQL y el acceso público/remoto.
