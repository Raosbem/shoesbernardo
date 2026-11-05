"""Branch deliveries: all monetary transitions share the customer's transaction lock."""
import json
from hashlib import sha256

from app import db
from app.models import (Cliente, Cuenta, PedidoSucursal, SolicitudSucursal, Zapateria,
                        TicketSucursal, DetalleTicketSucursal, DevolucionSucursal,
                        ValeSucursal, UsoValeSucursal)
from app.utils import money, today, utc_now, lock_customer


class BranchError(ValueError):
    pass


def percentage(value):
    try:
        result = money(value)
        if not 0 <= result <= 100:
            raise ValueError
        return result
    except ValueError:
        raise BranchError('El porcentaje debe estar entre 0 y 100.') from None


def available_vouchers(branch_id):
    return sum((vale.disponible for vale in ValeSucursal.query.filter_by(sucursal_id=branch_id)), money(0))


def request_articles(raw):
    try:
        articles = json.loads(raw)
    except (ValueError, TypeError):
        raise BranchError('No se pudieron leer los artículos.') from None
    if not isinstance(articles, list) or not 1 <= len(articles) <= 50:
        raise BranchError('Agrega entre 1 y 50 artículos.')
    result = []
    for index, article in enumerate(articles, 1):
        if not isinstance(article, dict):
            raise BranchError(f'Artículo {index}: revisa los datos.')
        cleaned = {}
        for field, limit in {'zapateria_id': 10, 'codigo': 50, 'color': 50, 'talla': 10,
                             'descripcion': 200, 'notas': 200, 'precio_referencia': 30}.items():
            value = article.get(field, '')
            if not isinstance(value, (str, int)) or isinstance(value, bool) or len(str(value)) > limit:
                raise BranchError(f'Artículo {index}: revisa el campo {field}.')
            cleaned[field] = str(value).strip()
        shop_id = cleaned['zapateria_id']
        if not shop_id.isascii() or not shop_id.isdecimal() or not 0 < int(shop_id) <= 2147483647:
            raise BranchError(f'Artículo {index}: selecciona una zapatería.')
        shop = Zapateria.query.filter_by(id=int(shop_id), activa=True).first()
        if not shop or not cleaned['codigo']:
            raise BranchError(f'Artículo {index}: selecciona una zapatería activa y captura el código.')
        try:
            price = money(cleaned['precio_referencia']) if cleaned['precio_referencia'] else None
            if price is not None and price < 0:
                raise ValueError
        except ValueError:
            raise BranchError(f'Artículo {index}: revisa el precio de referencia.') from None
        result.append(PedidoSucursal(zapateria_id=shop.id, codigo_producto=cleaned['codigo'],
            descripcion=cleaned['descripcion'], color=cleaned['color'] or None, notas=cleaned['notas'] or None,
            talla=cleaned['talla'] or None, precio_referencia=price,
            precio_base=money(0), precio_final=money(0), descuento=money(0),
            semana=today().strftime('%G-W%V')))
    return result


def save_request(branch, user_id, raw, send, existing=None):
    lock_customer(branch)
    db.session.refresh(branch)
    if not branch.activo:
        raise BranchError('Esta sucursal está desactivada.')
    if existing:
        db.session.refresh(existing)
        if existing.sucursal_id != branch.id or existing.estado != 'borrador':
            raise BranchError('El pedido ya fue enviado y no se puede modificar.')
    articles = request_articles(raw)
    batch = existing or SolicitudSucursal(sucursal_id=branch.id, creado_por=user_id)
    batch.estado = 'enviado' if send else 'borrador'
    batch.fecha_envio = utc_now() if send else None
    for article in articles:
        article.sucursal_id = branch.id
        article.estatus = 'pendiente' if send else 'borrador'
    batch.articulos = articles
    db.session.add(batch)
    db.session.commit()
    return batch


def begin_delivery(branch, ids, user_id):
    lock_customer(branch)
    if not ids or len(ids) > 100 or len(ids) != len(set(ids)):
        raise BranchError('Selecciona los artículos que vas a entregar.')
    orders = PedidoSucursal.query.filter(PedidoSucursal.id.in_(ids), PedidoSucursal.sucursal_id == branch.id).all()
    for order in orders:
        db.session.refresh(order)
    if len(orders) != len(ids) or any(p.estatus != 'recibido' or p.detalle_ticket for p in orders):
        raise BranchError('Selecciona solo artículos recibidos que no estén en otra entrega.')
    ticket = TicketSucursal(sucursal_id=branch.id, sucursal_nombre=branch.nombre,
                            creado_por=user_id, comision_pct=branch.comision_pct)
    for order in orders:
        ticket.lineas.append(DetalleTicketSucursal(pedido_id=order.id, tienda=order.zapateria.nombre,
            codigo=order.codigo_producto or '', descripcion=order.descripcion,
            color=order.color, talla=order.talla))
    db.session.add(ticket)
    db.session.commit()
    return ticket


def lock_delivery(ticket):
    lock_customer(ticket.sucursal)
    db.session.refresh(ticket)
    if ticket.estado != 'borrador':
        raise BranchError('Esta entrega ya fue confirmada o cancelada.')


def delivery_signature(ticket):
    values = [ticket.id, ticket.comision_pct, ticket.subtotal, ticket.comision,
              ticket.vale_aplicado, ticket.total,
              [(l.id, l.precio, l.descuento_pct, l.neto, l.comision) for l in ticket.lineas]]
    return sha256(json.dumps(values, default=str).encode('utf-8')).hexdigest()


def price_delivery(ticket, form):
    lock_delivery(ticket)
    db.session.refresh(ticket.sucursal)
    rate = ticket.sucursal.comision_pct
    values = []
    for line in ticket.lineas:
        try:
            price = money(form.get(f'precio_{line.id}', ''))
            discount = percentage(form.get(f'descuento_{line.id}', ''))
            if price <= 0:
                raise ValueError
        except ValueError:
            raise BranchError(f'Captura un precio mayor a cero y un descuento de 0 a 100 para {line.codigo}.') from None
        net = money(price * (1 - discount / 100))
        values.append((line, price, discount, net))
    try:
        subtotal = money(sum((v[3] for v in values), money(0)))
        commission = money(subtotal * rate / 100)
        total = money(subtotal + commission)
        credit = money(form.get('vale_aplicar', '0') or '0')
    except ValueError:
        raise BranchError('Revisa los importes de la entrega.') from None
    if credit < 0 or credit > total or credit > available_vouchers(ticket.sucursal_id):
        raise BranchError('El vale aplicado no puede superar el total ni los vales disponibles.')
    accumulated, previous_fee = money(0), money(0)
    for line, price, discount, net in values:
        accumulated += net
        cumulative_fee = money(accumulated * rate / 100)
        fee = cumulative_fee - previous_fee
        previous_fee = cumulative_fee
        line.precio, line.descuento_pct, line.neto, line.comision = price, discount, net, fee
    ticket.comision_pct = rate
    ticket.subtotal, ticket.comision = subtotal, commission
    ticket.vale_aplicado, ticket.total = credit, money(total - credit)
    ticket.revisado = True
    db.session.commit()


def confirm_delivery(ticket, user_id, reviewed_signature):
    lock_customer(ticket.sucursal)
    db.session.refresh(ticket)
    if ticket.estado == 'confirmado':
        return ticket
    if ticket.estado != 'borrador' or not ticket.revisado:
        raise BranchError('Revisa los precios antes de confirmar la entrega.')
    db.session.expire(ticket, ['lineas'])
    for line in ticket.lineas:
        db.session.refresh(line)
    if reviewed_signature != delivery_signature(ticket):
        raise BranchError('Los importes de esta preparación cambiaron. Revísalos antes de confirmar.')
    db.session.refresh(ticket.sucursal)
    if ticket.comision_pct != ticket.sucursal.comision_pct:
        raise BranchError('La comisión de la sucursal cambió. Vuelve a revisar esta entrega.')
    if ticket.vale_aplicado > available_vouchers(ticket.sucursal_id):
        raise BranchError('Cambió el saldo de los vales. Vuelve a revisar esta entrega.')
    for line in ticket.lineas:
        db.session.refresh(line.pedido)
        if line.pedido.estatus != 'recibido':
            raise BranchError('Uno de los artículos ya no está disponible para entrega.')
    remaining = ticket.vale_aplicado
    for vale in ValeSucursal.query.filter_by(sucursal_id=ticket.sucursal_id).order_by(ValeSucursal.fecha, ValeSucursal.id):
        use = min(remaining, vale.disponible)
        if use > 0:
            db.session.add(UsoValeSucursal(vale_id=vale.id, ticket_id=ticket.id, monto=use))
            remaining -= use
        if remaining == 0:
            break
    if remaining != 0:
        raise BranchError('No se pudo aplicar el vale. Revisa la entrega.')
    for line in ticket.lineas:
        order = line.pedido
        order.precio_base, order.descuento, order.precio_final = line.precio, line.descuento_pct, line.neto
        order.estatus, order.fecha_entrega = 'entregado', utc_now()
    branch = ticket.sucursal
    if not branch.cuenta:
        branch.cuenta = Cuenta(saldo_total=money(0))
    new_balance = money(branch.saldo + ticket.total)
    branch.cuenta.saldo_total = new_balance
    ticket.estado = 'confirmado'
    ticket.fecha_confirmacion, ticket.confirmado_por = utc_now(), user_id
    db.session.commit()
    return ticket


def request_return(order, user_id, reason):
    lock_customer(order.sucursal)
    db.session.refresh(order)
    if order.estatus != 'entregado' or order.devolucion:
        raise BranchError('Este artículo ya tiene una devolución o todavía no se ha entregado.')
    if not reason or len(reason) > 200:
        raise BranchError('Escribe el motivo de devolución (hasta 200 caracteres).')
    result = DevolucionSucursal(sucursal_id=order.sucursal_id, pedido_id=order.id,
        motivo=reason, solicitado_por=user_id, estado='solicitada')
    db.session.add(result)
    db.session.commit()
    return result


def resolve_return(devolution, user_id, approve, response=''):
    lock_customer(devolution.sucursal)
    db.session.refresh(devolution)
    if devolution.estado != 'solicitada':
        raise BranchError('Esta devolución ya fue resuelta.')
    if len(response) > 200 or (not approve and not response.strip()):
        raise BranchError('Escribe el motivo del rechazo (hasta 200 caracteres).')
    order = devolution.pedido
    db.session.refresh(order)
    if order.estatus != 'entregado':
        raise BranchError('El artículo no está disponible para devolución.')
    if approve:
        # Credit is consumed only on a future ticket: do not also reduce old debt.
        amount = order.detalle_ticket.neto if order.detalle_ticket else order.precio_final
        if amount <= 0:
            raise BranchError('Este artículo no tiene importe para generar un vale.')
        devolution.vale = ValeSucursal(sucursal_id=order.sucursal_id, monto=amount)
        order.estatus = 'devuelto'
    devolution.estado = 'aprobada' if approve else 'rechazada'
    devolution.fecha_resolucion, devolution.resuelto_por = utc_now(), user_id
    devolution.respuesta = response.strip() or 'Producto recibido; vale generado sin comisión.'
    db.session.commit()
