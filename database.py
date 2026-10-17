import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, inspect
from sqlalchemy.sql.schema import ColumnDefault


def get_model_defaults(model):
    mapper = inspect(model)
    defaults = {}

    for column in mapper.attrs:
        col = column.columns[0]
        default = col.default

        if isinstance(default, ColumnDefault):
            value = default.arg
            defaults[col.name] = value() if callable(value) else value
        else:
            defaults[col.name] = None

    return defaults


SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./data.db"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)

SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

from models import User

async def table_exists(conn, table_name):
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table"),
        {"table": table_name}
    )
    return result.fetchone() is not None

async def check_and_add_column():
    required_columns = [column.name for column in User.__table__.columns]
    print("required columns:", required_columns)

    python_defaults = get_model_defaults(User)

    def to_sql_value(val):
        if val is None:
            return "NULL"
        elif isinstance(val, (dict, list)):
            return f"'{json.dumps(val)}'"
        elif isinstance(val, str):
            return f"'{val}'"
        else:
            return str(val)

    async with engine.begin() as conn:
        if not await table_exists(conn, "users"):
            print("Table 'users' does not exist yet. Skipping column additions.")
            return

        result = await conn.execute(text("PRAGMA table_info(users);"))
        columns = result.fetchall()
        column_names = [column[1] for column in columns]

        for column in required_columns:
            if column not in column_names:
                default_sql_value = to_sql_value(python_defaults.get(column))
                try:
                    await conn.execute(
                        text(f"ALTER TABLE users ADD COLUMN {column} TEXT DEFAULT {default_sql_value};")
                    )
                    print(f"Added column '{column}' with default {default_sql_value}")
                except Exception as e:
                    print(f"Error adding column {column}: {e}")

        for column, default_val in python_defaults.items():
            if column in column_names:
                default_sql_value = to_sql_value(default_val)
                await conn.execute(
                    text(f"UPDATE users SET {column} = {default_sql_value} WHERE {column} IS NULL")
                )
