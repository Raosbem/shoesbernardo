# Calzado Bernardo

Sistema interno para clientes, pedidos de catálogo, deuda, abonos y compradores mayoristas.

La guía para recorrer las pantallas está en [GUIA_DE_USO.md](GUIA_DE_USO.md).
El flujo de pedidos, tickets y vales de sucursales está en [GUIA_SUCURSALES.md](GUIA_SUCURSALES.md).

## Ejecutar en Windows / PowerShell

Probado con Python 3.14.7. Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe run.py
```

Abre http://localhost:5000. El seed aplica las migraciones y crea las zapaterías y el administrador si faltan. No reinicia los datos existentes.

Acceso inicial: `admin` / `admin123`. Cambia la contraseña desde el menú del usuario → **Cambiar contraseña**. El servidor local escucha solo en esta computadora y tiene debug desactivado.

SQLite se guarda en `instance/negocio.db`. La clave de sesión local se genera una vez en `instance/secret_key` si no se define SECRET_KEY. Ambos quedan fuera de Git.

## Actualizar y respaldar

Antes de actualizar una base existente:

```powershell
.\.venv\Scripts\python.exe -m flask --app run:app backup-db
.\.venv\Scripts\python.exe -m flask --app run:app db upgrade
```

Los respaldos SQLite se guardan junto a la base con nombre `respaldo_*.db`. Copia periódicamente los respaldos a otro medio. Para restaurar, detén el servidor y conserva también una copia de la base actual antes de reemplazarla por el respaldo.

Para una base **del código anterior a las migraciones**, primero respáldala y verifica que corresponde al esquema original de las ocho tablas. Solo en ese caso ejecuta una vez `flask --app run:app db stamp 0001` con el Python del entorno y después `db upgrade`. No uses stamp en una base nueva ni para omitir migraciones. La base local de esta sesión ya está actualizada a 0002.

El arranque de la aplicación ya no modifica automáticamente el esquema. Las nuevas instalaciones usan seed.py; las actualizaciones usan db upgrade.

## Reglas de saldo

- Entregar un pedido local suma el precio de venta. Confirmar un ticket de sucursal suma productos netos más comisión, menos vales aplicados.
- Un pago reduce la deuda. No se permite registrar un pago superior a la deuda actual.
- Devolver un pedido local revierte su cargo y conserva los pagos como saldo a favor. En sucursales, aceptar una devolución genera un vale por el neto del producto sin comisión; el vale se aplica a una entrega futura y no se descuenta también de la deuda anterior.
- El saldo a favor se aplica automáticamente a cargos/entregas posteriores. No se registra un reembolso en efectivo: ese flujo todavía no existe.
- Solo el administrador puede anular abonos o cargos. La anulación revierte una sola vez y conserva el registro, usuario y fecha de anulación en la base.
- Los importes usan dos decimales y redondeo a centavos. Las operaciones de cuenta se serializan por cliente.
- Los cortes diarios y semanales usan America/Mexico_City; las fechas se guardan en UTC y se muestran en hora del negocio.
- Las ventas y pendientes incluyen sucursales. “Listos para entregar” incluye pedidos locales comprados y productos de sucursal recibidos. Las comisiones de sucursales del mes se muestran aparte de las ventas de productos.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m flask --app run:app db check
```

Las pruebas usan bases aisladas y cubren pagos/cambios/devoluciones, anulaciones, descuentos, validaciones, permisos, CSRF, fechas, reportes, migraciones y pagos simultáneos en SQLite. No escriben en negocio.db.

Nuevo pedido permite capturar hasta 50 artículos para un cliente y guardarlos en una sola operación. Cada artículo mantiene su zapatería y sus estados independientes. Las pruebas comprueban que un artículo inválido no guarde parcialmente la captura.

Para las pruebas opcionales de interacción móvil instala requirements-dev.txt y ejecuta `python -m unittest discover -s tests -p "browser_*.py" -v` con el Python del entorno. Utilizan Edge instalado, sin ventana y bases temporales. Comprueban pedidos locales y el recorrido de sucursales: acceso, borrador, envío, recepción, precios manuales, ticket, devolución y aplicación del vale en otra compra.

## Configuración y producción

Consulta [.env.example](.env.example). En producción define DATABASE_URL, una SECRET_KEY aleatoria privada y COOKIE_SECURE=1 al servir mediante HTTPS. Aplica `flask --app run:app db upgrade` antes de iniciar `gunicorn run:app` en Linux. Inicializa el administrador mediante seed.py solo si aún no existe y cambia su contraseña.

No se realizó un despliegue ni se ejecutaron pruebas contra PostgreSQL. Antes de publicar, verifica migraciones y flujos con una base PostgreSQL de prueba y configura respaldos del proveedor. El portal de sucursales se administra desde cada ficha: comisión fija y una cuenta por sucursal. Las cuentas de sucursal solo acceden al blueprint portal y al cambio de contraseña; la restricción también se aplica del lado del servidor. La migración 0003 añade solicitudes, entregas, tickets, devoluciones y vales conservando el historial existente. La administración general de empleados y los reembolsos en efectivo quedan para etapas posteriores.
