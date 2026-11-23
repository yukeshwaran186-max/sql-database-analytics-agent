"""
app/guardrails.py – Security guardrails and AST-based SQL validation.

NOTE ON NEMO GUARDRAILS:
NeMo Guardrails (nemoguardrails) is NOT available or installed in this environment
(offline / no network access). User-input security guardrails are implemented via
deterministic pattern-matching policies to block prompt-injections, malicious SQL
structures, and script attacks before LLM invocation, without falsely claiming
integration with the NeMo Guardrails library.
"""
from __future__ import annotations
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# ---------------------------------------------------------------------------
# User-input guardrails (Pre-LLM security check)
# ---------------------------------------------------------------------------

_DANGEROUS_KW = re.compile(
    r"\b(drop|delete|insert|update|alter|truncate|create|replace|merge)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--|#|/\*)")
_SEMICOLON = re.compile(r";")
_SCRIPT_TAG = re.compile(r"<\s*script", re.IGNORECASE)
_UNION_SELECT = re.compile(r"\bunion\b.{0,80}\bselect\b", re.IGNORECASE)
_BYPASS_ATTEMPT = re.compile(
    r"(ignore\s+(all\s+)?previous|disregard\s+instructions?|system\s*prompt)",
    re.IGNORECASE,
)

_INPUT_RULES: list[tuple[re.Pattern, str]] = [
    (_DANGEROUS_KW, "SQL keyword detected in user input"),
    (_COMMENT, "SQL comment pattern detected in user input"),
    (_SEMICOLON, "semicolon detected in user input"),
    (_SCRIPT_TAG, "script tag detected in user input"),
    (_UNION_SELECT, "UNION SELECT injection pattern detected"),
    (_BYPASS_ATTEMPT, "prompt-injection bypass attempt detected"),
]


def check_user_input(user_query: str) -> str | None:
    """Validate user input before LLM invocation.

    Returns an error message if blocked, or None if safe.
    Fail-closed: any detected malicious pattern terminates processing.
    """
    for pattern, reason in _INPUT_RULES:
        if pattern.search(user_query):
            return f"User input blocked by Guardrails: {reason}"
    return None


# ---------------------------------------------------------------------------
# AST-based SQL validation (sqlglot)
# ---------------------------------------------------------------------------

_FORBIDDEN_AST_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    getattr(exp, "AlterTable", exp.Expression),
    exp.Create,
    exp.Command,
)


def validate_sql(sql: str) -> str | None:
    """Validate generated SQL using sqlglot AST parsing.

    Enforces:
    - Must be parseable valid SQL.
    - Exactly one statement (rejects multiple statements, chained queries).
    - Only safe read-only SELECT statements allowed.
    - Rejects write operations (INSERT, UPDATE, DELETE, DROP, ALTER, etc.).
    - Walks AST tree to ensure no write operations are nested inside subqueries.
    - Handles comments and trailing semicolons safely.

    Returns an error message if invalid, or None if valid.
    """
    if not sql or not sql.strip():
        return "SQL validation error: empty SQL statement"

    try:
        parsed_statements = sqlglot.parse(sql, read="sqlite")
    except SqlglotError as err:
        return f"SQL validation error: parse error – {err}"
    except Exception as exc:
        return f"SQL validation error: syntax error – {exc}"

    if not parsed_statements:
        return "SQL validation error: empty SQL statement"

    if len(parsed_statements) > 1:
        return "SQL validation error: multiple statements are not allowed"

    statement = parsed_statements[0]
    if statement is None:
        return "SQL validation error: unable to parse SQL statement"

    # Top-level statement must be a Select expression
    if not isinstance(statement, exp.Select):
        stmt_type = statement.__class__.__name__
        return f"SQL validation error: {stmt_type} statements are not allowed (only SELECT is allowed)"

    # Walk all nodes in the AST to verify no forbidden expressions exist (e.g. in subqueries)
    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_AST_NODES):
            node_type = node.__class__.__name__
            return f"SQL validation error: forbidden {node_type} operation in statement"

    return None
