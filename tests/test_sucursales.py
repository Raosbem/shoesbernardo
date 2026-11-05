import json
import unittest
from flask import g

from app import create_app, db
from app.models import (Usuario, Cliente, Cuenta, Zapateria, SolicitudSucursal, PedidoSucursal,
    TicketSucursal, DetalleTicketSucursal, DevolucionSucursal, ValeSucursal, UsoValeSucursal, Abono)
from app.utils import money


class BranchFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'branch-tests',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'WTF_CSRF_ENABLED': False})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.admin = Usuario(nombre='Admin', username='admin', rol='admin', password_hash='unused')
        self.helper = Usuario(nombre='Ayudante', username='helper', rol='ayudante', password_hash='unused')
        self.branch = Cliente(nombre='Ire', es_sucursal=True, comision_pct=money(5), cuenta=Cuenta(saldo_total=money(0)))
        self.other = Cliente(nombre='Otra sucursal', es_sucursal=True, comision_pct=money(10), cuenta=Cuenta(saldo_total=money(0)))
        self.user = Usuario(nombre='Ire', username='ire', rol='sucursal', sucursal=self.branch, password_hash='unused')
        self.other_user = Usuario(nombre='Otra', username='otra', rol='sucursal', sucursal=self.other, password_hash='unused')
        self.shop = Zapateria(nombre='Andrea')
        db.session.add_all([self.admin, self.helper, self.branch, self.other, self.user, self.other_user, self.shop])
        db.session.commit()
        self.staff = self.app.test_client()
        self.portal = self.app.test_client()
        self.second = self.app.test_client()
        for client, user in [(self.staff, self.admin), (self.portal, self.user), (self.second, self.other_user)]:
            with client.session_transaction() as session:
                session['_user_id'] = str(user.id)
                session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def http(self, client, method, path, **kwargs):
        g.pop('_login_user', None)
        return getattr(client, method)(path, **kwargs)

    def article(self, **changes):
        data = {'zapateria_id': str(self.shop.id), 'codigo': 'AND-001', 'talla': '25', 'color': 'Negro', 'notas': 'Avisar al llegar'}
        data.update(changes)
        return data

    def send(self, articles=None, draft=False):
        response = self.http(self.portal, 'post', '/mi-sucursal/pedido', data={
            'articulos': json.dumps(articles or [self.article()]), 'intencion': 'borrador' if draft else 'enviar'})
        self.assertEqual(response.status_code, 302)
        return SolicitudSucursal.query.order_by(SolicitudSucursal.id.desc()).first()

    def receive(self, order):
        for state in ('pendiente', 'comprado'):
            response = self.http(self.staff, 'post', f'/sucursales/{order.sucursal_id}/pedido/{order.id}/avanzar', data={'estatus_actual': state})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(order.estatus, 'recibido')

    def prepare(self, orders):
        response = self.http(self.staff, 'post', f'/sucursales/{orders[0].sucursal_id}/preparar',
            data={'pedidos': [str(order.id) for order in orders]})
        self.assertEqual(response.status_code, 302)
        return TicketSucursal.query.order_by(TicketSucursal.id.desc()).first()

    def review(self, ticket, price='1000', discount='30', credit='0'):
        data = {'vale_aplicar': credit}
        for line in ticket.lineas:
            data[f'precio_{line.id}'], data[f'descuento_{line.id}'] = price, discount
        return self.http(self.staff, 'post', f'/sucursales/entregas/{ticket.id}/preparar', data=data)

    def confirm(self, ticket):
        from app.sucursales.services import delivery_signature
        return self.http(self.staff, 'post', f'/sucursales/entregas/{ticket.id}/confirmar', data={'revision': delivery_signature(ticket)})

    def delivered_ticket(self, price='1000', discount='30'):
        order = self.send().articulos[0]
        self.receive(order)
        ticket = self.prepare([order])
        self.review(ticket, price, discount)
        self.confirm(ticket)
        return ticket

    def return_credit(self, order):
        self.http(self.portal, 'post', f'/mi-sucursal/articulos/{order.id}/devolver', data={'motivo': 'No quedó la talla'})
        result = DevolucionSucursal.query.filter_by(pedido_id=order.id).one()
        self.http(self.staff, 'post', f'/sucursales/devoluciones/{result.id}/resolver', data={'accion': 'aprobar'})
        return result.vale

    def test_draft_send_and_staff_queue(self):
        batch = self.send([self.article(), self.article(codigo='SECOND')], draft=True)
        self.assertEqual(batch.estado, 'borrador')
        self.assertTrue(all(p.estatus == 'borrador' for p in batch.articulos))
        html = self.http(self.staff, 'get', '/pedidos/bandeja').get_data(as_text=True)
        self.assertNotIn('AND-001', html)
        self.assertEqual(self.http(self.staff, 'get', f'/sucursales/solicitudes/{batch.id}').status_code, 404)
        result = self.http(self.portal, 'post', f'/mi-sucursal/solicitudes/{batch.id}/editar', data={
            'articulos': json.dumps([self.article()]), 'intencion': 'enviar'})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(batch.estado, 'enviado')
        self.assertEqual(len(batch.articulos), 1)
        self.assertEqual(batch.articulos[0].notas, 'Avisar al llegar')
        self.assertIn('AND-001', self.http(self.staff, 'get', '/pedidos/bandeja').get_data(as_text=True))
        self.assertEqual(self.branch.saldo, money(0))
        self.http(self.portal, 'post', f'/mi-sucursal/solicitudes/{batch.id}/editar', data={'articulos': json.dumps([self.article(codigo='CHANGED')]), 'intencion': 'enviar'})
        self.assertEqual(batch.articulos[0].codigo_producto, 'AND-001')

    def test_delivery_manual_prices_commission_and_idempotence(self):
        ticket = self.delivered_ticket()
        self.assertEqual(ticket.subtotal, money(700))
        self.assertEqual(ticket.comision, money(35))
        self.assertEqual(ticket.total, money(735))
        self.assertEqual(self.branch.saldo, money(735))
        self.confirm(ticket)
        self.assertEqual(self.branch.saldo, money(735))
        self.assertEqual(ticket.lineas[0].pedido.estatus, 'entregado')

    def test_partial_delivery_and_no_charge_before_confirmation(self):
        batch = self.send([self.article(), self.article(codigo='LATER')])
        self.receive(batch.articulos[0])
        ticket = self.prepare([batch.articulos[0]])
        self.review(ticket)
        self.assertEqual(self.branch.saldo, money(0))
        self.assertEqual(batch.articulos[0].estatus, 'recibido')
        self.assertEqual(batch.articulos[1].estatus, 'pendiente')
        self.assertEqual(self.http(self.portal, 'get', f'/mi-sucursal/tickets/{ticket.id}').status_code, 404)
        self.confirm(ticket)
        self.assertEqual(self.branch.saldo, money(735))
        self.assertEqual(batch.articulos[1].estatus, 'pendiente')

    def test_invalid_prices_preserve_inputs_and_cannot_confirm(self):
        order = self.send().articulos[0]
        self.receive(order)
        ticket = self.prepare([order])
        for price, discount in [('nan', '10'), ('0', '10'), ('100', ''), ('100', '101')]:
            response = self.review(ticket, price, discount)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(ticket.revisado)
            self.assertEqual(self.branch.saldo, money(0))
        self.confirm(ticket)
        self.assertEqual(ticket.estado, 'borrador')

    def test_duplicate_reservation_and_cancel_release(self):
        order = self.send().articulos[0]
        self.receive(order)
        ticket = self.prepare([order])
        self.prepare([order])
        self.assertEqual(TicketSucursal.query.count(), 1)
        self.http(self.staff, 'post', f'/sucursales/entregas/{ticket.id}/cancelar')
        self.assertEqual(ticket.estado, 'cancelado')
        self.assertEqual(DetalleTicketSucursal.query.count(), 0)
        self.assertEqual(order.estatus, 'recibido')
        second = self.prepare([order])
        self.assertNotEqual(second.id, ticket.id)

    def test_ticket_snapshot_and_commission_changes(self):
        ticket = self.delivered_ticket()
        self.branch.comision_pct = money(10)
        self.branch.nombre = 'Nuevo nombre'
        self.shop.nombre = 'Otra tienda'
        db.session.commit()
        self.assertEqual(ticket.comision_pct, money(5))
        self.assertEqual(ticket.sucursal_nombre, 'Ire')
        self.assertEqual(ticket.lineas[0].tienda, 'Andrea')
        self.assertEqual(ticket.total, money(735))
        # A reviewed draft must be reviewed again if configuration changes.
        order = self.send().articulos[0]
        self.receive(order)
        draft = self.prepare([order])
        self.review(draft)
        self.branch.comision_pct = money(15)
        db.session.commit()
        self.confirm(draft)
        self.assertEqual(draft.estado, 'borrador')
        self.assertEqual(self.branch.saldo, money(735))

    def test_return_requires_receipt_and_excludes_commission(self):
        ticket = self.delivered_ticket()
        order = ticket.lineas[0].pedido
        self.http(self.portal, 'post', f'/mi-sucursal/articulos/{order.id}/devolver', data={'motivo': 'Talla'})
        result = DevolucionSucursal.query.one()
        self.assertEqual(ValeSucursal.query.count(), 0)
        self.assertEqual(order.estatus, 'entregado')
        self.http(self.staff, 'post', f'/sucursales/devoluciones/{result.id}/resolver', data={'accion': 'aprobar'})
        self.assertEqual(result.vale.monto, money(700))
        self.assertEqual(order.estatus, 'devuelto')
        self.assertEqual(ticket.total, money(735))
        self.assertEqual(self.branch.saldo, money(735))
        for _ in range(2):
            self.http(self.staff, 'post', f'/sucursales/devoluciones/{result.id}/resolver', data={'accion': 'aprobar'})
        self.assertEqual(ValeSucursal.query.count(), 1)

    def test_voucher_application_partial_remainder_and_once(self):
        original = self.delivered_ticket()
        voucher = self.return_credit(original.lineas[0].pedido)
        new = self.send().articulos[0]
        self.receive(new)
        delivery = self.prepare([new])
        self.review(delivery, '500', '0', '200')
        self.assertEqual(voucher.disponible, money(700))
        self.confirm(delivery)
        self.confirm(delivery)
        self.assertEqual(delivery.total, money(325))
        self.assertEqual(self.branch.saldo, money(1060))
        self.assertEqual(voucher.disponible, money(500))
        self.assertEqual(UsoValeSucursal.query.count(), 1)

    def test_voucher_insufficient_on_second_reviewed_ticket(self):
        voucher = self.return_credit(self.delivered_ticket().lineas[0].pedido)
        orders = self.send([self.article(), self.article(codigo='OTHER')]).articulos
        tickets = []
        for order in orders:
            self.receive(order)
            ticket = self.prepare([order])
            self.review(ticket, '1000', '0', '600')
            tickets.append(ticket)
        self.confirm(tickets[0])
        balance = self.branch.saldo
        self.confirm(tickets[1])
        self.assertEqual(tickets[1].estado, 'borrador')
        self.assertEqual(self.branch.saldo, balance)
        self.assertEqual(voucher.disponible, money(100))

    def test_rejected_return_no_voucher(self):
        order = self.delivered_ticket().lineas[0].pedido
        self.http(self.portal, 'post', f'/mi-sucursal/articulos/{order.id}/devolver', data={'motivo': 'No quedó'})
        result = DevolucionSucursal.query.one()
        self.http(self.staff, 'post', f'/sucursales/devoluciones/{result.id}/resolver', data={'accion': 'rechazar'})
        self.assertEqual(result.estado, 'solicitada')
        self.http(self.staff, 'post', f'/sucursales/devoluciones/{result.id}/resolver', data={'accion': 'rechazar', 'respuesta': 'Fuera del plazo'})
        self.assertEqual(result.estado, 'rechazada')
        self.assertEqual(ValeSucursal.query.count(), 0)
        self.assertEqual(order.estatus, 'entregado')

    def test_scope_all_admin_endpoints_denied_and_other_branch_hidden(self):
        ticket = self.delivered_ticket()
        batch = SolicitudSucursal.query.one()
        for path in ['/', '/clientes/', '/pedidos/bandeja', '/sucursales/', '/reportes/', '/abonos/']:
            response = self.http(self.portal, 'get', path)
            self.assertEqual(response.status_code, 302 if path == '/' else 403, path)
        for path in [f'/sucursales/entregas/{ticket.id}/confirmar', f'/sucursales/{self.branch.id}/abonar',
                     f'/sucursales/{self.branch.id}/acceso', f'/sucursales/{self.branch.id}/editar']:
            self.assertEqual(self.http(self.portal, 'post', path, data={'monto': '1'}).status_code, 403, path)
        for path in [f'/mi-sucursal/tickets/{ticket.id}', f'/mi-sucursal/tickets/{ticket.id}/pdf',
                     f'/mi-sucursal/solicitudes/{batch.id}', f'/mi-sucursal/solicitudes/{batch.id}/editar',
                     f'/mi-sucursal/articulos/{ticket.lineas[0].pedido_id}/devolver']:
            self.assertEqual(self.http(self.second, 'get', path).status_code, 404, path)

    def test_portal_and_staff_screens_and_pdf(self):
        ticket = self.delivered_ticket()
        self.return_credit(ticket.lineas[0].pedido)
        for path in ['/mi-sucursal/', '/mi-sucursal/pedido', '/mi-sucursal/tickets', '/mi-sucursal/vales',
                     '/mi-sucursal/devoluciones', '/mi-sucursal/pagos', f'/mi-sucursal/tickets/{ticket.id}']:
            self.assertEqual(self.http(self.portal, 'get', path).status_code, 200, path)
        for path in ['/pedidos/bandeja', '/pedidos/bandeja?tipo=sucursales', f'/pedidos/bandeja?sucursal_id={self.branch.id}',
                     '/sucursales/devoluciones', f'/sucursales/{self.branch.id}/acceso', f'/sucursales/tickets/{ticket.id}',
                     f'/sucursales/{self.branch.id}?tab=vales', f'/sucursales/{self.branch.id}?tab=pagos']:
            self.assertEqual(self.http(self.staff, 'get', path).status_code, 200, path)
        pdf = self.http(self.portal, 'get', f'/mi-sucursal/tickets/{ticket.id}/pdf')
        self.assertTrue(pdf.data.startswith(b'%PDF'))

    def test_payments_ticket_allocation_and_annulment(self):
        first = self.delivered_ticket()
        second = self.delivered_ticket()
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/abonar', data={'monto': '800'})
        self.assertEqual(first.pendiente, money(0))
        self.assertEqual(second.pendiente, money(670))
        self.assertEqual(self.branch.saldo, money(670))
        payment = Abono.query.filter_by(ticket_id=first.id).one()
        self.http(self.staff, 'post', f'/abonos/{payment.id}/eliminar')
        self.assertEqual(first.pendiente, money(735))
        self.assertEqual(self.branch.saldo, money(1405))
        before = Abono.query.count()
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/abonar', data={'monto': '800', 'ticket_id': str(first.id)})
        self.assertEqual(Abono.query.count(), before)

    def test_account_setup_commission_and_inactive_access(self):
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/editar', data={'nombre': 'Ire', 'comision_pct': '7.5'})
        self.assertEqual(self.branch.comision_pct, money('7.50'))
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/acceso', data={'username': 'ire-nueva', 'password': 'new-password-123', 'activo': '1'})
        self.assertTrue(self.user.check_password('new-password-123'))
        self.assertEqual(self.user.username, 'ire-nueva')
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/desactivar')
        self.assertEqual(self.http(self.portal, 'get', '/mi-sucursal/').status_code, 302)
        self.http(self.staff, 'post', f'/sucursales/{self.branch.id}/reactivar')
        self.assertEqual(self.http(self.portal, 'get', '/mi-sucursal/').status_code, 200)

    def test_non_admin_cannot_configure_commission_or_accept_returns(self):
        order = self.delivered_ticket().lineas[0].pedido
        self.http(self.portal, 'post', f'/mi-sucursal/articulos/{order.id}/devolver', data={'motivo': 'Talla'})
        helper = self.app.test_client()
        with helper.session_transaction() as session:
            session['_user_id'] = str(self.helper.id)
        for path in [f'/sucursales/{self.branch.id}/acceso', f'/sucursales/{self.branch.id}/editar',
                     f'/sucursales/devoluciones/{DevolucionSucursal.query.one().id}/resolver']:
            self.assertEqual(self.http(helper, 'post', path, data={'accion': 'aprobar'}).status_code, 403)

    def test_return_of_old_delivered_product(self):
        order = PedidoSucursal(sucursal_id=self.branch.id, zapateria_id=self.shop.id,
            codigo_producto='ANTERIOR', descripcion='Histórico', precio_base=money(100),
            descuento=money(10), precio_final=money(90), estatus='entregado')
        db.session.add(order)
        db.session.commit()
        voucher = self.return_credit(order)
        self.assertEqual(voucher.monto, money(90))
        self.assertEqual(self.branch.saldo, money(0))

    def test_stale_delivery_review_cannot_confirm_changed_prices(self):
        from app.sucursales.services import delivery_signature
        order = self.send().articulos[0]
        self.receive(order)
        ticket = self.prepare([order])
        self.review(ticket)
        old_review = delivery_signature(ticket)
        self.review(ticket, '2000', '0')
        self.http(self.staff, 'post', f'/sucursales/entregas/{ticket.id}/confirmar', data={'revision': old_review})
        self.assertEqual(ticket.estado, 'borrador')
        self.assertEqual(self.branch.saldo, money(0))

    def test_commission_rounded_on_net_subtotal(self):
        orders = self.send([self.article(), self.article(codigo='SECOND')]).articulos
        for order in orders:
            self.receive(order)
        ticket = self.prepare(orders)
        self.review(ticket, '100.05', '0')
        self.assertEqual(ticket.subtotal, money('200.10'))
        self.assertEqual(ticket.comision, money('10.01'))
        self.assertEqual(sum(line.comision for line in ticket.lineas), money('10.01'))


class BranchConcurrencyTests(unittest.TestCase):
    def test_two_deliveries_cannot_spend_same_voucher(self):
        import tempfile
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from app.sucursales.services import begin_delivery, price_delivery, delivery_signature
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'concurrent-branches',
                'WTF_CSRF_ENABLED': False, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'concurrent.db').as_posix()})
            with app.app_context():
                db.create_all()
                admin = Usuario(nombre='Admin', username='admin', rol='admin', password_hash='unused')
                branch = Cliente(nombre='Ire', es_sucursal=True, comision_pct=money(5), cuenta=Cuenta(saldo_total=money(0)))
                shop = Zapateria(nombre='Andrea')
                db.session.add_all([admin, branch, shop])
                db.session.flush()
                original = PedidoSucursal(sucursal_id=branch.id, zapateria_id=shop.id, descripcion='Anterior',
                    precio_base=money(1000), precio_final=money(700), estatus='devuelto')
                db.session.add(original)
                db.session.flush()
                devolution = DevolucionSucursal(sucursal_id=branch.id, pedido_id=original.id,
                    motivo='Anterior', estado='aprobada', solicitado_por=admin.id, resuelto_por=admin.id)
                devolution.vale = ValeSucursal(sucursal_id=branch.id, monto=money(700))
                db.session.add(devolution)
                orders = [PedidoSucursal(sucursal_id=branch.id, zapateria_id=shop.id, descripcion='Nuevo',
                    codigo_producto=str(n), precio_base=money(0), precio_final=money(0), estatus='recibido') for n in range(2)]
                db.session.add_all(orders)
                db.session.commit()
                uid, bid = admin.id, branch.id
                pending = []
                for order in orders:
                    ticket = begin_delivery(branch, [order.id], uid)
                    line = ticket.lineas[0]
                    price_delivery(ticket, {f'precio_{line.id}': '1000', f'descuento_{line.id}': '0', 'vale_aplicar': '600'})
                    pending.append((ticket.id, delivery_signature(ticket)))
            def confirm(data):
                with app.test_client() as client:
                    with client.session_transaction() as session:
                        session['_user_id'] = str(uid)
                    return client.post(f'/sucursales/entregas/{data[0]}/confirmar', data={'revision': data[1]}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(confirm, pending)), [302, 302])
            with app.app_context():
                self.assertEqual(TicketSucursal.query.filter_by(estado='confirmado').count(), 1)
                self.assertEqual(UsoValeSucursal.query.count(), 1)
                self.assertEqual(ValeSucursal.query.one().disponible, money(100))
                self.assertEqual(db.session.get(Cliente, bid).saldo, money(450))
                db.session.remove()
                db.engine.dispose()
