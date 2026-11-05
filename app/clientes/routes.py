from app.utils import utc_now
from app.utils import money, today, utc_start, admin_required, get_customer, lock_customer
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from app import db
from app.models import Cliente, Cuenta, Abono, Cargo, Pedido

clientes_bp = Blueprint('clientes', __name__, url_prefix='/clientes',
                         template_folder='templates')


# ---------------------------------------------------------------------------
# Lista de clientes
# ---------------------------------------------------------------------------
@clientes_bp.route('/')
@login_required
def lista():
    q = request.args.get('q', '').strip()
    solo_deuda = request.args.get('deuda', '')

    query = Cliente.query.filter_by(es_sucursal=False, activo=True)

    if q:
        query = query.filter(Cliente.nombre.ilike(f'%{q}%'))

    clientes = query.order_by(Cliente.nombre).all()

    hoy = today()
    limite_inactividad = hoy - timedelta(days=30)

    for c in clientes:
        c._alerta_deuda_alta = c.saldo > 500
        ultimo_abono = Abono.query.filter_by(anulado=False, cliente_id=c.id)\
            .order_by(Abono.fecha.desc()).first()
        c._alerta_inactivo = (
            c.saldo > 0 and
            (ultimo_abono is None or ultimo_abono.fecha < utc_start(limite_inactividad))
        )

    if solo_deuda:
        clientes = [c for c in clientes if c.saldo > 0]

    return render_template('clientes/lista.html', clientes=clientes, q=q, solo_deuda=solo_deuda)


# ---------------------------------------------------------------------------
# Crear cliente
# ---------------------------------------------------------------------------
@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()
        saldo_inicial_str = request.form.get('saldo_inicial', '0').strip()

        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
            return render_template('clientes/form.html', cliente=None)

        if Cliente.query.filter(db.func.lower(Cliente.nombre) == nombre.lower(), Cliente.es_sucursal == False).first():
            flash(f'Ya existe un cliente con el nombre "{nombre}".', 'warning')
            return render_template('clientes/form.html', cliente=None)

        try:
            saldo_inicial = money(saldo_inicial_str) if saldo_inicial_str else money(0)
            if saldo_inicial < 0:
                raise ValueError
        except ValueError:
            flash('El saldo inicial debe ser un número mayor o igual a cero.', 'danger')
            return render_template('clientes/form.html', cliente=None)

        cliente = Cliente(
            nombre=nombre,
            telefono=telefono or None,
            direccion=direccion or None,
            es_sucursal=False,
        )
        db.session.add(cliente)
        db.session.flush()

        cuenta = Cuenta(cliente_id=cliente.id, saldo_total=saldo_inicial)
        db.session.add(cuenta)

        # Si hay saldo inicial, registrar un cargo para trazabilidad
        if saldo_inicial > 0:
            cargo = Cargo(
                cliente_id=cliente.id,
                monto=saldo_inicial,
                descripcion='Saldo inicial al registrar cliente',
                registrado_por=current_user.id,
            )
            db.session.add(cargo)

        db.session.commit()

        flash(f'Cliente "{nombre}" registrado correctamente.', 'success')
        return redirect(url_for('clientes.detalle', id=cliente.id))

    return render_template('clientes/form.html', cliente=None)


# ---------------------------------------------------------------------------
# Ficha del cliente
# ---------------------------------------------------------------------------
@clientes_bp.route('/<int:id>')
@login_required
def detalle(id):
    cliente = get_customer(id)

    abonos = Abono.query.filter_by(anulado=False, cliente_id=id)\
        .order_by(Abono.fecha.desc()).limit(20).all()

    cargos = Cargo.query.filter_by(anulado=False, cliente_id=id)\
        .order_by(Cargo.fecha.desc()).limit(20).all()

    pedidos = Pedido.query.filter_by(cliente_id=id)\
        .order_by(Pedido.fecha_pedido.desc()).limit(20).all()

    total_abonado = db.session.query(db.func.sum(Abono.monto))\
        .filter_by(anulado=False, cliente_id=id).scalar() or money(0)
    total_comprado = db.session.query(db.func.sum(Pedido.precio_venta))\
        .filter_by(cliente_id=id, estatus='entregado').scalar() or money(0)

    return render_template('clientes/detalle.html',
                           cliente=cliente,
                           abonos=abonos,
                           cargos=cargos,
                           pedidos=pedidos,
                           total_abonado=total_abonado,
                           total_comprado=total_comprado)


# ---------------------------------------------------------------------------
# Editar cliente
# ---------------------------------------------------------------------------
@clientes_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    cliente = get_customer(id)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
            return render_template('clientes/form.html', cliente=cliente)

        if Cliente.query.filter(Cliente.id != id, db.func.lower(Cliente.nombre) == nombre.lower(), Cliente.es_sucursal == False).first():
            flash('Ya existe otro cliente con ese nombre.', 'danger')
            return render_template('clientes/form.html', cliente=cliente)
        cliente.nombre = nombre
        cliente.telefono = request.form.get('telefono', '').strip() or None
        cliente.direccion = request.form.get('direccion', '').strip() or None
        db.session.commit()

        flash('Datos actualizados.', 'success')
        return redirect(url_for('clientes.detalle', id=cliente.id))

    return render_template('clientes/form.html', cliente=cliente)


# ---------------------------------------------------------------------------
# Desactivar cliente (soft delete)
# ---------------------------------------------------------------------------
@clientes_bp.route('/<int:id>/desactivar', methods=['POST'])
@login_required
def desactivar(id):
    if current_user.rol != 'admin':
        flash('Solo el administrador puede desactivar clientes.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))

    cliente = get_customer(id)
    cliente.activo = False
    db.session.commit()
    flash(f'Cliente "{cliente.nombre}" desactivado.', 'info')
    return redirect(url_for('clientes.lista'))


# ---------------------------------------------------------------------------
# Agregar cargo manual
# ---------------------------------------------------------------------------
@clientes_bp.route('/<int:id>/cargo', methods=['POST'])
@login_required
def agregar_cargo(id):
    cliente = get_customer(id)
    monto_str = request.form.get('monto', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    try:
        monto = money(monto_str)
        if monto <= 0:
            raise ValueError
    except ValueError:
        flash('El monto del cargo debe ser mayor a cero.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))

    if not descripcion:
        flash('La descripción del cargo es obligatoria.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))

    lock_customer(cliente)
    cargo = Cargo(
        cliente_id=id,
        monto=monto,
        descripcion=descripcion,
        registrado_por=current_user.id,
    )
    db.session.add(cargo)

    if not cliente.cuenta:
        cliente.cuenta = Cuenta(cliente_id=id, saldo_total=money(0))
        db.session.add(cliente.cuenta)
    cliente.cuenta.agregar_cargo(monto)

    db.session.commit()
    flash(f'Cargo de ${monto:.2f} agregado. Saldo: ${cliente.cuenta.saldo_total:.2f}', 'success')
    return redirect(url_for('clientes.detalle', id=id))


# ---------------------------------------------------------------------------
# Eliminar cargo (devolución)
# ---------------------------------------------------------------------------
@clientes_bp.route('/<int:cliente_id>/cargo/<int:cargo_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar_cargo(cliente_id, cargo_id):
    cargo = Cargo.query.get_or_404(cargo_id)
    cliente = get_customer(cliente_id)

    if cargo.cliente_id != cliente_id:
        flash('Cargo no válido.', 'danger')
        return redirect(url_for('clientes.detalle', id=cliente_id))

    lock_customer(cliente)
    db.session.refresh(cargo)
    if cargo.anulado:
        flash('Este cargo ya fue anulado.', 'warning')
        return redirect(url_for('clientes.detalle', id=cliente_id))

    # Revertir del saldo
    if cliente.cuenta:
        cliente.cuenta.aplicar_abono(cargo.monto)

    cargo.anulado = True
    cargo.anulado_por = current_user.id
    cargo.fecha_anulacion = utc_now()
    db.session.commit()
    flash(f'Cargo de ${cargo.monto:.2f} eliminado. Saldo: ${cliente.cuenta.saldo_total:.2f}', 'info')
    return redirect(url_for('clientes.detalle', id=cliente_id))


# ---------------------------------------------------------------------------
# Gestión de zapaterías (admin)
# ---------------------------------------------------------------------------
@clientes_bp.route('/zapaterias')
@login_required
def zapaterias():
    if current_user.rol != 'admin':
        flash('Acceso restringido.', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models import Zapateria
    zaps = Zapateria.query.order_by(Zapateria.nombre).all()
    return render_template('clientes/zapaterias.html', zapaterias=zaps)


@clientes_bp.route('/zapaterias/nueva', methods=['POST'])
@login_required
def nueva_zapateria():
    if current_user.rol != 'admin':
        flash('Acceso restringido.', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models import Zapateria
    nombre = request.form.get('nombre', '').strip()
    if nombre:
        if not Zapateria.query.filter_by(nombre=nombre).first():
            db.session.add(Zapateria(nombre=nombre, activa=True))
            db.session.commit()
            flash(f'Zapatería "{nombre}" agregada.', 'success')
        else:
            flash('Ya existe esa zapatería.', 'warning')
    return redirect(url_for('clientes.zapaterias'))


@clientes_bp.route('/zapaterias/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_zapateria(id):
    if current_user.rol != 'admin':
        flash('Acceso restringido.', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models import Zapateria
    z = Zapateria.query.get_or_404(id)
    z.activa = not z.activa
    db.session.commit()
    estado = 'activada' if z.activa else 'desactivada'
    flash(f'Zapatería "{z.nombre}" {estado}.', 'info')
    return redirect(url_for('clientes.zapaterias'))
