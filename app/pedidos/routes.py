from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response
from flask_login import login_required, current_user
from datetime import date, timedelta
from collections import defaultdict
from io import BytesIO
from sqlalchemy import func
from app import db
from app.models import Pedido, Cliente, Zapateria
from xhtml2pdf import pisa

pedidos_bp = Blueprint('pedidos', __name__, url_prefix='/pedidos',
                        template_folder='templates')


# ---------------------------------------------------------------------------
# Lista de pedidos — nivel 1 (selección zapatería) o nivel 2 (lista filtrada)
# ---------------------------------------------------------------------------
@pedidos_bp.route('/')
@login_required
def lista():
    estatus = request.args.get('estatus', 'activos')
    zapateria_id = request.args.get('zapateria_id', type=int)
    cliente_id = request.args.get('cliente_id', type=int)
    q = request.args.get('q', '').strip()
    ver_todos = request.args.get('ver_todos', '')

    # ── Nivel 1: pantalla de selección de zapatería ──────────────────────────
    if not zapateria_id and not q and not ver_todos:
        zapaterias = Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all()
        conteos = {}
        for z in zapaterias:
            conteos[z.id] = Pedido.query.join(Pedido.cliente).filter(
                Cliente.es_sucursal == False,
                Pedido.zapateria_id == z.id,
                Pedido.estatus.in_(['pendiente', 'comprado'])
            ).count()
        return render_template('pedidos/seleccion.html',
                               zapaterias=zapaterias,
                               conteos=conteos)

    # ── Nivel 2: lista filtrada ───────────────────────────────────────────────
    # Cuando hay búsqueda por código, mostrar todos los estatus por defecto
    if q and estatus == 'activos':
        estatus = 'todos'

    # Filtro de fecha para vistas históricas (entregados / todos)
    fecha_rango = request.args.get('fecha_rango', '')
    hoy = date.today()
    fecha_desde = None

    if estatus in ('entregado', 'todos', 'cancelado', 'devuelto') and not q:
        if not fecha_rango:
            fecha_rango = 'mes'  # default: este mes
        if fecha_rango == 'semana':
            fecha_desde = hoy - timedelta(days=hoy.weekday())
        elif fecha_rango == 'mes':
            fecha_desde = hoy.replace(day=1)
        elif fecha_rango == 'trimestre':
            fecha_desde = (hoy - timedelta(days=90)).replace(day=1)
        # 'todo' → sin filtro de fecha

    query = Pedido.query.join(Pedido.cliente).filter(Cliente.es_sucursal == False)

    if q:
        query = query.filter(Pedido.codigo_producto.ilike(f'%{q}%'))

    if estatus == 'activos':
        query = query.filter(Pedido.estatus.in_(['pendiente', 'comprado']))
    elif estatus in Pedido.ESTATUS:
        query = query.filter(Pedido.estatus == estatus)

    if fecha_desde:
        query = query.filter(func.date(Pedido.fecha_pedido) >= fecha_desde)

    if zapateria_id:
        query = query.filter(Pedido.zapateria_id == zapateria_id)

    if cliente_id:
        query = query.filter(Pedido.cliente_id == cliente_id)

    pedidos = query.order_by(Pedido.fecha_pedido.desc()).all()

    # Agrupar por zapatería
    grupos_dict = {}
    for p in pedidos:
        key = p.zapateria.nombre
        if key not in grupos_dict:
            grupos_dict[key] = {'zapateria': p.zapateria, 'pedidos': []}
        grupos_dict[key]['pedidos'].append(p)
    grupos = sorted(grupos_dict.items(), key=lambda x: x[0])

    zapaterias = Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all()
    clientes = Cliente.query.filter_by(activo=True, es_sucursal=False).order_by(Cliente.nombre).all()
    zapateria_sel = Zapateria.query.get(zapateria_id) if zapateria_id else None

    total_pendiente = Pedido.query.join(Pedido.cliente)\
        .filter(Cliente.es_sucursal == False, Pedido.estatus == 'pendiente').count()
    total_comprado = Pedido.query.join(Pedido.cliente)\
        .filter(Cliente.es_sucursal == False, Pedido.estatus == 'comprado').count()

    return render_template('pedidos/lista.html',
                           grupos=grupos,
                           pedidos=pedidos,
                           estatus=estatus,
                           zapateria_id=zapateria_id,
                           zapateria_sel=zapateria_sel,
                           cliente_id=cliente_id,
                           zapaterias=zapaterias,
                           clientes=clientes,
                           total_pendiente=total_pendiente,
                           total_comprado=total_comprado,
                           q=q,
                           fecha_rango=fecha_rango)


# ---------------------------------------------------------------------------
# Nuevo pedido
# ---------------------------------------------------------------------------
@pedidos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    cliente_id = request.args.get('cliente_id', type=int)
    cliente_presel = Cliente.query.get(cliente_id) if cliente_id else None

    clientes = Cliente.query.filter_by(activo=True, es_sucursal=False).order_by(Cliente.nombre).all()
    zapaterias = Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all()

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id', type=int)
        zapateria_id = request.form.get('zapateria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        codigo = request.form.get('codigo', '').strip()
        color = request.form.get('color', '').strip()
        talla = request.form.get('talla', '').strip()
        precio_catalogo_str = request.form.get('precio_catalogo', '').strip()
        precio_venta_str = request.form.get('precio_venta', '').strip()
        notas = request.form.get('notas', '').strip()

        errores = []
        if not cliente_id:
            errores.append('Selecciona un cliente.')
        if not zapateria_id:
            errores.append('Selecciona una zapatería.')
        if not codigo:
            errores.append('El código del producto es obligatorio.')

        precio_venta = None
        try:
            precio_venta = float(precio_venta_str)
            if precio_venta <= 0:
                raise ValueError
        except ValueError:
            errores.append('El precio de venta debe ser mayor a cero.')

        precio_catalogo = None
        if precio_catalogo_str:
            try:
                precio_catalogo = float(precio_catalogo_str)
            except ValueError:
                errores.append('El precio de catálogo no es válido.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('pedidos/form.html',
                                   clientes=clientes, zapaterias=zapaterias,
                                   cliente_presel=cliente_presel, form_data=request.form,
                                   pedido=None)

        pedido = Pedido(
            cliente_id=cliente_id,
            zapateria_id=zapateria_id,
            descripcion=descripcion,
            codigo_producto=codigo or None,
            color=color or None,
            talla=talla or None,
            precio_catalogo=precio_catalogo,
            precio_venta=precio_venta,
            notas=notas or None,
        )
        db.session.add(pedido)
        db.session.commit()

        flash(f'Pedido registrado para {pedido.cliente.nombre}.', 'success')
        return redirect(url_for('pedidos.detalle', id=pedido.id))

    return render_template('pedidos/form.html',
                           clientes=clientes, zapaterias=zapaterias,
                           cliente_presel=cliente_presel, form_data=None,
                           pedido=None)


# ---------------------------------------------------------------------------
# Detalle de pedido
# ---------------------------------------------------------------------------
@pedidos_bp.route('/<int:id>')
@login_required
def detalle(id):
    pedido = Pedido.query.get_or_404(id)
    return render_template('pedidos/detalle.html', pedido=pedido)


# ---------------------------------------------------------------------------
# Editar pedido (solo pendiente)
# ---------------------------------------------------------------------------
@pedidos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    pedido = Pedido.query.get_or_404(id)

    if pedido.estatus != 'pendiente':
        flash('Solo se pueden editar pedidos en estatus pendiente.', 'warning')
        return redirect(url_for('pedidos.detalle', id=id))

    clientes = Cliente.query.filter_by(activo=True, es_sucursal=False).order_by(Cliente.nombre).all()
    zapaterias = Zapateria.query.filter_by(activa=True).order_by(Zapateria.nombre).all()

    if request.method == 'POST':
        descripcion = request.form.get('descripcion', '').strip()
        zapateria_id = request.form.get('zapateria_id', type=int)
        codigo = request.form.get('codigo', '').strip()
        color = request.form.get('color', '').strip()
        talla = request.form.get('talla', '').strip()
        precio_catalogo_str = request.form.get('precio_catalogo', '').strip()
        precio_venta_str = request.form.get('precio_venta', '').strip()
        notas = request.form.get('notas', '').strip()

        errores = []
        if not codigo:
            errores.append('El código del producto es obligatorio.')
        if not zapateria_id:
            errores.append('Selecciona una zapatería.')

        precio_venta = None
        try:
            precio_venta = float(precio_venta_str)
            if precio_venta <= 0:
                raise ValueError
        except ValueError:
            errores.append('El precio de venta debe ser mayor a cero.')

        precio_catalogo = None
        if precio_catalogo_str:
            try:
                precio_catalogo = float(precio_catalogo_str)
            except ValueError:
                errores.append('El precio de catálogo no es válido.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('pedidos/form.html',
                                   clientes=clientes, zapaterias=zapaterias,
                                   cliente_presel=pedido.cliente,
                                   form_data=request.form, pedido=pedido)

        pedido.zapateria_id = zapateria_id
        pedido.descripcion = descripcion
        pedido.codigo_producto = codigo or None
        pedido.color = color or None
        pedido.talla = talla or None
        pedido.precio_catalogo = precio_catalogo
        pedido.precio_venta = precio_venta
        pedido.notas = notas or None
        db.session.commit()

        flash('Pedido actualizado.', 'success')
        return redirect(url_for('pedidos.detalle', id=id))

    return render_template('pedidos/form.html',
                           clientes=clientes, zapaterias=zapaterias,
                           cliente_presel=pedido.cliente,
                           form_data=None, pedido=pedido)


# ---------------------------------------------------------------------------
# Avanzar estatus: pendiente → comprado → entregado
# ---------------------------------------------------------------------------
@pedidos_bp.route('/<int:id>/avanzar', methods=['POST'])
@login_required
def avanzar(id):
    pedido = Pedido.query.get_or_404(id)
    origen = request.form.get('origen', 'detalle')

    if pedido.estatus == 'pendiente':
        pedido.estatus = 'comprado'
        db.session.commit()
        flash('Pedido marcado como comprado.', 'success')
    elif pedido.estatus == 'comprado':
        pedido.marcar_entregado()
        db.session.commit()
        flash(
            f'Pedido entregado. Se cargaron ${pedido.precio_venta:.0f} al saldo de {pedido.cliente.nombre}.',
            'success'
        )
    else:
        flash('Este pedido no puede avanzar de estatus.', 'warning')

    if origen == 'lista':
        return redirect(url_for('pedidos.lista'))
    return redirect(url_for('pedidos.detalle', id=id))


# ---------------------------------------------------------------------------
# Cancelar pedido
# ---------------------------------------------------------------------------
@pedidos_bp.route('/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar(id):
    pedido = Pedido.query.get_or_404(id)
    origen = request.form.get('origen', 'detalle')

    if pedido.estatus in ('entregado', 'cancelado', 'devuelto'):
        flash('No se puede cancelar este pedido.', 'warning')
        return redirect(url_for('pedidos.detalle', id=id))

    motivo = request.form.get('motivo', '').strip()
    pedido.estatus = 'cancelado'
    if motivo:
        pedido.notas = f'Cancelado: {motivo}'

    db.session.commit()
    flash('Pedido cancelado.', 'info')

    if origen == 'lista':
        return redirect(url_for('pedidos.lista'))
    return redirect(url_for('pedidos.detalle', id=id))


# ---------------------------------------------------------------------------
# Devolver pedido entregado
# ---------------------------------------------------------------------------
@pedidos_bp.route('/<int:id>/devolver', methods=['POST'])
@login_required
def devolver(id):
    pedido = Pedido.query.get_or_404(id)

    if pedido.estatus != 'entregado':
        flash('Solo se pueden devolver pedidos entregados.', 'warning')
        return redirect(url_for('pedidos.detalle', id=id))

    tipo = request.form.get('tipo', 'devolucion')
    TIPOS = {
        'devolucion': 'Devolución (no se repone)',
        'cambio_talla': 'Cambio por talla',
        'cambio_defecto': 'Cambio por defecto de fábrica',
    }
    motivo_label = TIPOS.get(tipo, 'Devolución')

    # Revertir el cargo al saldo
    if pedido.cliente.cuenta:
        pedido.cliente.cuenta.aplicar_abono(pedido.precio_venta)

    pedido.estatus = 'devuelto'
    pedido.notas = motivo_label

    nuevo_pedido = None
    if tipo in ('cambio_talla', 'cambio_defecto'):
        nueva_talla = request.form.get('nueva_talla', '').strip() if tipo == 'cambio_talla' else None
        nuevo_pedido = Pedido(
            cliente_id=pedido.cliente_id,
            zapateria_id=pedido.zapateria_id,
            descripcion=pedido.descripcion,
            codigo_producto=pedido.codigo_producto,
            color=pedido.color,
            talla=nueva_talla if nueva_talla else pedido.talla,
            precio_catalogo=pedido.precio_catalogo,
            precio_venta=pedido.precio_venta,
            notas=f'Reposición por {motivo_label} — pedido original #{pedido.id}',
        )
        db.session.add(nuevo_pedido)

    db.session.commit()

    msg = f'Devolución registrada. Se descontaron ${pedido.precio_venta:.0f} del saldo de {pedido.cliente.nombre}.'
    if nuevo_pedido:
        msg += f' Nuevo pedido #{nuevo_pedido.id} creado automáticamente.'
    flash(msg, 'info')

    origen = request.form.get('origen', 'detalle')
    if nuevo_pedido:
        return redirect(url_for('pedidos.detalle', id=nuevo_pedido.id))
    if origen == 'cliente':
        return redirect(url_for('clientes.detalle', id=pedido.cliente_id))
    return redirect(url_for('pedidos.detalle', id=id))


# ---------------------------------------------------------------------------
# Exportar PDF por zapatería
# ---------------------------------------------------------------------------
@pedidos_bp.route('/exportar-pdf')
@login_required
def exportar_pdf():
    zapateria_id = request.args.get('zapateria_id', type=int)
    rango = request.args.get('rango', 'hoy')
    estatus = request.args.get('estatus', 'activos')

    hoy = date.today()
    if rango == 'semana':
        fecha_inicio = hoy - timedelta(days=hoy.weekday())
    else:
        fecha_inicio = hoy

    query = Pedido.query.join(Pedido.cliente).filter(Cliente.es_sucursal == False)

    if estatus == 'activos':
        query = query.filter(Pedido.estatus.in_(['pendiente', 'comprado']))
    elif estatus in Pedido.ESTATUS:
        query = query.filter(Pedido.estatus == estatus)

    if zapateria_id:
        query = query.filter(Pedido.zapateria_id == zapateria_id)

    query = query.filter(func.date(Pedido.fecha_pedido) >= fecha_inicio)

    pedidos = query.order_by(Pedido.fecha_pedido.asc()).all()

    zapateria = Zapateria.query.get(zapateria_id) if zapateria_id else None

    html = render_template('pedidos/pdf.html',
                           pedidos=pedidos,
                           zapateria=zapateria,
                           rango=rango,
                           fecha_inicio=fecha_inicio,
                           hoy=hoy,
                           estatus=estatus)

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    pdf = buffer.getvalue()

    nombre_zap = zapateria.nombre.replace(' ', '_') if zapateria else 'todos'
    nombre_archivo = f"pedidos_{nombre_zap}_{hoy}.pdf"

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    return response
