from app.utils import utc_now
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from decimal import Decimal
from app.utils import money


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    __table_args__ = (db.UniqueConstraint('sucursal_id', name='uq_usuario_sucursal'),)

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='ayudante')  # admin | ayudante
    activo = db.Column(db.Boolean, default=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id', name='fk_usuario_sucursal'), nullable=True)
    sucursal = db.relationship('Cliente', foreign_keys=[sucursal_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.username}>'


@login_manager.user_loader
def load_user(user_id):
    try:
        user = Usuario.query.filter_by(id=int(user_id), activo=True).first()
        if user and user.rol == 'sucursal' and (not user.sucursal or not user.sucursal.es_sucursal or not user.sucursal.activo):
            return None
        return user
    except (ValueError, TypeError):
        return None


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
    fecha_registro = db.Column(db.DateTime, default=utc_now)
    comision_pct = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal('0'), server_default='0')

    cuenta = db.relationship('Cuenta', backref='cliente', uselist=False, cascade='all, delete-orphan')
    abonos = db.relationship('Abono', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    cargos = db.relationship('Cargo', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    pedidos = db.relationship('Pedido', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    pedidos_sucursal = db.relationship('PedidoSucursal', backref='sucursal', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def saldo(self):
        if self.cuenta:
            return self.cuenta.saldo_total
        return money(0)

    def __repr__(self):
        return f'<Cliente {self.nombre}>'


# ---------------------------------------------------------------------------
# Cuenta (saldo del cliente)
# ---------------------------------------------------------------------------
class Cuenta(db.Model):
    __tablename__ = 'cuentas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), unique=True, nullable=False)
    saldo_total = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    ultima_actualizacion = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    def agregar_cargo(self, monto):
        self.saldo_total = money(self.saldo_total or 0) + money(monto)
        self.ultima_actualizacion = utc_now()

    def aplicar_abono(self, monto):
        self.saldo_total = money(self.saldo_total or 0) - money(monto)
        self.ultima_actualizacion = utc_now()

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
    precio_catalogo = db.Column(db.Numeric(12, 2), nullable=True)
    precio_venta = db.Column(db.Numeric(12, 2), nullable=False)
    estatus = db.Column(db.String(30), default='pendiente')
    fecha_pedido = db.Column(db.DateTime, default=utc_now)
    fecha_entrega = db.Column(db.DateTime, nullable=True)
    notas = db.Column(db.Text, nullable=True)

    def marcar_entregado(self):
        """Marca como entregado y carga el precio al saldo del cliente."""
        from app import db as _db
        self.estatus = 'entregado'
        self.fecha_entrega = utc_now()
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
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha = db.Column(db.DateTime, default=utc_now)
    registrado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    notas = db.Column(db.String(200), nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets_sucursal.id', name='fk_abono_ticket'), nullable=True)

    anulado = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    anulado_por = db.Column(db.Integer, nullable=True)
    fecha_anulacion = db.Column(db.DateTime, nullable=True)

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
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, default=utc_now)
    registrado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

    anulado = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    anulado_por = db.Column(db.Integer, nullable=True)
    fecha_anulacion = db.Column(db.DateTime, nullable=True)

    usuario = db.relationship('Usuario', backref='cargos_registrados')

    def __repr__(self):
        return f'<Cargo ${self.monto} cliente={self.cliente_id}>'


# ---------------------------------------------------------------------------
# PedidoSucursal (mayorista con descuento)
# ---------------------------------------------------------------------------
class PedidoSucursal(db.Model):
    __tablename__ = 'pedidos_sucursal'

    ESTATUS = ['borrador', 'pendiente', 'comprado', 'recibido', 'entregado', 'cancelado', 'devuelto']

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    zapateria_id = db.Column(db.Integer, db.ForeignKey('zapaterias.id'), nullable=False)
    codigo_producto = db.Column(db.String(50), nullable=True)
    descripcion = db.Column(db.String(200), nullable=False)
    color = db.Column(db.String(50), nullable=True)
    talla = db.Column(db.String(10), nullable=True)
    precio_base = db.Column(db.Numeric(12, 2), nullable=False)
    descuento = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))  # porcentaje
    precio_final = db.Column(db.Numeric(12, 2), nullable=False)
    semana = db.Column(db.String(20), nullable=True)  # ej: 2025-W15
    estatus = db.Column(db.String(30), default='pendiente')
    fecha_pedido = db.Column(db.DateTime, default=utc_now)
    fecha_entrega = db.Column(db.DateTime, nullable=True)
    precio_referencia = db.Column(db.Numeric(12, 2), nullable=True)
    notas = db.Column(db.String(200))
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes_sucursal.id', name='fk_pedido_solicitud'), nullable=True)
    detalle_ticket = db.relationship('DetalleTicketSucursal', back_populates='pedido', uselist=False)
    devolucion = db.relationship('DevolucionSucursal', back_populates='pedido', uselist=False)

    def calcular_precio_final(self):
        self.precio_final = money(self.precio_base * (1 - self.descuento / 100))

    @property
    def cliente(self):
        return self.sucursal

    @property
    def precio_venta(self):
        return self.precio_final

    def marcar_entregado(self):
        from app import db as _db
        self.estatus = 'entregado'
        self.fecha_entrega = utc_now()
        sucursal = self.sucursal
        if not sucursal.cuenta:
            sucursal.cuenta = Cuenta(cliente_id=sucursal.id)
            _db.session.add(sucursal.cuenta)
        sucursal.cuenta.agregar_cargo(self.precio_final)

    def __repr__(self):
        return f'<PedidoSucursal {self.id} semana={self.semana}>'


class SolicitudSucursal(db.Model):
    __tablename__ = 'solicitudes_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    fecha = db.Column(db.DateTime, nullable=False, default=utc_now)
    fecha_envio = db.Column(db.DateTime)
    creado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    sucursal = db.relationship('Cliente')
    articulos = db.relationship('PedidoSucursal', backref='solicitud', cascade='all, delete-orphan', order_by='PedidoSucursal.id')


class TicketSucursal(db.Model):
    __tablename__ = 'tickets_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    sucursal_nombre = db.Column(db.String(150), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='borrador')
    fecha = db.Column(db.DateTime, nullable=False, default=utc_now)
    fecha_confirmacion = db.Column(db.DateTime)
    creado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    confirmado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    comision_pct = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal('0'))
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0'))
    comision = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0'))
    vale_aplicado = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0'))
    total = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal('0'))
    revisado = db.Column(db.Boolean, nullable=False, default=False)
    sucursal = db.relationship('Cliente')
    lineas = db.relationship('DetalleTicketSucursal', back_populates='ticket', cascade='all, delete-orphan', order_by='DetalleTicketSucursal.id')
    abonos = db.relationship('Abono', backref='ticket', lazy='dynamic')

    @property
    def folio(self):
        return f'S-{self.id:06d}'

    @property
    def total_pagado(self):
        return db.session.query(db.func.sum(Abono.monto)).filter_by(ticket_id=self.id, anulado=False).scalar() or money(0)

    @property
    def pendiente(self):
        return self.total - self.total_pagado


class DetalleTicketSucursal(db.Model):
    __tablename__ = 'detalles_ticket_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets_sucursal.id'), nullable=False)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos_sucursal.id'), nullable=False, unique=True)
    tienda = db.Column(db.String(100), nullable=False)
    codigo = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    color = db.Column(db.String(50))
    talla = db.Column(db.String(10))
    precio = db.Column(db.Numeric(12, 2))
    descuento_pct = db.Column(db.Numeric(5, 2))
    neto = db.Column(db.Numeric(12, 2))
    comision = db.Column(db.Numeric(12, 2))
    ticket = db.relationship('TicketSucursal', back_populates='lineas')
    pedido = db.relationship('PedidoSucursal', back_populates='detalle_ticket')


class DevolucionSucursal(db.Model):
    __tablename__ = 'devoluciones_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos_sucursal.id'), nullable=False, unique=True)
    motivo = db.Column(db.String(200), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='solicitada')
    fecha = db.Column(db.DateTime, nullable=False, default=utc_now)
    solicitado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    resuelto_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_resolucion = db.Column(db.DateTime)
    respuesta = db.Column(db.String(200))
    sucursal = db.relationship('Cliente')
    pedido = db.relationship('PedidoSucursal', back_populates='devolucion')
    vale = db.relationship('ValeSucursal', back_populates='devolucion', uselist=False)


class ValeSucursal(db.Model):
    __tablename__ = 'vales_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    devolucion_id = db.Column(db.Integer, db.ForeignKey('devoluciones_sucursal.id'), nullable=False, unique=True)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=utc_now)
    devolucion = db.relationship('DevolucionSucursal', back_populates='vale')
    usos = db.relationship('UsoValeSucursal', back_populates='vale', order_by='UsoValeSucursal.id')

    @property
    def folio(self):
        return f'V-{self.id:06d}'

    @property
    def disponible(self):
        usado = db.session.query(db.func.sum(UsoValeSucursal.monto)).filter_by(vale_id=self.id).scalar() or money(0)
        return self.monto - usado


class UsoValeSucursal(db.Model):
    __tablename__ = 'usos_vale_sucursal'
    __table_args__ = (db.UniqueConstraint('vale_id', 'ticket_id', name='uq_vale_ticket'),)
    id = db.Column(db.Integer, primary_key=True)
    vale_id = db.Column(db.Integer, db.ForeignKey('vales_sucursal.id'), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets_sucursal.id'), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    vale = db.relationship('ValeSucursal', back_populates='usos')
    ticket = db.relationship('TicketSucursal', backref='usos_vales')
