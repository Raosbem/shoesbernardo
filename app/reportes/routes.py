from flask import Blueprint, render_template
from flask_login import login_required

reportes_bp = Blueprint('reportes', __name__, url_prefix='/reportes',
                         template_folder='templates')


@reportes_bp.route('/')
@login_required
def index():
    return render_template('reportes/index.html')


@reportes_bp.route('/deudas')
@login_required
def deudas():
    return render_template('reportes/deudas.html')


@reportes_bp.route('/pedidos')
@login_required
def pedidos():
    return render_template('reportes/pedidos.html')


@reportes_bp.route('/ventas')
@login_required
def ventas():
    return render_template('reportes/ventas.html')


@reportes_bp.route('/exportar/<tipo>')
@login_required
def exportar(tipo):
    return f'Exportar {tipo} — próximamente', 200
