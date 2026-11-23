import os
from unittest import mock
import pandas as pd
import pytest
import plotly.graph_objects as go
from sqlalchemy import text

os.environ["SQLITE_DB_URL"] = "sqlite:///:memory:"

from app.database import init_db, engine, inspect_schema
from app.graph import run_query
from app.chart import generate_plotly_chart


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (order_date) VALUES (datetime('now'))"))
    yield


def test_chart_empty_dataframe():
    assert generate_plotly_chart(pd.DataFrame()) is None
    assert generate_plotly_chart(None) is None


def test_chart_datetime_and_numeric():
    df = pd.DataFrame({
        "order_date": pd.date_range("2024-01-01", periods=5, freq="D"),
        "total_amount": [100, 150, 200, 250, 300],
    })
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_chart_categorical_and_numeric():
    df = pd.DataFrame({
        "category": ["Electronics", "Books", "Clothing"],
        "sales": [5000, 3200, 1500],
    })
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_chart_multi_numeric():
    df = pd.DataFrame({
        "quantity": [1, 2, 3, 4, 5],
        "price": [10.5, 20.0, 15.2, 8.0, 25.0],
    })
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)


def test_chart_single_numeric():
    df = pd.DataFrame({
        "order_id": [101, 102, 103, 104],
    })
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)


def test_chart_only_categorical():
    df = pd.DataFrame({
        "status": ["Completed", "Pending", "Completed", "Cancelled", "Completed"],
    })
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)


# Phase 4 Flow Integration Tests

def test_normal_database_question_to_chart(monkeypatch):
    """Test normal database question producing table data and dynamic Plotly chart."""
    def mock_create(*, model, messages, temperature=0):
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content="SELECT id, order_date FROM orders"))])
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create)

    state = run_query("Show all orders")
    assert state["error_message"] == ""
    assert state["retry_count"] == 0
    assert len(state["db_result"]) > 0

    df = pd.DataFrame(state["db_result"])
    assert not df.empty
    fig = generate_plotly_chart(df)
    assert fig is not None
    assert isinstance(fig, go.Figure)


def test_ui_self_correction_flow(monkeypatch):
    """Test SQL self-correction when query generates bad column initially."""
    calls = []
    def mock_create(*, model, messages, temperature=0):
        if not calls:
            calls.append(1)
            sql = "SELECT invalid_col FROM orders"
        else:
            sql = "SELECT id, order_date FROM orders"
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content=sql))])
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create)

    state = run_query("Get order details with self correction")
    assert state["retry_count"] == 1
    assert state["error_message"] == ""
    assert len(state["db_result"]) > 0


def test_ui_blocked_drop_query(monkeypatch):
    """Test blocked DROP query displays security error and leaves table intact."""
    def fail_if_called(*_, **__):
        raise AssertionError("LLM should not be called")
    monkeypatch.setattr('openai.ChatCompletion.create', fail_if_called)

    state = run_query("DROP TABLE orders; -- malicious attempt")
    assert "Guardrails" in state["error_message"]
    assert state["retry_count"] == 3
    assert state["db_result"] == []

    # Verify table remains intact
    schema = inspect_schema()
    assert "orders" in schema
