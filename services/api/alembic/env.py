from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import settings
from app.db.session import Base
from app.models import entities  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)
target_metadata = Base.metadata

# Extension-owned tables (PostGIS spatial_ref_sys, plus the tiger geocoder and
# topology tables that some PostGIS images place on the search path) are not
# part of MCHO's model. Without this filter `alembic check` would propose
# dropping them. The online path asks PostgreSQL which relations extensions own.
EXTENSION_OWNED_TABLES: set[str] = {"spatial_ref_sys"}
EXTENSION_OWNED_TABLES_SQL = text("""
    SELECT c.relname
    FROM pg_depend d
    JOIN pg_class c ON c.oid = d.objid AND d.classid = 'pg_class'::regclass
    WHERE d.deptype = 'e' AND c.relkind IN ('r', 'p', 'v', 'm')
""")


def include_object(obj, name, type_, reflected, compare_to):
    if not reflected or compare_to is not None:
        return True
    if type_ == "table":
        return name not in EXTENSION_OWNED_TABLES
    if type_ == "index":
        return obj.table.name not in EXTENSION_OWNED_TABLES
    return True


def run_migrations_offline():
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        EXTENSION_OWNED_TABLES.update(connection.scalars(EXTENSION_OWNED_TABLES_SQL))
        # End the autobegun read transaction; otherwise Alembic would treat the
        # run as externally managed and never commit the migration.
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
