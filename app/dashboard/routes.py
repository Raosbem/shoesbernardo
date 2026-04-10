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
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # lunes

    # Métricas del día
    abonos_hoy = db.session.query(func.sum(Abono.monto)).filter(
        func.date(Abono.fecha) == hoy
    ).scalar() or 0.0

    # Métricas de la semana
    abonos_semana = db.session.query(func.sum(Abono.monto)).filter(
        Abono.fecha >= inicio_semana
    ).scalar() or 0.0

    # Pedidos pendientes
    pedidos_pendientes = Pedido.query.filter_by(estatus='pendiente').count()

    # Deuda total activa
    deuda_total = db.session.query(func.sum(Cuenta.saldo_total)).scalar() or 0.0

    # Clientes con saldo > 0
    clientes_con_deuda = Cuenta.query.filter(Cuenta.saldo_total > 0).count()

    # Ventas (pedidos entregados) esta semana
    ventas_semana = db.session.query(func.sum(Pedido.precio_venta)).filter(
        Pedido.estatus == 'entregado',
        Pedido.fecha_entrega >= inicio_semana
    ).scalar() or 0.0

    # Últimos 5 abonos del día
    ultimos_abonos = Abono.query.filter(
        func.date(Abono.fecha) == hoy
    ).order_by(Abono.fecha.desc()).limit(5).all()

    # Últimos 5 pedidos pendientes
    ultimos_pedidos = Pedido.query.filter_by(estatus='pendiente')\
        .order_by(Pedido.fecha_pedido.desc()).limit(5).all()

    return render_template('dashboard/index.html',
                           abonos_hoy=abonos_hoy,
                           abonos_semana=abonos_semana,
                           ventas_semana=ventas_semana,
                           pedidos_pendientes=pedidos_pendientes,
                           deuda_total=deuda_total,
                           clientes_con_deuda=clientes_con_deuda,
                           ultimos_abonos=ultimos_abonos,
                           ultimos_pedidos=ultimos_pedidos,
                           hoy=hoy)
