from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from database import Base, DATABASE_URL
import models  # Charge les modèles dans les métadonnées Alembic.

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Les tests peuvent fournir leur connexion temporaire sans accéder à Oracle.
    connection = config.attributes.get('connection')
    if connection is not None:
        migrate(connection)
        return
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        migrate(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
