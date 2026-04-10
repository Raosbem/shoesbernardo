from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date
from sqlalchemy import func
from app import db
from app.models import Abono, Cliente, Cuenta

abonos_bp = Blueprint('abonos', __name__, url_prefix='/abonos',
                       template_folder='templates')


# ---------------------------------------------------------------------------
# Registrar abono rápido
# ---------------------------------------------------------------------------
@abonos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    cliente_id = request.args.get('cliente_id', type=int)
    cliente_presel = Cliente.query.get(cliente_id) if cliente_id else None

    clientes = Cliente.query.filter_by(es_sucursal=False, activo=True)\
        .order_by(Cliente.nombre).all()

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id', type=int)
        monto_str = request.form.get('monto', '').strip()
        notas = request.form.get('notas', '').strip()

        if not cliente_id:
            flash('Selecciona un cliente.', 'danger')
            return render_template('abonos/nuevo.html',
                                   clientes=clientes, cliente_presel=cliente_presel)

        try:
            monto = float(monto_str)
            if monto <= 0:
                raise ValueError
        except ValueError:
            flash('El monto debe ser un número mayor a cero.', 'danger')
            return render_template('abonos/nuevo.html',
                                   clientes=clientes, cliente_presel=cliente_presel)

        cliente = Cliente.query.get_or_404(cliente_id)
        saldo_actual = cliente.saldo

        # Bloquear si no tiene saldo
        if saldo_actual <= 0:
            flash(f'{cliente.nombre} no tiene saldo pendiente. No se puede registrar un abono.', 'warning')
            return render_template('abonos/nuevo.html',
                                   clientes=clientes, cliente_presel=cliente_presel)

        # Bloquear si el abono excede el saldo
        if monto > saldo_actual:
            flash(
                f'El abono (${monto:.0f}) supera el saldo de {cliente.nombre} (${saldo_actual:.0f}). '
                f'Ingresa un monto menor o igual al saldo.',
                'warning'
            )
            return render_template('abonos/nuevo.html',
                                   clientes=clientes, cliente_presel=cliente_presel)

        abono = Abono(
            cliente_id=cliente_id,
            monto=monto,
            registrado_por=current_user.id,
            notas=notas or None,
        )
        db.session.add(abono)
        cliente.cuenta.aplicar_abono(monto)
        db.session.commit()

        flash(
            f'Abono de ${monto:.0f} registrado para {cliente.nombre}. '
            f'Saldo restante: ${cliente.cuenta.saldo_total:.0f}',
            'success'
        )
        return redirect(url_for('abonos.nuevo'))

    return render_template('abonos/nuevo.html',
                           clientes=clientes, cliente_presel=cliente_presel)


# ---------------------------------------------------------------------------
# Eliminar abono (revierte el saldo)
# ---------------------------------------------------------------------------
@abonos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    abono = Abono.query.get_or_404(id)
    cliente = abono.cliente
    origen = request.form.get('origen', 'historial')

    # Revertir el monto al saldo del cliente
    if cliente.cuenta:
        cliente.cuenta.agregar_cargo(abono.monto)

    db.session.delete(abono)
    db.session.commit()

    flash(
        f'Abono de ${abono.monto:.0f} eliminado. '
        f'Saldo actualizado: ${cliente.cuenta.saldo_total:.0f}',
        'info'
    )

    if origen == 'detalle':
        return redirect(url_for('clientes.detalle', id=cliente.id))
    return redirect(url_for('abonos.historial'))


# ---------------------------------------------------------------------------
# Historial de abonos
# ---------------------------------------------------------------------------
@abonos_bp.route('/')
@login_required
def historial():
    fecha_str = request.args.get('fecha', '')
    cliente_id = request.args.get('cliente_id', type=int)

    query = Abono.query

    if fecha_str:
        try:
            fecha_filtro = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            query = query.filter(func.date(Abono.fecha) == fecha_filtro)
        except ValueError:
            fecha_str = ''
    else:
        fecha_filtro = date.today()
        fecha_str = fecha_filtro.strftime('%Y-%m-%d')
        query = query.filter(func.date(Abono.fecha) == fecha_filtro)

    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)

    abonos = query.order_by(Abono.fecha.desc()).all()
    total_dia = sum(a.monto for a in abonos)

    clientes = Cliente.query.filter_by(activo=True, es_sucursal=False)\
        .order_by(Cliente.nombre).all()

    return render_template('abonos/historial.html',
                           abonos=abonos,
                           total_dia=total_dia,
                           fecha_str=fecha_str,
                           cliente_id=cliente_id,
                           clientes=clientes)
