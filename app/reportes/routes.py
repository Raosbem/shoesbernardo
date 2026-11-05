from app.utils import money, today, utc_start, day_range
from flask import Blueprint, render_template, request, send_file, make_response
from flask_login import login_required
from datetime import date, datetime
from io import BytesIO
from sqlalchemy import func
from app import db
from app.models import PedidoSucursal, Cliente, Pedido, Abono, Cuenta, TicketSucursal

from xhtml2pdf import pisa

reportes_bp = Blueprint('reportes', __name__, url_prefix='/reportes',
                        template_folder='templates')


# ---------------------------------------------------------------------------
# Página principal de reportes
# ---------------------------------------------------------------------------
@reportes_bp.route('/')
@login_required
def index():
    hoy = today()
    return render_template('reportes/index.html', hoy=hoy)


# ---------------------------------------------------------------------------
# Exportar resumen general
# ---------------------------------------------------------------------------
@reportes_bp.route('/exportar/resumen')
@login_required
def exportar_resumen():
    hoy = today()
    inicio_mes = hoy.replace(day=1)

    deuda_total        = db.session.query(func.sum(Cuenta.saldo_total))\
                           .filter(Cuenta.saldo_total > 0).scalar() or money(0)
    clientes_con_deuda = Cuenta.query.filter(Cuenta.saldo_total > 0).count()

    cobrado_mes = db.session.query(func.sum(Abono.monto))\
                    .filter(Abono.anulado == False, Abono.fecha >= utc_start(inicio_mes)).scalar() or money(0)

    vendido_mes = db.session.query(func.sum(Pedido.precio_venta))\
                    .filter(Pedido.estatus == 'entregado',
                            Pedido.fecha_entrega >= utc_start(inicio_mes)).scalar() or money(0)

    vendido_mes += db.session.query(func.sum(PedidoSucursal.precio_final)).filter(PedidoSucursal.estatus == 'entregado', PedidoSucursal.fecha_entrega >= utc_start(inicio_mes)).scalar() or money(0)
    comisiones_mes = db.session.query(func.sum(TicketSucursal.comision)).filter(
        TicketSucursal.estado == 'confirmado', TicketSucursal.fecha_confirmacion >= utc_start(inicio_mes)
    ).scalar() or money(0)

    pedidos_pendientes = Pedido.query.filter_by(estatus='pendiente').count() + PedidoSucursal.query.filter_by(estatus='pendiente').count()
    pedidos_comprados  = Pedido.query.filter_by(estatus='comprado').count() + PedidoSucursal.query.filter_by(estatus='recibido').count()
    pedidos_entregados = Pedido.query.filter(
        Pedido.estatus == 'entregado',
        Pedido.fecha_entrega >= utc_start(inicio_mes)
    ).count()

    pedidos_activos = Pedido.query.filter(
        Pedido.estatus.in_(['pendiente', 'comprado'])
    ).order_by(Pedido.estatus, Pedido.fecha_pedido).all()

    pedidos_entregados += PedidoSucursal.query.filter(PedidoSucursal.estatus == 'entregado', PedidoSucursal.fecha_entrega >= utc_start(inicio_mes)).count()
    pedidos_activos += PedidoSucursal.query.filter(PedidoSucursal.estatus.in_(['pendiente', 'comprado', 'recibido'])).order_by(PedidoSucursal.fecha_pedido).all()

    html = render_template('reportes/pdf_resumen.html',
                           hoy=hoy,
                           deuda_total=deuda_total,
                           clientes_con_deuda=clientes_con_deuda,
                           cobrado_mes=cobrado_mes,
                           vendido_mes=vendido_mes,
                           comisiones_mes=comisiones_mes,
                           pedidos_pendientes=pedidos_pendientes,
                           pedidos_comprados=pedidos_comprados,
                           pedidos_entregados=pedidos_entregados,
                           pedidos_activos=pedidos_activos)

    buf = BytesIO()
    pisa.CreatePDF(html, dest=buf)
    buf.seek(0)

    nombre = f'resumen_{hoy.strftime("%Y%m%d")}.pdf'
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


# ---------------------------------------------------------------------------
# Exportar historial de abonos
# ---------------------------------------------------------------------------
@reportes_bp.route('/exportar/abonos')
@login_required
def exportar_abonos():
    fecha_desde_str = request.args.get('desde', '')
    fecha_hasta_str = request.args.get('hasta', '')
    hoy = today()

    try:
        fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_desde = hoy.replace(day=1)

    try:
        fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_hasta = hoy

    if fecha_hasta < fecha_desde:
        from flask import abort
        abort(400, description='La fecha final no puede ser anterior a la inicial.')

    abonos = Abono.query.filter(
        Abono.anulado == False,
        Abono.fecha >= utc_start(fecha_desde),
        Abono.fecha < day_range(fecha_hasta)[1]
    ).order_by(Abono.fecha).all()

    total = sum(a.monto for a in abonos)

    html = render_template('reportes/pdf_abonos.html',
                           hoy=hoy,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           abonos=abonos,
                           total=total)

    buf = BytesIO()
    pisa.CreatePDF(html, dest=buf)
    buf.seek(0)

    nombre = f'abonos_{fecha_desde.strftime("%Y%m%d")}_{fecha_hasta.strftime("%Y%m%d")}.pdf'
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response
