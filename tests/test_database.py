import os
import pytest
from sqlalchemy import inspect

# Ensure we use an in-memory SQLite database for tests
os.environ["SQLITE_DB_URL"] = "sqlite:///:memory:"

from app.database import init_db, inspect_schema, Base, engine
from app.models import Order

def test_database_initialization_and_schema():
    # Initialize the database (creates tables)
    init_db()
    # Inspect schema using SQLAlchemy inspector
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "orders" in tables, "orders table should be created"
    columns = {col["name"] for col in inspector.get_columns("orders")}
    expected = {"id", "order_date"}
    assert expected.issubset(columns), f"orders table should have columns {expected}, got {columns}"
    # Also test our helper function returns correct mapping
    schema = inspect_schema()
    assert "orders" in schema
    assert set(schema["orders"]).issuperset(expected)
