import os
import pytest
from unittest import mock
from sqlalchemy import text

# Ensure in-memory SQLite for isolation
os.environ["SQLITE_DB_URL"] = "sqlite:///:memory:"

from app.database import init_db, engine
from app.graph import run_query

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield

def mock_create_return(sql):
    """Helper: returns a mock openai response with the given SQL content."""
    def _mock(*, model, messages, temperature=0):
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content=sql))])
    return _mock

def test_successful_sql_generation(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return('SELECT 1'))
    state = run_query("Give me a constant")
    assert state["generated_sql"].strip() == "SELECT 1"
    assert state["error_message"] == ""
    assert len(state["db_result"]) == 1

def test_invalid_column_error_and_retry(monkeypatch):
    calls = []
    def mock_create(*, model, messages, temperature=0):
        if not calls:
            calls.append(1)
            sql = "SELECT non_existing FROM orders"
        else:
            sql = "SELECT id FROM orders"
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content=sql))])
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create)

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (order_date) VALUES (datetime('now'))"))

    state = run_query("Get order ids")
    assert state["retry_count"] == 1
    assert state["error_message"] == ""
    assert any("id" in row for row in state["db_result"])

def test_retry_limit_exceeded(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return("SELECT bad FROM nowhere"))
    state = run_query("Bad query")
    assert state["retry_count"] == 3
    assert state["error_message"] != ""
    assert state["db_result"] == []
