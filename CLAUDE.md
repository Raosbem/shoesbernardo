# CLAUDE.md — Sistema de Gestión Comercial (Calzado por Catálogo)

> Este archivo es leído automáticamente al iniciar cada sesión. Mantenerlo actualizado al cerrar cada sesión.

---

## Descripción del proyecto

Aplicación web interna para gestionar un negocio de calzado y ropa por catálogo.
El dueño actúa como intermediario: recibe pedidos de clientes, compra con descuento y revende.
Clientes pagan de contado o en abonos. Existen "sucursales" (compradores mayoristas semanales).

**Deploy:** Railway (PostgreSQL en prod, SQLite en local)
**URL producción:** pendiente de configurar en Railway

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Flask (Python) |
| ORM | SQLAlchemy |
| DB local | SQLite (`instance/negocio.db`) |
| DB producción | PostgreSQL (Railway) |
| Frontend | Bootstrap 5 CDN + Jinja2 templates |
| Auth | Flask-Login |
| Reportes | xhtml2pdf (PDF) |
| Deploy | Railway (desde GitHub, sin Docker) |

---

## Estructura del proyecto

```
negocio_calzado/
├── app/
│   ├── __init__.py          # App factory
│   ├── models.py            # Modelos SQLAlchemy
│   ├── auth/
│   │   ├── routes.py
│   │   └── templates/auth/
│   ├── clientes/
│   │   ├── routes.py
│   │   └── templates/clientes/
│   ├── pedidos/
│   │   ├── routes.py
│   │   └── templates/pedidos/
│   ├── abonos/
│   │   ├── routes.py
│   │   └── templates/abonos/
│   ├── sucursales/
│   │   ├── routes.py
│   │   └── templates/sucursales/
│   ├── reportes/
│   │   ├── routes.py
│   │   └── templates/reportes/
│   └── static/
│       ├── css/
│       └── js/
├── instance/
│   └── negocio.db           # SQLite local (gitignored)
├── templates/               # Templates globales (base.html, dashboard)
├── CLAUDE.md
├── config.py
├── run.py
├── seed.py
└── requirements.txt
```

---

## Modelos de BD

| Modelo | Descripción |
|--------|-------------|
| `Usuario` | Login, rol: admin / ayudante |
| `Zapateria` | Cklass, Andrea, etc. |
| `Cliente` | Clientes comunidad + sucursales (`es_sucursal`) |
| `Pedido` | Pedidos de clientes regulares |
| `Cuenta` | Saldo actual por cliente (1 por cliente) |
| `Abono` | Pagos parciales de clientes |
| `PedidoSucursal` | Pedidos mayoristas con descuento |

---

## Credenciales iniciales (seed)

- **Admin:** `admin` / `admin123`
- Cambiar desde la app después del primer login

---

## Zapaterías precargadas (seed)

Supershoes, Golden Shoes, Pakar, Andrea, Cklass, Price Shoes, BL Shoes

---

## Decisiones de diseño tomadas

- **Cuadre semanal eliminado** → reemplazado por Dashboard con métricas en tiempo real (no se necesita modelo extra)
- **Sucursales separadas** de clientes regulares en módulo y flujo propios
- **SQLite local / PostgreSQL prod** → config.py detecta `DATABASE_URL` del entorno
- **PDF generado con xhtml2pdf** (no weasyprint — requiere GTK en Windows, incompatible)
- Interfaz **mobile-first**, simple, sin tecnicismos — el dueño lo usa desde iPhone
- **Lista de pedidos en dos niveles**: nivel 1 = selección de zapatería con tarjetas, nivel 2 = lista filtrada por zapatería con tabs
- **Vistas históricas** (entregados/todos/cancelados/devueltos) muestran por defecto "este mes" para evitar listas largas

---

## Prioridades de desarrollo

| # | Módulo | Estado |
|---|--------|--------|
| 1 | Estructura base + Modelos + Auth | ✅ Completado |
| 2 | Clientes + Abonos | ✅ Completado |
| 3 | Pedidos | ✅ Completado |
| 4 | Sucursales | ✅ Completado |
| 5 | Reportes (PDF) | ✅ Completado |
| 6 | Dashboard con métricas | ✅ Completado |

---

## Cómo correr el proyecto localmente

```bash
pip install -r requirements.txt
python seed.py        # Crea BD + datos iniciales
python run.py         # Levanta servidor en http://localhost:5000
```

---

## Variables de entorno (.env)

```
SECRET_KEY=clave-secreta-cambiar
DATABASE_URL=                   # Vacío = usa SQLite local
                                # En Railway: postgresql://...
```

---

## Notas para próximas sesiones

_(Actualizar aquí al final de cada sesión)_

- Sucursales (2026-11-04): portal /mi-sucursal con cuenta vinculada a una sola sucursal, guardia global que bloquea módulos de personal, borradores/envío de pedidos múltiples. Bandeja unificada /pedidos/bandeja en navegación. Pendiente→comprado→recibido→entregado; preparación manual de precio/descuento por producto, revisión y confirmación con ticket snapshot/PDF. Comisión fija configurable solo por admin, calculada sobre subtotal neto; conserva histórico y validación de revisión. Devoluciones solicitadas y aprobadas por admin al recibir físicamente; vale por neto SIN comisión, solo aplicado a futuras entregas (no rebajar además deuda anterior). Uso parcial/FIFO/lock por sucursal, pagos por ticket y distribución de pagos generales. Migración 0003 aplicada tras respaldo SQLite, ver GUIA_SUCURSALES.md. Pruebas en tests/test_sucursales.py y browser_sucursales.py. No se importaron los datos del Excel ni se crearon cuentas ficticias en la base del usuario.

- Pedidos múltiples (2026-11-04): nuevo formulario pedidos/nuevo.html y static/js/pedidos_nuevo.js. Un cliente, varios artículos de distintas tiendas, resumen editable con total y registro atómico (máximo 50). Conserva captura ante errores; cada artículo conserva compra/entrega independiente. Nuevo GET /pedidos/nuevo usa esta pantalla; edición individual conserva pedidos/form.html. Pasaron 29 pruebas de servidor y una prueba Playwright/Edge móvil con datos aislados. Priorizar facilidad de uso en todos los cambios según petición del usuario.

- Estabilización (2026-11-03): Numeric/Decimal y crédito en devoluciones/cambios; anulaciones auditadas solo admin; validaciones, bloqueo de cuenta, CSRF/logout POST, cambio de contraseña, zona horaria y métricas de sucursales corregidos. Migraciones 0001/0002; seed aplica upgrade. Respaldo previo a migración local. 25 pruebas pasaron, incluyendo migraciones/pagos simultáneos. Consultar README.md y GUIA_DE_USO.md. PostgreSQL, revisión visual móvil/PDF y tickets siguen pendientes.

- Revisión (2026-11-03): Ver `REVISION_PROYECTO.md`. Sintaxis de 19 archivos, 17 vistas y tres exportaciones PDF comprobadas con SQLite en memoria. Flujos básicos de pedidos/abonos/sucursales funcionales. Reproducidos: pérdida de crédito al cambiar pedidos parcialmente pagados, montos infinitos aceptados, pedido con cliente inexistente y redirección externa en login. Priorizar saldos y validaciones antes de continuar. Sin cambios en lógica de la aplicación.

- Sesión 1 (2026-04-09): Etapa 1 completada — estructura, modelos, auth, seed, templates base.
- Sesión 2 (2026-04-09): Etapa 2 completada — Módulo Clientes (CRUD, ficha, búsqueda, alertas deuda/inactividad, gestión zapaterías) + Módulo Abonos (registro rápido con saldo visible, historial con filtros, descuento automático de saldo).
- Sesión 3 (2026-04-09): Etapa 3 completada — Módulo Pedidos (lista con tabs activos/pendiente/comprado/entregado/todos, filtros por zapatería y cliente, nuevo pedido, detalle, editar, avanzar estatus pendiente→comprado→entregado, cancelar con motivo). Al entregar se carga automáticamente precio_venta al saldo del cliente. Edición solo permitida en estatus pendiente. Cancelación bloqueada si ya fue entregado. Devoluciones con 3 tipos (simple, cambio talla, cambio defecto). PDF por zapatería con xhtml2pdf.
- Sesión 4 (2026-04-09): Mejoras al Módulo Pedidos — (1) Navegación en dos niveles: pantalla de selección de zapatería con tarjetas + contador de activos, luego lista filtrada con botón ←. (2) Buscador por código de producto disponible en ambas pantallas (búsqueda parcial, cross-zapatería). (3) Filtro de fechas automático en vistas históricas (entregados/todos/cancelados/devueltos): por defecto "este mes", opciones: semana / mes / trimestre / todo el historial. Template nuevo: `pedidos/seleccion.html`. Parámetro `ver_todos=1` para saltarse la selección.
- Sesión 5 (2026-04-10): Etapa 4 completada — Módulo Sucursales completo: lista con contador de pendientes, nueva/editar sucursal, ficha con saldo + abono rápido inline + historial de pedidos filtrable por semana + historial de abonos, nuevo pedido (precio base + descuento % → precio final calculado en tiempo real con JS, semana ISO), entregar pedido (carga saldo automáticamente), cancelar pedido. Corrección en abonos.eliminar: redirect a sucursales.detalle cuando origen='sucursal'.
- Sesión 6 (2026-04-11): Etapa 5 completada — Reportes cambiados de Excel a PDF (xhtml2pdf). Templates: pdf_resumen.html (métricas + pedidos activos) y pdf_abonos.html (historial + total). Etapa 6 completada — Dashboard funcional con 7 métricas, listos para entregar, abonos del día, pedidos pendientes, top deudores, alertas inactividad. Mejora en abonos: selector de cliente reemplazado por buscador con Tom Select (CDN). run.py actualizado con host='0.0.0.0' para acceso desde iPhone en red local. Sucursales (flujo real de tickets) pendiente para próxima etapa — el jefe lo dejó para después.
