from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Usuario
from app import db
from urllib.parse import urlsplit
from sqlalchemy import func

auth_bp = Blueprint('auth', __name__, url_prefix='/auth',
                    template_folder='templates')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('portal.inicio' if current_user.rol == 'sucursal' else 'dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        usuario = Usuario.query.filter(func.lower(Usuario.username) == username.lower(), Usuario.activo == True).first()
        if usuario and usuario.rol == 'sucursal' and (not usuario.sucursal or not usuario.sucursal.activo or not usuario.sucursal.es_sucursal):
            usuario = None

        if usuario and usuario.check_password(password):
            login_user(usuario, remember=True)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/') or next_page.startswith('//') or '\\' in next_page or urlsplit(next_page).netloc:
                next_page = url_for('dashboard.index')
            if usuario.rol == 'sucursal':
                next_page = url_for('portal.inicio')
            return redirect(next_page)
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/password', methods=['GET', 'POST'])
@login_required
def password():
    if request.method == 'POST':
        previous = request.form.get('actual', '')
        new = request.form.get('nueva', '')
        confirmation = request.form.get('confirmacion', '')
        if not current_user.check_password(previous):
            flash('La contraseña actual es incorrecta.', 'danger')
        elif len(new) < 10 or len(new) > 128:
            flash('Usa una contraseña de entre 10 y 128 caracteres.', 'danger')
        elif new != confirmation:
            flash('Las contraseñas no coinciden.', 'danger')
        else:
            current_user.set_password(new)
            db.session.commit()
            flash('Contraseña actualizada.', 'success')
            return redirect(url_for('dashboard.index'))
    return render_template('auth/password.html')
