"""End-to-end branch workflow on mobile, using temporary data only."""
import tempfile
import threading
import unittest
from pathlib import Path

from app import create_app, db
from app.models import Cliente, Cuenta, TicketSucursal, Usuario, ValeSucursal, Zapateria
from app.utils import money


class BranchBrowserTests(unittest.TestCase):
    def test_portal_delivery_return_and_next_purchase(self):
        from playwright.sync_api import sync_playwright, expect
        from werkzeug.serving import make_server
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'browser-branches',
                'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'branch.db').as_posix()})
            with app.app_context():
                db.create_all()
                user = Usuario(nombre='Admin', username='admin', rol='admin')
                user.set_password('browser-admin-123')
                branch = Cliente(nombre='Ire prueba', es_sucursal=True, comision_pct=money(5), cuenta=Cuenta(saldo_total=money(0)))
                shop = Zapateria(nombre='Andrea')
                db.session.add_all([user, branch, shop])
                db.session.commit()
                bid, sid = branch.id, str(shop.id)
            server = make_server('127.0.0.1', 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel='msedge', headless=True)
                    staff_context = browser.new_context(viewport={'width': 1280, 'height': 900})
                    branch_context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                    staff, portal = staff_context.new_page(), branch_context.new_page()
                    errors = []
                    for page in (staff, portal):
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('dialog', lambda dialog: dialog.accept())
                    base = f'http://127.0.0.1:{server.server_port}'

                    def login(page, username, password):
                        page.goto(base + '/auth/login')
                        page.locator('[name=username]').fill(username)
                        page.locator('[name=password]').fill(password)
                        page.locator('button[type=submit]').click()
                        page.wait_for_load_state('networkidle')

                    login(staff, 'admin', 'browser-admin-123')
                    staff.goto(base + f'/sucursales/{bid}/acceso')
                    staff.locator('[name=username]').fill('ire-prueba')
                    staff.locator('[name=password]').fill('browser-ire-123')
                    staff.get_by_role('button', name='Guardar acceso', exact=True).click()
                    expect(staff).to_have_url(base + f'/sucursales/{bid}')
                    login(portal, 'ire-prueba', 'browser-ire-123')
                    expect(portal).to_have_url(base + '/mi-sucursal/')
                    self.assertEqual(portal.get_by_role('link', name='Clientes', exact=True).count(), 0)

                    portal.get_by_role('link', name='+ Hacer pedido', exact=True).click()
                    portal.locator('#zapateria').select_option(sid)
                    portal.locator('#codigo').fill('PORTAL-01')
                    portal.locator('#talla').fill('25')
                    portal.locator('#color').fill('Negro')
                    portal.get_by_role('button', name='Guardar borrador para después').click()
                    expect(portal.locator('body')).to_contain_text('Borrador: todavía no se ha enviado')
                    portal.get_by_role('link', name='Continuar y enviar pedido').click()
                    portal.locator('#registrar').click()
                    expect(portal.locator('body')).to_contain_text('Enviado. Cada artículo')

                    def prepare_from_queue(code, price, discount, use_credit=False):
                        staff.goto(base + f'/pedidos/bandeja?tipo=sucursales&sucursal_id={bid}')
                        card = staff.locator('.card.card-body').filter(has_text=code).last
                        card.get_by_role('button', name='Marcar comprado').click()
                        card = staff.locator('.card.card-body').filter(has_text=code).last
                        card.get_by_role('button', name='Ya llegó al local').click()
                        card = staff.locator('.card.card-body').filter(has_text=code).last
                        card.locator('input[type=checkbox]').check()
                        staff.get_by_role('button', name='Preparar entrega de los seleccionados').click()
                        staff.locator('.precio').fill(price)
                        staff.locator('.descuento').fill(discount)
                        if use_credit:
                            staff.get_by_role('button', name='Usar los vales disponibles').click()
                        staff.get_by_role('button', name='Revisar entrega antes de confirmar').click()

                    prepare_from_queue('PORTAL-01', '1000', '30')
                    expect(staff.locator('body')).to_contain_text('$735.00')
                    staff.get_by_role('button', name='Confirmar entrega y generar ticket').click()
                    staff.wait_for_url('**/sucursales/tickets/*')
                    first_id = staff.url.rsplit('/', 1)[-1]
                    portal.goto(base + '/mi-sucursal/tickets')
                    portal.get_by_role('link').filter(has_text='S-000001').click()
                    portal.get_by_role('link', name='Solicitar devolución', exact=True).click()
                    portal.locator('[name=motivo]').fill('No quedó la talla')
                    portal.get_by_role('button', name='Enviar solicitud de devolución').click()
                    expect(portal.locator('body')).to_contain_text('Pendiente de recepción')
                    staff.goto(base + '/sucursales/devoluciones')
                    staff.get_by_role('button', name='Ya recibí el producto: generar vale').click()
                    portal.goto(base + '/mi-sucursal/vales')
                    expect(portal.locator('body')).to_contain_text('$700.00')
                    self.assertFalse(portal.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
                    Path('instance').mkdir(exist_ok=True)
                    portal.screenshot(path='instance/sucursal-vales-mobile.png', full_page=True)

                    portal.get_by_role('link', name='+ Hacer pedido', exact=True).click()
                    portal.locator('#zapateria').select_option(sid)
                    portal.locator('#codigo').fill('PORTAL-02')
                    portal.locator('#registrar').click()
                    expect(portal.locator('body')).to_contain_text('Enviado. Cada artículo')
                    prepare_from_queue('PORTAL-02', '1000', '0', use_credit=True)
                    expect(staff.locator('body')).to_contain_text('$350.00')
                    staff.get_by_role('button', name='Confirmar entrega y generar ticket').click()
                    staff.wait_for_url('**/sucursales/tickets/*')
                    second_id = staff.url.rsplit('/', 1)[-1]
                    portal.goto(base + f'/mi-sucursal/tickets/{second_id}')
                    expect(portal.locator('body')).to_contain_text('$350.00')
                    portal.screenshot(path='instance/sucursal-ticket-mobile.png', full_page=True)
                    self.assertFalse(portal.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
                    pdf = branch_context.request.get(base + f'/mi-sucursal/tickets/{first_id}/pdf')
                    self.assertTrue(pdf.body().startswith(b'%PDF'))
                    self.assertEqual(errors, [])
                    browser.close()
                with app.app_context():
                    self.assertEqual(TicketSucursal.query.filter_by(estado='confirmado').count(), 2)
                    self.assertEqual(ValeSucursal.query.one().disponible, money(0))
                    self.assertEqual(db.session.get(Cliente, bid).saldo, money(1085))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()
