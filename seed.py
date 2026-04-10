"""
seed.py — Inicializa la base de datos con datos básicos.
Ejecutar una sola vez: python seed.py
"""
from app import create_app, db
from app.models import Usuario, Zapateria

ZAPATERIAS = [
    'Supershoes',
    'Golden Shoes',
    'Pakar',
    'Andrea',
    'Cklass',
    'Price Shoes',
    'BL Shoes',
]


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Crear zapaterías si no existen
        for nombre in ZAPATERIAS:
            if not Zapateria.query.filter_by(nombre=nombre).first():
                db.session.add(Zapateria(nombre=nombre, activa=True))
                print(f'  + Zapatería: {nombre}')

        # Crear usuario admin si no existe
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(
                nombre='Administrador',
                username='admin',
                rol='admin',
                activo=True,
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print('  + Usuario admin creado (admin / admin123)')

        db.session.commit()
        print('\nSeed completado.')


if __name__ == '__main__':
    seed()
