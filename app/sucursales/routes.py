from flask import Blueprint, render_template
from flask_login import login_required

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales',
                           template_folder='templates')


@sucursales_bp.route('/')
@login_required
def lista():
    return render_template('sucursales/lista.html')


@sucursales_bp.route('/<int:id>')
@login_required
def detalle(id):
    return render_template('sucursales/detalle.html')


@sucursales_bp.route('/<int:id>/pedido', methods=['GET', 'POST'])
@login_required
def nuevo_pedido(id):
    return render_template('sucursales/pedido.html')
