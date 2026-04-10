from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='ayudante')  # admin | ayudante
    activo = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.username}>'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Zapateria
# ---------------------------------------------------------------------------
class Zapateria(db.Model):
    __tablename__ = 'zapaterias'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    activa = db.Column(db.Boolean, default=True)

    pedidos = db.relationship('Pedido', backref='zapateria', lazy='dynamic')
    pedidos_sucursal = db.relationship('PedidoSucursal', backref='zapateria', lazy='dynamic')

    def __repr__(self):
        return f'<Zapateria {self.nombre}>'


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(20), nullable=True)
    direccion = db.Column(db.String(250), nullable=True)
    es_sucursal = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    cuenta = db.relationship('Cuenta', backref='cliente', uselist=False, cascade='all, delete-orphan')
    abonos = db.relationship('Abono', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    cargos = db.relationship('Cargo', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    pedidos = db.relationship('Pedido', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    pedidos_sucursal = db.relationship('PedidoSucursal', backref='sucursal', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def saldo(self):
        if self.cuenta:
            return self.cuenta.saldo_total
        return 0.0

    def __repr__(self):
        return f'<Cliente {self.nombre}>'


# ---------------------------------------------------------------------------
# Cuenta (saldo del cliente)
# ---------------------------------------------------------------------------
class Cuenta(db.Model):
    __tablename__ = 'cuentas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), unique=True, nullable=False)
    saldo_total = db.Column(db.Float, default=0.0)
    ultima_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def agregar_cargo(self, monto):
        self.saldo_total = (self.saldo_total or 0.0) + monto
        self.ultima_actualizacion = datetime.utcnow()

    def aplicar_abono(self, monto):
        self.saldo_total = max(0.0, (self.saldo_total or 0.0) - monto)
        self.ultima_actualizacion = datetime.utcnow()

    def __repr__(self):
        return f'<Cuenta cliente={self.cliente_id} saldo={self.saldo_total}>'


# ---------------------------------------------------------------------------
# Pedido (clientes regulares)
# ---------------------------------------------------------------------------
class Pedido(db.Model):
    __tablename__ = 'pedidos'

    ESTATUS = ['pendiente', 'comprado', 'entregado', 'cancelado', 'devuelto']

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    zapateria_id = db.Column(db.Integer, db.ForeignKey('zapaterias.id'), nullable=False)
    codigo_producto = db.Column(db.String(50), nullable=True)
    descripcion = db.Column(db.String(200), nullable=False)
    color = db.Column(db.String(50), nullable=True)
    talla = db.Column(db.String(10), nullable=True)
    precio_catalogo = db.Column(db.Float, nullable=True)
    precio_venta = db.Column(db.Float, nullable=False)
    estatus = db.Column(db.String(30), default='pendiente')
    fecha_pedido = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_entrega = db.Column(db.DateTime, nullable=True)
    notas = db.Column(db.Text, nullable=True)

    def marcar_entregado(self):
        """Marca como entregado y carga el precio al saldo del cliente."""
        from app import db as _db
        self.estatus = 'entregado'
        self.fecha_entrega = datetime.utcnow()
        cliente = self.cliente
        if not cliente.cuenta:
            cliente.cuenta = Cuenta(cliente_id=cliente.id)
            _db.session.add(cliente.cuenta)
        cliente.cuenta.agregar_cargo(self.precio_venta)

    def __repr__(self):
        return f'<Pedido {self.id} {self.descripcion[:30]}>'


# ---------------------------------------------------------------------------
# Abono
# ---------------------------------------------------------------------------
class Abono(db.Model):
    __tablename__ = 'abonos'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    registrado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    notas = db.Column(db.String(200), nullable=True)

    usuario = db.relationship('Usuario', backref='abonos_registrados')

    def __repr__(self):
        return f'<Abono ${self.monto} cliente={self.cliente_id}>'


# ---------------------------------------------------------------------------
# Cargo (cargo manual al saldo del cliente — devoluciones lo eliminan)
# ---------------------------------------------------------------------------
class Cargo(db.Model):
    __tablename__ = 'cargos'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    registrado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

    usuario = db.relationship('Usuario', backref='cargos_registrados')

    def __repr__(self):
        return f'<Cargo ${self.monto} cliente={self.cliente_id}>'


# ---------------------------------------------------------------------------
# PedidoSucursal (mayorista con descuento)
# ---------------------------------------------------------------------------
class PedidoSucursal(db.Model):
    __tablename__ = 'pedidos_sucursal'

    ESTATUS = ['pendiente', 'entregado', 'cancelado']

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    zapateria_id = db.Column(db.Integer, db.ForeignKey('zapaterias.id'), nullable=False)
    codigo_producto = db.Column(db.String(50), nullable=True)
    descripcion = db.Column(db.String(200), nullable=False)
    color = db.Column(db.String(50), nullable=True)
    talla = db.Column(db.String(10), nullable=True)
    precio_base = db.Column(db.Float, nullable=False)
    descuento = db.Column(db.Float, default=0.0)  # porcentaje
    precio_final = db.Column(db.Float, nullable=False)
    semana = db.Column(db.String(20), nullable=True)  # ej: 2025-W15
    estatus = db.Column(db.String(30), default='pendiente')
    fecha_pedido = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_entrega = db.Column(db.DateTime, nullable=True)

    def calcular_precio_final(self):
        self.precio_final = self.precio_base * (1 - self.descuento / 100)

    def marcar_entregado(self):
        from app import db as _db
        self.estatus = 'entregado'
        self.fecha_entrega = datetime.utcnow()
        sucursal = self.sucursal
        if not sucursal.cuenta:
            sucursal.cuenta = Cuenta(cliente_id=sucursal.id)
            _db.session.add(sucursal.cuenta)
        sucursal.cuenta.agregar_cargo(self.precio_final)

    def __repr__(self):
        return f'<PedidoSucursal {self.id} semana={self.semana}>'
