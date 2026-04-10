from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Inicia sesión para continuar.'
login_manager.login_message_category = 'warning'


def create_app():
    app = Flask(__name__, template_folder='../templates')
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.auth.routes import auth_bp
    from app.clientes.routes import clientes_bp
    from app.pedidos.routes import pedidos_bp
    from app.abonos.routes import abonos_bp
    from app.sucursales.routes import sucursales_bp
    from app.reportes.routes import reportes_bp
    from app.dashboard.routes import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(abonos_bp)
    app.register_blueprint(sucursales_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()

    return app
