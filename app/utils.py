from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from functools import wraps
from zoneinfo import ZoneInfo

from flask import abort, current_app
from flask_login import current_user


def money(value):
    """Parse a finite monetary amount with cent precision."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount.copy_abs() > Decimal('9999999999.99'):
            raise ValueError
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (DecimalException, TypeError):
        raise ValueError('Monto inválido.') from None


def today():
    return datetime.now(ZoneInfo(current_app.config['BUSINESS_TIMEZONE'])).date()


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def localtime(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(current_app.config['BUSINESS_TIMEZONE']))


def utc_start(day):
    local = datetime.combine(day, time.min, ZoneInfo(current_app.config['BUSINESS_TIMEZONE']))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def day_range(day):
    return utc_start(day), utc_start(day + timedelta(days=1))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.rol != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def get_customer(customer_id, branch=False, active=False):
    from app.models import Cliente
    query = Cliente.query.filter_by(id=customer_id, es_sucursal=branch)
    if active:
        query = query.filter_by(activo=True)
    return query.first_or_404()


def lock_customer(customer):
    """Serialize account changes, including on SQLite, until commit."""
    from app import db
    from app.models import Cliente
    db.session.execute(db.update(Cliente).where(Cliente.id == customer.id)
                       .values(activo=Cliente.activo))
    db.session.expire(customer, ['cuenta'])
    if customer.cuenta:
        db.session.refresh(customer.cuenta)
