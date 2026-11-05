import re
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app import create_app, db
from app.models import Usuario, Cliente, Cuenta, Zapateria, Pedido, PedidoSucursal, Abono, Cargo
from app.utils import money, today, day_range


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-key',
                               'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
                               'WTF_CSRF_ENABLED': False})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.admin = Usuario(nombre='Admin', username='admin', rol='admin')
        self.admin.set_password('password-test-123')
        self.helper = Usuario(nombre='Ayudante', username='helper', rol='ayudante')
        self.helper.set_password('password-test-123')
        self.customer = Cliente(nombre='Cliente', es_sucursal=False, cuenta=Cuenta(saldo_total=money(0)))
        self.branch = Cliente(nombre='Sucursal', es_sucursal=True, cuenta=Cuenta(saldo_total=money(0)))
        self.shop = Zapateria(nombre='Catálogo', activa=True)
        db.session.add_all([self.admin, self.helper, self.customer, self.branch, self.shop])
        db.session.commit()
        self.client = self.app.test_client()
        self.login()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def login(self, username='admin', suffix=''):
        return self.client.post('/auth/login'+suffix, data={'username': username, 'password': 'password-test-123'})

    def order(self, amount='100'):
        response = self.client.post('/pedidos/nuevo', data={'cliente_id': self.customer.id,
            'zapateria_id': self.shop.id, 'codigo': 'ABC', 'descripcion': 'Zapatos', 'precio_venta': amount})
        self.assertEqual(response.status_code, 302)
        return Pedido.query.order_by(Pedido.id.desc()).first()

    def deliver(self, order):
        for state in ('pendiente', 'comprado'):
            self.client.post(f'/pedidos/{order.id}/avanzar', data={'estatus_actual': state})

    def payment(self, amount):
        return self.client.post('/abonos/nuevo', data={'cliente_id': self.customer.id, 'monto': amount})

    def test_delivery_and_payment(self):
        order = self.order('100.25')
        self.deliver(order)
        self.payment('40.10')
        self.assertEqual(self.customer.saldo, Decimal('60.15'))
        self.client.post(f'/pedidos/{order.id}/avanzar', data={'estatus_actual': 'comprado'})
        self.assertEqual(self.customer.saldo, Decimal('60.15'))

    def test_exchange_preserves_previous_payment(self):
        order = self.order()
        self.deliver(order)
        self.payment('40')
        self.client.post(f'/pedidos/{order.id}/devolver', data={'tipo': 'cambio_talla', 'nueva_talla': '26'})
        self.assertEqual(self.customer.saldo, money(-40))
        self.client.post(f'/pedidos/{order.id}/devolver', data={'tipo': 'cambio_talla'})
        self.assertEqual(Pedido.query.count(), 2)
        replacement = Pedido.query.order_by(Pedido.id.desc()).first()
        self.deliver(replacement)
        self.assertEqual(self.customer.saldo, money(60))

    def test_return_paid_order_keeps_credit(self):
        order = self.order()
        self.deliver(order)
        self.payment('100')
        self.client.post(f'/pedidos/{order.id}/devolver', data={'tipo': 'devolucion'})
        self.assertEqual(self.customer.saldo, money(-100))
        self.assertIn(b'Saldo a favor', self.client.get(f'/clientes/{self.customer.id}').data)
        self.deliver(self.order('150'))
        self.assertEqual(self.customer.saldo, money(50))

    def test_invalid_money(self):
        for value in ['inf', '-inf', 'nan', 'NaN', '-1', 'abc', '10000000000', '1e1000000']:
            with self.subTest(value=value):
                response = self.client.post('/clientes/nuevo', data={'nombre': 'Invalid '+value, 'saldo_inicial': value})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(Cliente.query.count(), 2)

    def test_invalid_order_references_and_money(self):
        for fields in [{'cliente_id': 999}, {'cliente_id': self.branch.id}, {'zapateria_id': 999},
                       {'precio_venta': 'nan'}, {'precio_catalogo': '-10'}]:
            data = {'cliente_id': self.customer.id, 'zapateria_id': self.shop.id, 'codigo': 'A', 'precio_venta': '100'}
            data.update(fields)
            self.assertEqual(self.client.post('/pedidos/nuevo', data=data).status_code, 200)
        self.assertEqual(Pedido.query.count(), 0)

    def test_excess_payment_rejected(self):
        self.deliver(self.order())
        self.payment('101')
        self.assertEqual(Abono.query.count(), 0)
        self.assertEqual(self.customer.saldo, money(100))

    def test_payment_annulment_is_audited_and_once(self):
        self.deliver(self.order())
        self.payment('40')
        payment = Abono.query.one()
        for _ in range(2):
            self.client.post(f'/abonos/{payment.id}/eliminar')
        self.assertEqual(self.customer.saldo, money(100))
        self.assertTrue(payment.anulado)
        self.assertEqual(payment.anulado_por, self.admin.id)
        self.assertIsNotNone(payment.fecha_anulacion)
        self.assertEqual(Abono.query.count(), 1)
        with patch('app.abonos.routes.render_template', return_value='ok') as render:
            self.client.get('/abonos/')
            self.assertEqual(render.call_args.kwargs['abonos'], [])
            self.assertEqual(render.call_args.kwargs['total_dia'], 0)

    def test_cargo_annulment_preserves_credit(self):
        self.client.post(f'/clientes/{self.customer.id}/cargo', data={'monto': '100', 'descripcion': 'Deuda'})
        self.payment('40')
        cargo = Cargo.query.one()
        for _ in range(2):
            self.client.post(f'/clientes/{self.customer.id}/cargo/{cargo.id}/eliminar')
        self.assertEqual(self.customer.saldo, money(-40))
        self.assertTrue(cargo.anulado)

    def test_helper_cannot_annul(self):
        self.deliver(self.order())
        self.payment('40')
        payment = Abono.query.one()
        self.client.post('/auth/logout')
        self.login('helper')
        self.assertEqual(self.client.post(f'/abonos/{payment.id}/eliminar').status_code, 403)
        self.assertEqual(self.customer.saldo, money(60))

    def test_branch_discount_delivery_and_payment(self):
        import json
        from app.models import TicketSucursal
        from app.sucursales.services import delivery_signature
        self.client.post(f'/sucursales/{self.branch.id}/pedido', data={'articulos': json.dumps([
            {'zapateria_id': str(self.shop.id), 'codigo': 'MAY-01', 'descripcion': 'Mayorista'}])})
        order = PedidoSucursal.query.one()
        self.assertEqual(order.precio_final, money(0))
        for state in ('pendiente', 'comprado'):
            self.client.post(f'/sucursales/{self.branch.id}/pedido/{order.id}/avanzar', data={'estatus_actual': state})
        self.client.post(f'/sucursales/{self.branch.id}/preparar', data={'pedidos': [str(order.id)]})
        ticket = TicketSucursal.query.one()
        line = ticket.lineas[0]
        self.client.post(f'/sucursales/entregas/{ticket.id}/preparar', data={f'precio_{line.id}': '200.50', f'descuento_{line.id}': '10'})
        for _ in range(2):
            self.client.post(f'/sucursales/entregas/{ticket.id}/confirmar', data={'revision': delivery_signature(ticket)})
        self.assertEqual(order.precio_final, money('180.45'))
        self.client.post(f'/sucursales/{self.branch.id}/abonar', data={'monto': '80.10'})
        self.assertEqual(self.branch.saldo, money('100.35'))
        html = self.client.get('/abonos/').get_data(as_text=True)
        self.assertIn(f'href="/sucursales/{self.branch.id}"', html)
        self.assertIn('Sucursal (sucursal)', html)

    def test_customer_branch_separation(self):
        self.assertEqual(self.client.get(f'/clientes/{self.branch.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/sucursales/{self.customer.id}').status_code, 404)

    def test_login_redirect_and_password(self):
        self.client.post('/auth/logout')
        response = self.login(suffix='?next=https://example.org')
        self.assertEqual(response.location, '/')
        self.client.post('/auth/password', data={'actual': 'password-test-123', 'nueva': 'new-password-456', 'confirmacion': 'new-password-456'})
        self.assertTrue(self.admin.check_password('new-password-456'))
        self.assertEqual(self.client.get('/auth/logout').status_code, 405)

    def test_csrf_login_and_mutations(self):
        self.client.post('/auth/logout')
        self.app.config['WTF_CSRF_ENABLED'] = True
        client = self.app.test_client()
        self.assertEqual(client.post('/auth/login', data={'username': 'admin', 'password': 'password-test-123'}).status_code, 400)
        html = client.get('/auth/login').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        self.assertEqual(client.post('/auth/login', data={'csrf_token': token, 'username': 'admin', 'password': 'password-test-123'}).status_code, 302)
        self.assertEqual(client.post('/clientes/nuevo', data={'nombre': 'No token'}).status_code, 400)
        self.assertEqual(client.post('/clientes/nuevo', data={'nombre': 'Con token', 'csrf_token': token}).status_code, 302)

    def test_all_screens_and_pdf(self):
        order = self.order()
        self.deliver(order)
        self.payment('10')
        for path in ['/', '/clientes/', '/clientes/nuevo', f'/clientes/{self.customer.id}',
                     f'/clientes/{self.customer.id}/editar', '/clientes/zapaterias',
                     '/pedidos/', '/pedidos/?ver_todos=1', '/pedidos/nuevo', f'/pedidos/{order.id}',
                     '/abonos/', '/abonos/nuevo', '/sucursales/', '/sucursales/nueva',
                     f'/sucursales/{self.branch.id}', f'/sucursales/{self.branch.id}/editar',
                     f'/sucursales/{self.branch.id}/pedido', '/reportes/', '/auth/password']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        for path in ['/pedidos/exportar-pdf', '/reportes/exportar/resumen', '/reportes/exportar/abonos']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data.startswith(b'%PDF'))

    def test_timezone_boundary(self):
        start, end = day_range(today())
        self.assertEqual(start.hour, 6)
        for timestamp in [start - timedelta(seconds=1), start, end]:
            db.session.add(Abono(cliente_id=self.customer.id, monto=money(10), registrado_por=self.admin.id, fecha=timestamp))
        db.session.commit()
        with patch('app.abonos.routes.render_template', return_value='ok') as render:
            self.client.get('/abonos/')
            self.assertEqual(len(render.call_args.kwargs['abonos']), 1)

    def test_branch_sales_in_metrics_and_annulment_excluded(self):
        order = PedidoSucursal(sucursal_id=self.branch.id, zapateria_id=self.shop.id,
            descripcion='Sucursal', precio_base=money(200), descuento=money(0), precio_final=money(200),
            estatus='entregado', fecha_entrega=datetime.utcnow())
        db.session.add(order)
        db.session.commit()
        with patch('app.dashboard.routes.render_template', return_value='ok') as render:
            self.client.get('/')
            self.assertEqual(render.call_args.kwargs['ventas_mes'], money(200))
        with patch('app.reportes.routes.render_template', return_value='<html>OK</html>') as render:
            self.client.get('/reportes/exportar/resumen')
            self.assertEqual(render.call_args.kwargs['vendido_mes'], money(200))

    def test_cancel_and_edit_order_rules(self):
        order = self.order()
        self.client.post(f'/pedidos/{order.id}/editar', data={'zapateria_id': self.shop.id,
            'codigo': 'EDIT', 'descripcion': 'Editado', 'precio_venta': '120.50'})
        self.assertEqual(order.precio_venta, money('120.50'))
        self.client.post(f'/pedidos/{order.id}/cancelar', data={'motivo': 'Prueba'})
        self.client.post(f'/pedidos/{order.id}/avanzar', data={'estatus_actual': 'pendiente'})
        self.assertEqual(order.estatus, 'cancelado')
        self.assertEqual(self.customer.saldo, money(0))

    def test_inactive_references_rejected(self):
        self.customer.activo = False
        self.shop.activa = False
        db.session.commit()
        response = self.client.post('/pedidos/nuevo', data={'cliente_id': self.customer.id,
            'zapateria_id': self.shop.id, 'codigo': 'INVALID', 'precio_venta': '100'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pedido.query.count(), 0)

    def test_repeated_purchase_does_not_deliver_order(self):
        order = self.order()
        for _ in range(2):
            self.client.post(f'/pedidos/{order.id}/avanzar', data={'estatus_actual': 'pendiente'})
        self.assertEqual(order.estatus, 'comprado')
        self.assertEqual(self.customer.saldo, money(0))
        self.assertEqual(self.client.post(f'/pedidos/{order.id}/avanzar').status_code, 400)

    def batch_article(self, **changes):
        article = {'zapateria_id': str(self.shop.id), 'codigo': 'BATCH',
                   'precio_venta': '100.25', 'descripcion': 'Artículo de prueba'}
        article.update(changes)
        return article

    def post_batch(self, articles):
        import json
        return self.client.post('/pedidos/nuevo', data={'cliente_id': self.customer.id,
                                                      'articulos': json.dumps(articles)})

    def test_batch_orders_different_shops(self):
        shop = Zapateria(nombre='Segunda tienda', activa=True)
        db.session.add(shop)
        db.session.commit()
        response = self.post_batch([self.batch_article(), self.batch_article(zapateria_id=str(shop.id), codigo='SECOND', precio_venta='200.50')])
        self.assertEqual(response.status_code, 302)
        self.assertIn('cliente_id=', response.location)
        orders = Pedido.query.order_by(Pedido.id).all()
        self.assertEqual(len(orders), 2)
        self.assertEqual({order.zapateria_id for order in orders}, {self.shop.id, shop.id})
        self.assertTrue(all(order.cliente_id == self.customer.id and order.estatus == 'pendiente' for order in orders))
        self.assertEqual(self.customer.saldo, money(0))
        self.deliver(orders[0])
        self.assertEqual(self.customer.saldo, money('100.25'))
        self.assertEqual(orders[1].estatus, 'pendiente')

    def test_batch_invalid_article_preserves_all_without_partial_save(self):
        response = self.post_batch([self.batch_article(codigo='KEEP-ME'), self.batch_article(precio_venta='nan')])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pedido.query.count(), 0)
        self.assertIn(b'KEEP-ME', response.data)
        self.assertIn(b'Art\xc3\xadculo 2', response.data)

    def test_batch_input_limits_and_references(self):
        for articles in [[], {}, [None], [self.batch_article(codigo='a'*51)],
                         [self.batch_article(zapateria_id='999999999999999999999999')],
                         [self.batch_article()]*51]:
            with self.subTest(articles=str(articles)[:60]):
                self.assertEqual(self.post_batch(articles).status_code, 400)
        for changes in [{'zapateria_id': '999'}, {'codigo': ''}, {'precio_venta': '-1'},
                        {'precio_catalogo': 'inf'}]:
            self.assertEqual(self.post_batch([self.batch_article(**changes)]).status_code, 200)
        self.assertEqual(Pedido.query.count(), 0)

    def test_single_article_batch_and_customer_selection(self):
        response = self.post_batch([self.batch_article()])
        self.assertEqual(response.location, f'/pedidos/{Pedido.query.one().id}')
        response = self.client.get(f'/pedidos/nuevo?cliente_id={self.customer.id}')
        self.assertIn(f'value="{self.customer.id}" selected'.encode(), response.data)

    def test_invalid_and_inactive_user_session(self):
        self.admin.activo = False
        db.session.commit()
        from flask import g
        g.pop('_login_user', None)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_branch_invalid_reference_prices(self):
        import json
        for value in ('inf', 'nan', '-1'):
            data = {'articulos': json.dumps([{'zapateria_id': str(self.shop.id), 'codigo': 'INVALID', 'precio_referencia': value}])}
            self.assertEqual(self.client.post(f'/sucursales/{self.branch.id}/pedido', data=data).status_code, 200)
        self.assertEqual(PedidoSucursal.query.count(), 0)

    def test_historical_delivery_uses_delivery_date(self):
        order = self.order()
        order.fecha_pedido = datetime.utcnow() - timedelta(days=100)
        db.session.commit()
        self.deliver(order)
        with patch('app.pedidos.routes.render_template', return_value='ok') as render:
            self.client.get('/pedidos/?ver_todos=1&estatus=entregado')
            self.assertEqual(len(render.call_args.kwargs['pedidos']), 1)

    def test_lengths_and_invalid_ids(self):
        self.assertEqual(self.client.post('/clientes/nuevo', data={'nombre': 'a'*151}).status_code, 400)
        self.assertEqual(self.client.get('/clientes/99999999999999999999999').status_code, 404)
        self.assertEqual(self.client.post('/pedidos/nuevo', data={'cliente_id': '99999999999999999999999'}).status_code, 400)


class MigrationTests(unittest.TestCase):
    def test_upgrade_existing_and_fresh_database(self):
        import tempfile
        from pathlib import Path
        from flask_migrate import upgrade
        from sqlalchemy import inspect
        with tempfile.TemporaryDirectory() as directory:
            uri = 'sqlite:///' + (Path(directory) / 'migration.db').as_posix()
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': uri})
            with app.app_context():
                upgrade(revision='0001')
                db.session.execute(db.text("INSERT INTO clientes (id, nombre, es_sucursal, activo) VALUES (1, 'Existente', 0, 1)"))
                db.session.execute(db.text('INSERT INTO cuentas (cliente_id, saldo_total) VALUES (1, 60.15)'))
                db.session.execute(db.text("INSERT INTO usuarios (id, nombre, username, password_hash, rol, activo) VALUES (1, 'Admin anterior', 'admin', 'hash-anterior', 'admin', 1)"))
                db.session.execute(db.text("INSERT INTO zapaterias (id, nombre, activa) VALUES (1, 'Andrea', 1)"))
                db.session.execute(db.text("INSERT INTO pedidos (id, cliente_id, zapateria_id, descripcion, precio_venta, estatus) VALUES (1, 1, 1, 'Histórico', 100, 'entregado')"))
                db.session.execute(db.text("INSERT INTO abonos (cliente_id, monto, registrado_por) VALUES (1, 40, 1)"))
                db.session.execute(db.text("INSERT INTO cargos (cliente_id, monto, descripcion, registrado_por) VALUES (1, .15, 'Anterior', 1)"))
                db.session.commit()
                upgrade()
                self.assertEqual(db.session.get(Cliente, 1).saldo, money('60.15'))
                self.assertEqual(db.session.get(Usuario, 1).password_hash, 'hash-anterior')
                self.assertEqual(Abono.query.one().monto, money(40))
                self.assertEqual(Cargo.query.one().monto, money('.15'))
                self.assertEqual(Pedido.query.one().descripcion, 'Histórico')
                self.assertIn('anulado', [col['name'] for col in inspect(db.engine).get_columns('abonos')])
                self.assertEqual(db.session.execute(db.text('PRAGMA foreign_key_check')).all(), [])
                db.session.remove()
                db.engine.dispose()
            uri = 'sqlite:///' + (Path(directory) / 'fresh.db').as_posix()
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': uri})
            with app.app_context():
                upgrade()
                self.assertIn('pedidos_sucursal', inspect(db.engine).get_table_names())
                db.session.remove()
                db.engine.dispose()


class ConcurrencyTests(unittest.TestCase):
    def test_simultaneous_payments_do_not_overpay(self):
        import tempfile
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'WTF_CSRF_ENABLED': False,
                'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'concurrent.db').as_posix()})
            with app.app_context():
                db.create_all()
                user = Usuario(nombre='Admin', username='admin', rol='admin', password_hash='unused')
                customer = Cliente(nombre='Cliente', es_sucursal=False, cuenta=Cuenta(saldo_total=money(100)))
                db.session.add_all([user, customer])
                db.session.commit()
                uid, cid = user.id, customer.id
            def pay():
                with app.test_client() as client:
                    with client.session_transaction() as session:
                        session['_user_id'] = str(uid)
                        session['_fresh'] = True
                    return client.post('/abonos/nuevo', data={'cliente_id': cid, 'monto': '60'}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: pay(), range(2)))
            self.assertEqual(sorted(results), [200, 302])
            with app.app_context():
                self.assertEqual(db.session.get(Cliente, cid).saldo, money(40))
                self.assertEqual(Abono.query.count(), 1)
                db.session.remove()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()
