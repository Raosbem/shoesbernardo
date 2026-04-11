from flask import Blueprint, render_template
from flask_login import login_required
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app import db
from app.models import Cliente, Pedido, Abono, Cuenta, Cargo

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='',
                         template_folder='templates')


@dashboard_bp.route('/')
@login_required
def index():
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())   # lunes
    inicio_mes = hoy.replace(day=1)

    # --- Cobros ---
    abonos_hoy = db.session.query(func.sum(Abono.monto)).filter(
        func.date(Abono.fecha) == hoy
    ).scalar() or 0.0

    abonos_semana = db.session.query(func.sum(Abono.monto)).filter(
        Abono.fecha >= inicio_semana
    ).scalar() or 0.0

    # --- Ventas (entregados) ---
    ventas_semana = db.session.query(func.sum(Pedido.precio_venta)).filter(
        Pedido.estatus == 'entregado',
        Pedido.fecha_entrega >= inicio_semana
    ).scalar() or 0.0

    ventas_mes = db.session.query(func.sum(Pedido.precio_venta)).filter(
        Pedido.estatus == 'entregado',
        Pedido.fecha_entrega >= inicio_mes
    ).scalar() or 0.0

    # --- Pedidos por estatus ---
    pedidos_pendientes = Pedido.query.filter_by(estatus='pendiente').count()
    pedidos_comprados  = Pedido.query.filter_by(estatus='comprado').count()

    # --- Deuda total ---
    deuda_total = db.session.query(func.sum(Cuenta.saldo_total)).filter(
        Cuenta.saldo_total > 0
    ).scalar() or 0.0
    clientes_con_deuda = Cuenta.query.filter(Cuenta.saldo_total > 0).count()

    # --- Últimos 5 abonos del día ---
    ultimos_abonos = Abono.query.filter(
        func.date(Abono.fecha) == hoy
    ).order_by(Abono.fecha.desc()).limit(5).all()

    # --- Pedidos pendientes (últimos 5) ---
    ultimos_pedidos = Pedido.query.filter_by(estatus='pendiente')\
        .order_by(Pedido.fecha_pedido.desc()).limit(5).all()

    # --- Pedidos comprados (listos para entregar) — todos ---
    lista_comprados = Pedido.query.filter_by(estatus='comprado')\
        .order_by(Pedido.fecha_pedido.asc()).all()

    # --- Top 5 deudores ---
    top_deudores = db.session.query(Cliente, Cuenta)\
        .join(Cuenta, Cliente.id == Cuenta.cliente_id)\
        .filter(Cuenta.saldo_total > 0, Cliente.activo == True)\
        .order_by(Cuenta.saldo_total.desc())\
        .limit(5).all()

    # --- Alertas: clientes con deuda sin abonar en +30 días ---
    limite_inactividad = hoy - timedelta(days=30)

    # subconsulta: último abono por cliente
    ultimo_abono_sq = db.session.query(
        Abono.cliente_id,
        func.max(Abono.fecha).label('ultimo')
    ).group_by(Abono.cliente_id).subquery()

    alertas = db.session.query(Cliente, Cuenta)\
        .join(Cuenta, Cliente.id == Cuenta.cliente_id)\
        .outerjoin(ultimo_abono_sq, Cliente.id == ultimo_abono_sq.c.cliente_id)\
        .filter(
            Cuenta.saldo_total > 0,
            Cliente.activo == True,
            Cliente.es_sucursal == False,
            db.or_(
                ultimo_abono_sq.c.ultimo == None,
                ultimo_abono_sq.c.ultimo < limite_inactividad
            )
        ).order_by(Cuenta.saldo_total.desc()).limit(8).all()

    return render_template('dashboard/index.html',
                           hoy=hoy,
                           abonos_hoy=abonos_hoy,
                           abonos_semana=abonos_semana,
                           ventas_semana=ventas_semana,
                           ventas_mes=ventas_mes,
                           pedidos_pendientes=pedidos_pendientes,
                           pedidos_comprados=pedidos_comprados,
                           deuda_total=deuda_total,
                           clientes_con_deuda=clientes_con_deuda,
                           ultimos_abonos=ultimos_abonos,
                           ultimos_pedidos=ultimos_pedidos,
                           lista_comprados=lista_comprados,
                           top_deudores=top_deudores,
                           alertas=alertas)
