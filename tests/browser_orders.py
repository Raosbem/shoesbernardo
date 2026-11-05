"""Optional browser check: python -m unittest discover -s tests -p browser_orders.py -v."""
import tempfile
import threading
import unittest
from pathlib import Path

from app import create_app, db
from app.models import Cliente, Cuenta, Pedido, Usuario, Zapateria
from app.utils import money


class OrderBrowserTests(unittest.TestCase):
    def test_multiple_articles_on_mobile(self):
        from playwright.sync_api import sync_playwright, expect
        from werkzeug.serving import make_server

        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'browser-test',
                'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'browser.db').as_posix()})
            with app.app_context():
                db.create_all()
                user = Usuario(nombre='Prueba', username='prueba', rol='admin')
                user.set_password('browser-test-123')
                customer = Cliente(nombre='Cliente navegador', es_sucursal=False, cuenta=Cuenta(saldo_total=money(0)))
                shops = [Zapateria(nombre=name, activa=True) for name in ('Andrea', 'Cklass', 'Pakar')]
                db.session.add_all([user, customer, *shops])
                db.session.commit()
                cid = customer.id
                shop_ids = [str(shop.id) for shop in shops]
            server = make_server('127.0.0.1', 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel='msedge', headless=True)
                    page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('dialog', lambda dialog: dialog.accept())
                    base = f'http://127.0.0.1:{server.server_port}'
                    page.goto(base + '/auth/login')
                    page.locator('[name=username]').fill('prueba')
                    page.locator('[name=password]').fill('browser-test-123')
                    page.locator('button[type=submit]').click()
                    page.wait_for_url(base + '/')
                    page.goto(base + f'/pedidos/nuevo?cliente_id={cid}')
                    expect(page.locator('#cliente')).to_have_value(str(cid))
                    page.locator('#zapateria').select_option(shop_ids[0])
                    page.locator('#codigo').fill('AND-01')
                    page.locator('#precio_venta').fill('450')
                    page.locator('#guardar-articulo').click()
                    expect(page.locator('#editor')).to_be_hidden()
                    page.locator('#otro-articulo').click()
                    expect(page.locator('#cliente')).to_have_value(str(cid))
                    page.locator('#zapateria').select_option(shop_ids[1])
                    page.locator('#codigo').fill('CLK-02')
                    page.locator('#precio_venta').fill('600')
                    page.locator('#guardar-articulo').click()
                    expect(page.locator('#registrar')).to_have_text('Registrar 2 artículos')
                    page.get_by_role('button', name='Editar artículo 1', exact=True).click()
                    page.locator('#precio_venta').fill('400.25')
                    page.locator('#guardar-articulo').click()
                    page.get_by_role('button', name='Quitar artículo 2', exact=True).click()
                    expect(page.locator('#lista-articulos')).not_to_contain_text('CLK-02')
                    page.locator('#otro-articulo').click()
                    page.locator('#zapateria').select_option(shop_ids[1])
                    page.locator('#codigo').fill('CLK-03')
                    page.locator('#registrar').click()
                    expect(page).to_have_url(base + f'/pedidos/nuevo?cliente_id={cid}')
                    page.locator('#precio_venta').fill('600')
                    page.locator('#guardar-articulo').click()
                    page.locator('#otro-articulo').click()
                    page.locator('#zapateria').select_option(shop_ids[2])
                    page.locator('#codigo').fill('PAK-04')
                    page.locator('#precio_venta').fill('350')
                    # Save directly with the final article still in the editor.
                    expect(page.locator('#registrar')).to_have_text('Registrar 3 artículos')
                    self.assertFalse(page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
                    page.locator('#registrar').click()
                    page.wait_for_url('**/pedidos/?**')
                    expect(page.locator('body')).to_contain_text('Se registraron 3 artículos')
                    self.assertEqual(errors, [])
                    browser.close()
                with app.app_context():
                    orders = Pedido.query.order_by(Pedido.id).all()
                    self.assertEqual([order.codigo_producto for order in orders], ['AND-01', 'CLK-03', 'PAK-04'])
                    self.assertEqual(orders[0].precio_venta, money('400.25'))
                    self.assertEqual(db.session.get(Cliente, cid).saldo, money(0))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()
