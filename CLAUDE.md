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
| Reportes | openpyxl (Excel), weasyprint (PDF) |
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
| 4 | Sucursales | ⬜ Pendiente |
| 5 | Reportes (Excel + PDF) | ⬜ Pendiente |
| 6 | Dashboard con métricas | ⬜ Pendiente |

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

- Sesión 1 (2026-04-09): Etapa 1 completada — estructura, modelos, auth, seed, templates base.
- Sesión 2 (2026-04-09): Etapa 2 completada — Módulo Clientes (CRUD, ficha, búsqueda, alertas deuda/inactividad, gestión zapaterías) + Módulo Abonos (registro rápido con saldo visible, historial con filtros, descuento automático de saldo).
- Sesión 3 (2026-04-09): Etapa 3 completada — Módulo Pedidos (lista con tabs activos/pendiente/comprado/entregado/todos, filtros por zapatería y cliente, nuevo pedido, detalle, editar, avanzar estatus pendiente→comprado→entregado, cancelar con motivo). Al entregar se carga automáticamente precio_venta al saldo del cliente. Edición solo permitida en estatus pendiente. Cancelación bloqueada si ya fue entregado. Devoluciones con 3 tipos (simple, cambio talla, cambio defecto). PDF por zapatería con xhtml2pdf.
- Sesión 4 (2026-04-09): Mejoras al Módulo Pedidos — (1) Navegación en dos niveles: pantalla de selección de zapatería con tarjetas + contador de activos, luego lista filtrada con botón ←. (2) Buscador por código de producto disponible en ambas pantallas (búsqueda parcial, cross-zapatería). (3) Filtro de fechas automático en vistas históricas (entregados/todos/cancelados/devueltos): por defecto "este mes", opciones: semana / mes / trimestre / todo el historial. Template nuevo: `pedidos/seleccion.html`. Parámetro `ver_todos=1` para saltarse la selección.
