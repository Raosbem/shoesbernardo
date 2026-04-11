from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date
from app import db
from app.models import Cliente, Cuenta, Abono, PedidoSucursal, Zapateria

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales',
                           template_folder='templates')


# ---------------------------------------------------------------------------
# Lista de sucursales
# ---------------------------------------------------------------------------
@sucursales_bp.route('/')
@login_required
def lista():
    sucursales = Cliente.query.filter_by(es_sucursal=True, activo=True)\
        .order_by(Cliente.nombre).all()

    semana_actual = date.today().strftime('%G-W%V')
    for s in sucursales:
        s._pendientes = PedidoSucursal.query.filter_by(
            sucursal_id=s.id, estatus='pendiente').count()
        s._semana_actual = PedidoSucursal.query.filter_by(
            sucursal_id=s.id, semana=semana_actual).count()

    return render_template('sucursales/lista.html', sucursales=sucursales)


# ---------------------------------------------------------------------------
# Nueva sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()

        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
            return render_template('sucursales/form.html', sucursal=None)

        if Cliente.query.filter(
                Cliente.nombre.ilike(nombre),
                Cliente.es_sucursal == True).first():
            flash(f'Ya existe una sucursal con el nombre "{nombre}".', 'warning')
            return render_template('sucursales/form.html', sucursal=None)

        sucursal = Cliente(
            nombre=nombre,
            telefono=telefono or None,
            direccion=direccion or None,
            es_sucursal=True,
        )
        db.session.add(sucursal)
        db.session.flush()

        cuenta = Cuenta(cliente_id=sucursal.id, saldo_total=0.0)
        db.session.add(cuenta)
        db.session.commit()

        flash(f'Sucursal "{nombre}" registrada.', 'success')
        return redirect(url_for('sucursales.detalle', id=sucursal.id))

    return render_template('sucursales/form.html', sucursal=None)


# ---------------------------------------------------------------------------
# Detalle de sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>')
@login_required
def detalle(id):
    sucursal = Cliente.query.get_or_404(id)

    semana_filter = request.args.get('semana', '')

    query = PedidoSucursal.query.filter_by(sucursal_id=id)
    if semana_filter:
        query = query.filter_by(semana=semana_filter)
    pedidos = query.order_by(PedidoSucursal.fecha_pedido.desc()).all()

    # semanas disponibles para filtro (más recientes primero)
    semanas_rows = db.session.query(PedidoSucursal.semana)\
        .filter(PedidoSucursal.sucursal_id == id,
                PedidoSucursal.semana.isnot(None))\
        .distinct().order_by(PedidoSucursal.semana.desc()).all()
    semanas = [s[0] for s in semanas_rows]

    semana_actual = date.today().strftime('%G-W%V')

    pendientes = [p for p in pedidos if p.estatus == 'pendiente']
    total_pendiente = sum(p.precio_final for p in pendientes)

    abonos = Abono.query.filter_by(cliente_id=id)\
        .order_by(Abono.fecha.desc()).limit(20).all()
    total_abonado = db.session.query(db.func.sum(Abono.monto))\
        .filter_by(cliente_id=id).scalar() or 0.0
    total_entregado = db.session.query(db.func.sum(PedidoSucursal.precio_final))\
        .filter_by(sucursal_id=id, estatus='entregado').scalar() or 0.0

    return render_template('sucursales/detalle.html',
                           sucursal=sucursal,
                           pedidos=pedidos,
                           semanas=semanas,
                           semana_filter=semana_filter,
                           semana_actual=semana_actual,
                           total_pendiente=total_pendiente,
                           abonos=abonos,
                           total_abonado=total_abonado,
                           total_entregado=total_entregado)


# ---------------------------------------------------------------------------
# Editar sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    sucursal = Cliente.query.get_or_404(id)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
            return render_template('sucursales/form.html', sucursal=sucursal)

        sucursal.nombre = nombre
        sucursal.telefono = request.form.get('telefono', '').strip() or None
        sucursal.direccion = request.form.get('direccion', '').strip() or None
        db.session.commit()

        flash('Datos actualizados.', 'success')
        return redirect(url_for('sucursales.detalle', id=sucursal.id))

    return render_template('sucursales/form.html', sucursal=sucursal)


# ---------------------------------------------------------------------------
# Desactivar sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/desactivar', methods=['POST'])
@login_required
def desactivar(id):
    if current_user.rol != 'admin':
        flash('Solo el administrador puede desactivar sucursales.', 'danger')
        return redirect(url_for('sucursales.detalle', id=id))

    sucursal = Cliente.query.get_or_404(id)
    sucursal.activo = False
    db.session.commit()
    flash(f'Sucursal "{sucursal.nombre}" desactivada.', 'info')
    return redirect(url_for('sucursales.lista'))


# ---------------------------------------------------------------------------
# Nuevo pedido de sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/pedido', methods=['GET', 'POST'])
@login_required
def nuevo_pedido(id):
    sucursal = Cliente.query.get_or_404(id)
    zapaterias = Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all()
    semana_actual = date.today().strftime('%G-W%V')

    if request.method == 'POST':
        zapateria_id = request.form.get('zapateria_id', type=int)
        codigo = request.form.get('codigo_producto', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        color = request.form.get('color', '').strip()
        talla = request.form.get('talla', '').strip()
        semana = request.form.get('semana', '').strip() or semana_actual

        try:
            precio_base = float(request.form.get('precio_base', 0))
            descuento = float(request.form.get('descuento', 0))
            if precio_base <= 0:
                raise ValueError
            if descuento < 0 or descuento >= 100:
                raise ValueError
        except ValueError:
            flash('Precio base debe ser mayor a cero y el descuento entre 0 y 99.', 'danger')
            return render_template('sucursales/pedido.html',
                                   sucursal=sucursal, zapaterias=zapaterias,
                                   semana_actual=semana_actual)

        if not zapateria_id or not descripcion:
            flash('Zapatería y descripción son obligatorios.', 'danger')
            return render_template('sucursales/pedido.html',
                                   sucursal=sucursal, zapaterias=zapaterias,
                                   semana_actual=semana_actual)

        precio_final = round(precio_base * (1 - descuento / 100), 2)

        pedido = PedidoSucursal(
            sucursal_id=id,
            zapateria_id=zapateria_id,
            codigo_producto=codigo or None,
            descripcion=descripcion,
            color=color or None,
            talla=talla or None,
            precio_base=precio_base,
            descuento=descuento,
            precio_final=precio_final,
            semana=semana,
        )
        db.session.add(pedido)
        db.session.commit()

        flash(f'Pedido registrado. Precio final: ${precio_final:.0f}', 'success')
        return redirect(url_for('sucursales.detalle', id=id))

    return render_template('sucursales/pedido.html',
                           sucursal=sucursal, zapaterias=zapaterias,
                           semana_actual=semana_actual)


# ---------------------------------------------------------------------------
# Entregar pedido
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/pedido/<int:pedido_id>/entregar', methods=['POST'])
@login_required
def entregar_pedido(id, pedido_id):
    pedido = PedidoSucursal.query.get_or_404(pedido_id)
    if pedido.sucursal_id != id:
        flash('Pedido no válido.', 'danger')
        return redirect(url_for('sucursales.detalle', id=id))
    if pedido.estatus != 'pendiente':
        flash('Solo se pueden entregar pedidos pendientes.', 'warning')
        return redirect(url_for('sucursales.detalle', id=id))

    pedido.marcar_entregado()
    db.session.commit()
    flash(f'Pedido entregado. Se cargaron ${pedido.precio_final:.0f} al saldo.', 'success')
    return redirect(url_for('sucursales.detalle', id=id))


# ---------------------------------------------------------------------------
# Cancelar pedido
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/pedido/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(id, pedido_id):
    pedido = PedidoSucursal.query.get_or_404(pedido_id)
    if pedido.sucursal_id != id:
        flash('Pedido no válido.', 'danger')
        return redirect(url_for('sucursales.detalle', id=id))
    if pedido.estatus == 'entregado':
        flash('No se puede cancelar un pedido ya entregado.', 'warning')
        return redirect(url_for('sucursales.detalle', id=id))

    pedido.estatus = 'cancelado'
    db.session.commit()
    flash('Pedido cancelado.', 'info')
    return redirect(url_for('sucursales.detalle', id=id))


# ---------------------------------------------------------------------------
# Registrar abono a sucursal
# ---------------------------------------------------------------------------
@sucursales_bp.route('/<int:id>/abonar', methods=['POST'])
@login_required
def abonar(id):
    sucursal = Cliente.query.get_or_404(id)
    monto_str = request.form.get('monto', '').strip()
    notas = request.form.get('notas', '').strip()

    try:
        monto = float(monto_str)
        if monto <= 0:
            raise ValueError
    except ValueError:
        flash('El monto debe ser un número mayor a cero.', 'danger')
        return redirect(url_for('sucursales.detalle', id=id))

    if sucursal.saldo <= 0:
        flash('La sucursal no tiene saldo pendiente.', 'warning')
        return redirect(url_for('sucursales.detalle', id=id))

    if monto > sucursal.saldo:
        flash(f'El abono (${monto:.0f}) supera el saldo (${sucursal.saldo:.0f}).', 'warning')
        return redirect(url_for('sucursales.detalle', id=id))

    abono = Abono(
        cliente_id=id,
        monto=monto,
        registrado_por=current_user.id,
        notas=notas or None,
    )
    db.session.add(abono)
    sucursal.cuenta.aplicar_abono(monto)
    db.session.commit()

    flash(f'Abono de ${monto:.0f} registrado. Saldo: ${sucursal.cuenta.saldo_total:.0f}', 'success')
    return redirect(url_for('sucursales.detalle', id=id))
