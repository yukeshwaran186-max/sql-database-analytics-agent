import os
import pytest
from unittest import mock
from sqlalchemy import text

# Ensure in-memory SQLite for isolation
os.environ["SQLITE_DB_URL"] = "sqlite:///:memory:"

from app.database import init_db, engine
from app.graph import run_query
from app.guardrails import validate_sql, check_user_input

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (order_date) VALUES (datetime('now'))"))
    yield

def mock_create_return(sql):
    def _mock(*, model, messages, temperature=0):
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content=sql))])
    return _mock

def test_valid_select(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return('SELECT id FROM orders'))
    state = run_query('Give me order ids')
    assert state['error_message'] == ''
    assert state['retry_count'] == 0
    assert isinstance(state['db_result'], list)
    assert any('id' in row for row in state['db_result'])

def test_block_write_operations(monkeypatch):
    for bad_sql in [
        'INSERT INTO orders (order_date) VALUES (datetime("now"))',
        'UPDATE orders SET order_date = datetime("now") WHERE id = 1',
        'DELETE FROM orders WHERE id = 1',
        'DROP TABLE orders',
        'ALTER TABLE orders ADD COLUMN foo TEXT',
    ]:
        monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return(bad_sql))
        state = run_query('show orders information')
        assert 'SQL validation error' in state['error_message'], f"Expected block for: {bad_sql}"
        assert state['retry_count'] == 3
        assert state['db_result'] == []

def test_multiple_statements(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return('SELECT 1; SELECT 2'))
    state = run_query('multiple queries request')
    assert 'multiple statements' in state['error_message']
    assert state['retry_count'] == 3

def test_drop_table_blocked_and_table_intact(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return('DROP TABLE orders'))
    state = run_query('show me the orders table schema')
    assert 'SQL validation error' in state['error_message']
    from app.database import inspect_schema
    schema = inspect_schema()
    assert 'orders' in schema

def test_malicious_user_input_guardrails(monkeypatch):
    def fail_if_called(*_, **__):
        raise AssertionError('LLM should not be called')
    monkeypatch.setattr('openai.ChatCompletion.create', fail_if_called)
    state = run_query('DROP TABLE orders; -- malicious')
    assert 'Guardrails' in state['error_message']
    assert state['retry_count'] == 3

def test_normal_question_allowed(monkeypatch):
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return('SELECT id FROM orders'))
    state = run_query('How many orders')
    assert state['error_message'] == ''
    assert state['retry_count'] == 0
    assert isinstance(state['db_result'], list)

def test_nested_subquery_allowed(monkeypatch):
    # Valid nested SELECT subquery should be allowed
    nested_sql = "SELECT id FROM (SELECT id, order_date FROM orders)"
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return(nested_sql))
    state = run_query('Get orders using subquery')
    assert state['error_message'] == ''
    assert len(state['db_result']) > 0

def test_nested_write_subquery_blocked(monkeypatch):
    # Nested write operation inside subquery must be rejected by AST walk
    malicious_nested = "SELECT * FROM (DELETE FROM orders)"
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return(malicious_nested))
    state = run_query('Nested exploit test')
    assert 'SQL validation error' in state['error_message']
    assert 'DELETE' in state['error_message'].upper()
    assert state['retry_count'] == 3

def test_comments_and_trailing_semicolon(monkeypatch):
    # Comments and trailing semicolons must be parsed cleanly without false positives
    valid_sql_with_comment = "SELECT id FROM orders; -- get order ids"
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create_return(valid_sql_with_comment))
    state = run_query('List orders with comment')
    assert state['error_message'] == ''
    assert len(state['db_result']) > 0

def test_security_failure_does_not_retry_llm(monkeypatch):
    # Verify security validation stops at END immediately, without triggering reflection retries
    call_count = 0
    def mock_create(*, model, messages, temperature=0):
        nonlocal call_count
        call_count += 1
        return mock.Mock(choices=[mock.Mock(message=mock.Mock(content='DROP TABLE orders'))])
    monkeypatch.setattr('openai.ChatCompletion.create', mock_create)
    state = run_query('Attempt exploit')
    assert call_count == 1  # exactly 1 generation, no retries on security violations
    assert state['retry_count'] == 3
    assert 'SQL validation error' in state['error_message']
