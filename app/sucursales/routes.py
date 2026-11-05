import json
from io import BytesIO
from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from xhtml2pdf import pisa
from app import db
from app.models import (Abono, Cliente, Cuenta, DevolucionSucursal, PedidoSucursal,
                        SolicitudSucursal, TicketSucursal, Usuario, ValeSucursal, Zapateria)
from app.utils import admin_required, get_customer, lock_customer, money
from app.sucursales.services import (BranchError, available_vouchers, begin_delivery,
    confirm_delivery, delivery_signature, lock_delivery, percentage, price_delivery, request_return,
    resolve_return, save_request)

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales', template_folder='templates')
portal_bp = Blueprint('portal', __name__, url_prefix='/mi-sucursal', template_folder='templates')


def failure(error, endpoint, **kwargs):
    db.session.rollback()
    flash(str(error), 'danger')
    return redirect(url_for(endpoint, **kwargs))


def own_branch():
    if current_user.rol != 'sucursal' or not current_user.sucursal_id:
        abort(403)
    return get_customer(current_user.sucursal_id, branch=True, active=True)


def visible_ticket(id):
    ticket = TicketSucursal.query.get_or_404(id)
    if current_user.rol == 'sucursal' and (ticket.sucursal_id != own_branch().id or ticket.estado != 'confirmado'):
        abort(404)
    return ticket


def panel(branch, portal=False, tab='pedidos'):
    orders = PedidoSucursal.query.filter(PedidoSucursal.sucursal_id == branch.id,
        PedidoSucursal.estatus != 'borrador').order_by(PedidoSucursal.fecha_pedido.desc()).all()
    batches = SolicitudSucursal.query.filter_by(sucursal_id=branch.id)
    if not portal:
        batches = batches.filter(db.or_(SolicitudSucursal.estado == 'enviado', SolicitudSucursal.creado_por == current_user.id))
    return render_template('sucursales/panel.html', sucursal=branch, portal=portal, tab=tab,
        pedidos=orders, disponible=available_vouchers(branch.id),
        solicitudes=batches.order_by(SolicitudSucursal.id.desc()).all(),
        tickets=TicketSucursal.query.filter_by(sucursal_id=branch.id, estado='confirmado').order_by(TicketSucursal.id.desc()).all(),
        preparaciones=TicketSucursal.query.filter_by(sucursal_id=branch.id, estado='borrador').order_by(TicketSucursal.id.desc()).all() if not portal else [],
        devoluciones=DevolucionSucursal.query.filter_by(sucursal_id=branch.id).order_by(DevolucionSucursal.id.desc()).all(),
        vales=ValeSucursal.query.filter_by(sucursal_id=branch.id).order_by(ValeSucursal.id.desc()).all(),
        abonos=Abono.query.filter_by(cliente_id=branch.id, anulado=False).order_by(Abono.fecha.desc()).limit(30).all())


@sucursales_bp.route('/')
@login_required
def lista():
    query = Cliente.query.filter_by(es_sucursal=True)
    if not request.args.get('inactivas'):
        query = query.filter_by(activo=True)
    branches = query.order_by(Cliente.nombre).all()
    for branch in branches:
        branch._pendientes = PedidoSucursal.query.filter(PedidoSucursal.sucursal_id == branch.id,
            PedidoSucursal.estatus.in_(['pendiente', 'comprado', 'recibido'])).count()
    return render_template('sucursales/lista.html', sucursales=branches,
        devoluciones_pendientes=DevolucionSucursal.query.filter_by(estado='solicitada').count())


def branch_form(branch=None):
    if request.method == 'POST':
        name = request.form.get('nombre', '').strip()
        try:
            if not name:
                raise BranchError('El nombre es obligatorio.')
            rate = percentage(request.form.get('comision_pct', '0'))
            duplicate = Cliente.query.filter(func.lower(Cliente.nombre) == name.lower(), Cliente.es_sucursal == True)
            if branch:
                duplicate = duplicate.filter(Cliente.id != branch.id)
            if duplicate.first():
                raise BranchError('Ya existe otra sucursal con ese nombre.')
            if branch:
                lock_customer(branch)
            else:
                branch = Cliente(es_sucursal=True, cuenta=Cuenta(saldo_total=money(0)))
            branch.nombre, branch.comision_pct = name, rate
            branch.telefono = request.form.get('telefono', '').strip() or None
            branch.direccion = request.form.get('direccion', '').strip() or None
            db.session.add(branch)
            db.session.commit()
            flash('Sucursal guardada. Su comisión se aplicará a las próximas entregas.', 'success')
            return redirect(url_for('sucursales.detalle', id=branch.id))
        except BranchError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return render_template('sucursales/form.html', sucursal=branch)


@sucursales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@admin_required
def nueva():
    return branch_form()


@sucursales_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(id):
    return branch_form(get_customer(id, branch=True))


@sucursales_bp.route('/<int:id>')
@login_required
def detalle(id):
    return panel(get_customer(id, branch=True), tab=request.args.get('tab', 'pedidos'))


@sucursales_bp.route('/<int:id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(id):
    branch = get_customer(id, branch=True)
    branch.activo = False
    db.session.commit()
    flash('Sucursal desactivada. Su historial se conserva y su acceso queda bloqueado.', 'info')
    return redirect(url_for('sucursales.lista'))


@sucursales_bp.route('/<int:id>/reactivar', methods=['POST'])
@login_required
@admin_required
def reactivar(id):
    branch = get_customer(id, branch=True)
    branch.activo = True
    db.session.commit()
    flash('Sucursal reactivada.', 'success')
    return redirect(url_for('sucursales.detalle', id=id))


@sucursales_bp.route('/<int:id>/acceso', methods=['GET', 'POST'])
@login_required
@admin_required
def acceso(id):
    branch = get_customer(id, branch=True, active=True)
    user = Usuario.query.filter_by(sucursal_id=id).first()
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            if not username or len(username) > 50:
                raise BranchError('Captura un nombre de usuario (hasta 50 caracteres).')
            duplicate = Usuario.query.filter(func.lower(Usuario.username) == username.lower())
            if user:
                duplicate = duplicate.filter(Usuario.id != user.id)
            if duplicate.first():
                raise BranchError('Ese usuario ya está ocupado. Elige otro.')
            if (not user or password) and not 10 <= len(password) <= 128:
                raise BranchError('La contraseña debe tener entre 10 y 128 caracteres.')
            user = user or Usuario(sucursal_id=id, rol='sucursal', nombre=branch.nombre)
            user.username, user.activo = username, request.form.get('activo') == '1'
            if password:
                user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Acceso guardado. Comparte el usuario y la contraseña con esta sucursal.', 'success')
            return redirect(url_for('sucursales.detalle', id=id))
        except BranchError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return render_template('sucursales/acceso.html', sucursal=branch, usuario=user)


def order_form(branch, portal=False, batch=None):
    initial = []
    if batch:
        if batch.sucursal_id != branch.id:
            abort(404)
        if not portal and batch.estado == 'borrador' and batch.creado_por != current_user.id:
            abort(404)
        if batch.estado != 'borrador':
            flash('El pedido ya fue enviado. Puedes consultar su avance aquí.', 'info')
            return redirect(url_for('portal.solicitud' if portal else 'sucursales.solicitud', id=batch.id))
        initial = [{'zapateria_id': str(p.zapateria_id), 'codigo': p.codigo_producto,
                    'descripcion': p.descripcion, 'talla': p.talla or '', 'color': p.color or '', 'notas': p.notas or '',
                    'precio_referencia': str(p.precio_referencia) if p.precio_referencia is not None else ''}
                   for p in batch.articulos]
    if request.method == 'POST':
        raw = request.form.get('articulos', '')
        try:
            intention = request.form.get('intencion', 'enviar')
            if intention not in ('enviar', 'borrador'):
                raise BranchError('Elige guardar borrador o enviar pedido.')
            saved = save_request(branch, current_user.id, raw, intention == 'enviar', batch)
            flash('Pedido enviado. Lo verás aquí conforme avance.' if intention == 'enviar' else 'Borrador guardado. Puedes continuarlo después.', 'success')
            return redirect(url_for('portal.solicitud' if portal else 'sucursales.solicitud', id=saved.id))
        except BranchError as error:
            db.session.rollback()
            flash(str(error), 'danger')
            try:
                parsed = json.loads(raw)
                initial = parsed if isinstance(parsed, list) and all(isinstance(a, dict) for a in parsed) else []
            except ValueError:
                pass
    return render_template('pedidos/nuevo.html', clientes=[], cliente_presel=None,
        zapaterias=Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all(),
        articulos=initial, sucursal=branch, modo_sucursal=True,
        volver=url_for('portal.inicio') if portal else url_for('sucursales.detalle', id=branch.id))


@sucursales_bp.route('/<int:id>/pedido', methods=['GET', 'POST'])
@login_required
def nuevo_pedido(id):
    return order_form(get_customer(id, branch=True, active=True))


def show_request(batch, portal=False):
    if portal and batch.sucursal_id != own_branch().id:
        abort(404)
    if not portal and batch.estado == 'borrador' and batch.creado_por != current_user.id:
        abort(404)
    return render_template('sucursales/solicitud.html', solicitud=batch, portal=portal)


@sucursales_bp.route('/solicitudes/<int:id>')
@login_required
def solicitud(id):
    return show_request(SolicitudSucursal.query.get_or_404(id))


@sucursales_bp.route('/solicitudes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_solicitud(id):
    batch = SolicitudSucursal.query.get_or_404(id)
    return order_form(batch.sucursal, batch=batch)


@sucursales_bp.route('/<int:id>/pedido/<int:pedido_id>/avanzar', methods=['POST'])
@login_required
def avanzar_pedido(id, pedido_id):
    branch = get_customer(id, branch=True)
    try:
        lock_customer(branch)
        order = PedidoSucursal.query.filter_by(id=pedido_id, sucursal_id=id).first_or_404()
        db.session.refresh(order)
        expected = request.form.get('estatus_actual')
        if expected not in ('pendiente', 'comprado') or expected != order.estatus:
            raise BranchError('El artículo ya cambió de estado. Revisa la lista actualizada.')
        order.estatus = 'comprado' if expected == 'pendiente' else 'recibido'
        db.session.commit()
        flash('Artículo marcado como comprado.' if expected == 'pendiente' else 'Artículo recibido. Ya puedes preparar su entrega.', 'success')
    except BranchError as error:
        return failure(error, 'sucursales.detalle', id=id)
    if request.form.get('origen') == 'bandeja':
        return redirect(url_for('pedidos.bandeja', tipo=request.form.get('tipo', 'todos'),
            estado=request.form.get('estado', 'activos'), sucursal_id=request.form.get('sucursal_id', '')))
    return redirect(url_for('sucursales.detalle', id=id))


@sucursales_bp.route('/<int:id>/pedido/<int:pedido_id>/entregar', methods=['POST'])
@login_required
def entregar_pedido(id, pedido_id):
    get_customer(id, branch=True)
    PedidoSucursal.query.filter_by(id=pedido_id, sucursal_id=id).first_or_404()
    flash('Selecciona los artículos recibidos y pulsa Preparar entrega para capturar precios y descuentos.', 'info')
    return redirect(url_for('sucursales.detalle', id=id))


@sucursales_bp.route('/<int:id>/pedido/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(id, pedido_id):
    branch = get_customer(id, branch=True)
    try:
        lock_customer(branch)
        order = PedidoSucursal.query.filter_by(id=pedido_id, sucursal_id=id).first_or_404()
        db.session.refresh(order)
        if order.estatus not in ('pendiente', 'comprado', 'recibido') or order.detalle_ticket:
            raise BranchError('Solo puedes cancelar artículos sin entrega preparada o confirmada.')
        order.estatus = 'cancelado'
        db.session.commit()
        flash('Artículo cancelado. No se cargó al saldo.', 'info')
    except BranchError as error:
        return failure(error, 'sucursales.detalle', id=id)
    return redirect(url_for('sucursales.detalle', id=id))


@sucursales_bp.route('/<int:id>/preparar', methods=['POST'])
@login_required
def preparar(id):
    branch = get_customer(id, branch=True)
    try:
        raw = request.form.getlist('pedidos')
        if any(not value.isascii() or not value.isdecimal() or len(value) > 10 for value in raw):
            raise BranchError('Selecciona artículos válidos.')
        ticket = begin_delivery(branch, [int(value) for value in raw], current_user.id)
        return redirect(url_for('sucursales.precios', id=ticket.id))
    except BranchError as error:
        return failure(error, 'sucursales.detalle', id=id)


@sucursales_bp.route('/entregas/<int:id>/preparar', methods=['GET', 'POST'])
@login_required
def precios(id):
    ticket = TicketSucursal.query.get_or_404(id)
    if ticket.estado != 'borrador':
        return redirect(url_for('sucursales.ticket', id=id))
    if request.method == 'POST':
        try:
            price_delivery(ticket, request.form)
            return redirect(url_for('sucursales.revisar', id=id))
        except BranchError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return render_template('sucursales/preparar.html', ticket=ticket,
                           disponible=available_vouchers(ticket.sucursal_id))


@sucursales_bp.route('/entregas/<int:id>/revisar')
@login_required
def revisar(id):
    ticket = TicketSucursal.query.get_or_404(id)
    if ticket.estado != 'borrador':
        return redirect(url_for('sucursales.ticket', id=id))
    if not ticket.revisado:
        return redirect(url_for('sucursales.precios', id=id))
    return render_template('sucursales/ticket.html', ticket=ticket, revision=True, portal=False,
                           firma=delivery_signature(ticket))


@sucursales_bp.route('/entregas/<int:id>/confirmar', methods=['POST'])
@login_required
def confirmar(id):
    ticket = TicketSucursal.query.get_or_404(id)
    try:
        confirm_delivery(ticket, current_user.id, request.form.get('revision'))
        flash('Entrega confirmada. El ticket ya está disponible para la sucursal.', 'success')
        return redirect(url_for('sucursales.ticket', id=id))
    except (BranchError, ValueError) as error:
        return failure(error, 'sucursales.precios', id=id)


@sucursales_bp.route('/entregas/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_entrega(id):
    ticket = TicketSucursal.query.get_or_404(id)
    branch_id = ticket.sucursal_id
    try:
        lock_delivery(ticket)
        ticket.lineas.clear()
        ticket.estado = 'cancelado'
        db.session.commit()
        flash('Preparación cancelada. Los artículos siguen recibidos y no se cargó ningún importe.', 'info')
    except BranchError as error:
        return failure(error, 'sucursales.detalle', id=branch_id)
    return redirect(url_for('sucursales.detalle', id=branch_id))


def ticket_response(ticket, portal=False):
    if ticket.estado != 'confirmado':
        abort(404)
    return render_template('sucursales/ticket.html', ticket=ticket, revision=False, portal=portal)


@sucursales_bp.route('/tickets/<int:id>')
@login_required
def ticket(id):
    return ticket_response(visible_ticket(id))


def pdf_response(ticket):
    if ticket.estado != 'confirmado':
        abort(404)
    html = render_template('sucursales/ticket_pdf.html', ticket=ticket)
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if result.err:
        abort(500, description='No se pudo generar el PDF. Inténtalo nuevamente.')
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="ticket_{ticket.folio}.pdf"'
    return response


@sucursales_bp.route('/tickets/<int:id>/pdf')
@login_required
def ticket_pdf(id):
    return pdf_response(visible_ticket(id))


@sucursales_bp.route('/<int:id>/abonar', methods=['POST'])
@login_required
def abonar(id):
    branch = get_customer(id, branch=True)
    try:
        lock_customer(branch)
        amount = money(request.form.get('monto', ''))
        if amount <= 0 or amount > branch.saldo:
            raise BranchError('Captura un abono mayor a cero y no superior a la deuda actual.')
        ticket_id = request.form.get('ticket_id', type=int)
        ticket = None
        if request.form.get('ticket_id'):
            ticket = TicketSucursal.query.filter_by(id=ticket_id, sucursal_id=id, estado='confirmado').first_or_404()
            if amount > ticket.pendiente:
                raise BranchError('El abono supera lo pendiente de este ticket.')
        note = request.form.get('notas', '').strip() or None
        remaining = amount
        targets = [ticket] if ticket else TicketSucursal.query.filter_by(sucursal_id=id, estado='confirmado').order_by(TicketSucursal.id).all()
        for target in targets:
            portion = min(remaining, target.pendiente)
            if portion > 0:
                db.session.add(Abono(cliente_id=id, monto=portion, registrado_por=current_user.id, notas=note, ticket_id=target.id))
                remaining -= portion
            if remaining == 0:
                break
        if remaining > 0:
            db.session.add(Abono(cliente_id=id, monto=remaining, registrado_por=current_user.id, notas=note))
        branch.cuenta.aplicar_abono(amount)
        db.session.commit()
        flash('Pago registrado.', 'success')
    except (BranchError, ValueError) as error:
        return failure(error, 'sucursales.detalle', id=id, tab='pagos')
    return redirect(url_for('sucursales.ticket', id=ticket.id) if ticket else url_for('sucursales.detalle', id=id, tab='pagos'))


def return_form(order, portal=False):
    if portal and order.sucursal_id != own_branch().id:
        abort(404)
    if request.method == 'POST':
        try:
            request_return(order, current_user.id, request.form.get('motivo', '').strip())
            flash('Devolución solicitada. El vale se genera cuando el administrador recibe y acepta el producto.', 'success')
            return redirect(url_for('portal.devoluciones') if portal else url_for('sucursales.detalle', id=order.sucursal_id, tab='devoluciones'))
        except BranchError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    if order.estatus != 'entregado' or order.devolucion:
        flash('Este artículo ya tiene una devolución o todavía no se ha entregado.', 'info')
        return redirect(url_for('portal.devoluciones') if portal else url_for('sucursales.detalle', id=order.sucursal_id, tab='devoluciones'))
    return render_template('sucursales/devolver.html', pedido=order, portal=portal)


@sucursales_bp.route('/articulos/<int:id>/devolver', methods=['GET', 'POST'])
@login_required
def devolver(id):
    return return_form(PedidoSucursal.query.get_or_404(id))


@sucursales_bp.route('/devoluciones')
@login_required
def devoluciones():
    return render_template('sucursales/devoluciones.html', portal=False, sucursal=None,
        devoluciones=DevolucionSucursal.query.order_by(DevolucionSucursal.fecha.desc()).all())


@sucursales_bp.route('/devoluciones/<int:id>/resolver', methods=['POST'])
@login_required
@admin_required
def resolver(id):
    item = DevolucionSucursal.query.get_or_404(id)
    try:
        action = request.form.get('accion')
        if action not in ('aprobar', 'rechazar'):
            raise BranchError('Elige confirmar recepción o rechazar la devolución.')
        resolve_return(item, current_user.id, action == 'aprobar', request.form.get('respuesta', ''))
        flash('Producto recibido y vale generado sin comisión.' if action == 'aprobar' else 'Devolución rechazada con su motivo.', 'success')
    except BranchError as error:
        return failure(error, 'sucursales.devoluciones')
    return redirect(url_for('sucursales.devoluciones'))


@portal_bp.route('/')
@login_required
def inicio():
    return panel(own_branch(), portal=True)


@portal_bp.route('/tickets')
@login_required
def tickets():
    return panel(own_branch(), portal=True, tab='tickets')


@portal_bp.route('/vales')
@login_required
def vales():
    return panel(own_branch(), portal=True, tab='vales')


@portal_bp.route('/devoluciones')
@login_required
def devoluciones():
    return panel(own_branch(), portal=True, tab='devoluciones')


@portal_bp.route('/pagos')
@login_required
def pagos():
    return panel(own_branch(), portal=True, tab='pagos')


@portal_bp.route('/pedido', methods=['GET', 'POST'])
@login_required
def nuevo():
    return order_form(own_branch(), portal=True)


@portal_bp.route('/solicitudes/<int:id>')
@login_required
def solicitud(id):
    return show_request(SolicitudSucursal.query.get_or_404(id), portal=True)


@portal_bp.route('/solicitudes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    return order_form(own_branch(), portal=True, batch=SolicitudSucursal.query.get_or_404(id))


@portal_bp.route('/tickets/<int:id>')
@login_required
def ticket(id):
    own_branch()
    return ticket_response(visible_ticket(id), portal=True)


@portal_bp.route('/tickets/<int:id>/pdf')
@login_required
def ticket_pdf(id):
    own_branch()
    return pdf_response(visible_ticket(id))


@portal_bp.route('/articulos/<int:id>/devolver', methods=['GET', 'POST'])
@login_required
def devolver(id):
    return return_form(PedidoSucursal.query.get_or_404(id), portal=True)
