from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import click

from app import db


def register_commands(app):
    @app.cli.command('backup-db')
    def backup_db():
        """Create a consistent local SQLite backup without stopping the app."""
        if db.engine.dialect.name != 'sqlite' or db.engine.url.database == ':memory:':
            raise click.ClickException('Este comando respalda SQLite local. Para PostgreSQL usa pg_dump.')
        source = Path(db.engine.url.database)
        if not source.is_file():
            raise click.ClickException('La base de datos todavía no existe.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        target = source.with_name(f'respaldo_{stamp}.db')
        with sqlite3.connect(source) as origin, sqlite3.connect(target) as destination:
            origin.backup(destination)
        click.echo(f'Respaldo creado: {target}')
