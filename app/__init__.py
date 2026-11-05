from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from pathlib import Path
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()


@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, record):
    import sqlite3
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Inicia sesión para continuar.'
login_manager.login_message_category = 'warning'


def create_app(test_config=None):
    app = Flask(__name__, template_folder='../templates')
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get('SECRET_KEY'):
        if app.config.get('DATABASE_URL'):
            raise RuntimeError('Configura SECRET_KEY antes de usar una base de producción.')
        import secrets
        secret_path = Path(app.instance_path) / 'secret_key'
        if not secret_path.exists():
            try:
                with secret_path.open('x', encoding='utf-8') as handle:
                    handle.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        app.config['SECRET_KEY'] = secret_path.read_text(encoding='utf-8')

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    from app.utils import localtime
    app.jinja_env.filters['localtime'] = localtime

    from app.auth.routes import auth_bp
    from app.clientes.routes import clientes_bp
    from app.pedidos.routes import pedidos_bp
    from app.abonos.routes import abonos_bp
    from app.sucursales.routes import sucursales_bp, portal_bp
    from app.reportes.routes import reportes_bp
    from app.dashboard.routes import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(abonos_bp)
    app.register_blueprint(sucursales_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(dashboard_bp)
    from app.commands import register_commands
    register_commands(app)

    from flask import request, render_template, abort, redirect, url_for
    from flask_login import current_user
    from werkzeug.exceptions import HTTPException

    @app.before_request
    def restrict_branch_access():
        if current_user.is_authenticated:
            if current_user.rol == 'sucursal':
                if not current_user.sucursal or not current_user.sucursal.activo or not current_user.sucursal.es_sucursal:
                    abort(403)
                if request.endpoint == 'dashboard.index':
                    return redirect(url_for('portal.inicio'))
                if request.blueprint not in ('portal', 'auth') and request.endpoint != 'static':
                    abort(403)
            elif current_user.rol not in ('admin', 'ayudante'):
                abort(403)

    @app.before_request
    def validate_form_lengths():
        limits = {'nombre': 100, 'username': 50, 'telefono': 20,
                  'direccion': 250, 'descripcion': 200, 'codigo': 50,
                  'codigo_producto': 50, 'color': 50, 'talla': 10,
                  'nueva_talla': 10, 'notas': 200, 'semana': 8,
                  'motivo': 200}
        for field, limit in limits.items():
            if any(len(value) > limit for value in request.form.getlist(field)):
                from flask import abort
                abort(400, description=f'El campo {field} permite hasta {limit} caracteres.')
        from flask import abort
        for value in (request.view_args or {}).values():
            if isinstance(value, int) and not 0 < value <= 2147483647:
                abort(404)
        for field in ('cliente_id', 'zapateria_id', 'ticket_id', 'sucursal_id'):
            for value in request.form.getlist(field) + request.args.getlist(field):
                if value and (not value.isascii() or not value.isdecimal() or len(value) > 10 or not 0 < int(value) <= 2147483647):
                    abort(400, description='La selección no es válida.')

    @app.errorhandler(HTTPException)
    def request_error(error):
        db.session.rollback()
        return render_template('error.html', error=error), error.code

    return app
