"""
app/graph.py – LangGraph SQL generation workflow (Phase 2 + Phase 3).

Flow:
  inspect_schema → guardrails ──(blocked?)──► END
                             └─(safe)──► generate_sql → validate_sql ──(blocked?)──► END
                                                                    └─(valid)──► execute_query → reflection
                                                                                                    ├─(error, retries<3)─► generate_sql
                                                                                                    └─(ok or max retries)─► END
"""
from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import StateGraph, END
from sqlalchemy import text
import openai

from app.database import inspect_schema, engine
from app.guardrails import check_user_input, validate_sql


# ---------------------------------------------------------------------------
# State schema (TypedDict required by LangGraph ≥ 1.x)
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    user_query:    str
    generated_sql: str
    db_result:     list
    error_message: str
    retry_count:   int
    schema:        dict


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def inspect_schema_node(state: GraphState) -> GraphState:
    """Populate schema from the live database."""
    state["schema"] = inspect_schema()
    return state


def guardrails_node(state: GraphState) -> GraphState:
    """Block malicious user input before LLM invocation (fail-closed).
    If blocked, set error_message and set retry_count=3 to prevent retries.
    """
    error = check_user_input(state["user_query"])
    if error:
        state["error_message"] = error
        state["retry_count"] = 3   # Security failure: cannot be retried
    return state


def generate_sql_node(state: GraphState) -> GraphState:
    """Call the LLM (or mock) to generate a SQL query."""
    user_query = state["user_query"]
    schema = state.get("schema", {})
    prev_error = state.get("error_message", "")
    prev_sql = state.get("generated_sql", "")

    prompt = (
        "Generate a read-only SQLite SELECT statement for the request: "
        f"{user_query}. Use only tables/columns from the schema: {schema}."
    )
    if prev_error and prev_sql:
        prompt += (
            f" The previous query was: '{prev_sql}' which failed with error: '{prev_error}'. "
            "Please correct the query using only existing columns from the schema."
        )
    prompt += " Return only the SQL string."

    response = openai.ChatCompletion.create(
        model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    state["generated_sql"] = response.choices[0].message.content.strip()
    state["error_message"] = ""   # clear previous error before validation
    return state


def validate_sql_node(state: GraphState) -> GraphState:
    """AST-validate the generated SQL with sqlglot.
    Reject non-SELECT, write/destructive operations, or multiple statements.
    On security validation failure, set retry_count=3 so it cannot be retried.
    """
    error = validate_sql(state["generated_sql"])
    if error:
        state["error_message"] = error
        state["retry_count"] = 3   # Security violation: terminate immediately, no retries
    return state


def execute_query_node(state: GraphState) -> GraphState:
    """Execute the validated SQL; store rows or capture db error for reflection."""
    if state.get("error_message"):
        return state          # Never execute if validation failed
    sql = state["generated_sql"]
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            state["db_result"] = [dict(row._mapping) for row in result]
        state["error_message"] = ""
    except Exception as exc:
        state["db_result"] = []
        state["error_message"] = str(exc)
    return state


def reflection_node(state: GraphState) -> GraphState:
    """Increment retry_count if there is a retriable database error."""
    if state.get("error_message") and state.get("retry_count", 0) < 3:
        state["retry_count"] = state["retry_count"] + 1
    return state


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_guardrails(state: GraphState) -> str:
    """Skip LLM generation entirely if guardrails blocked the input."""
    if state.get("error_message"):
        return END
    return "generate_sql"


def _route_after_validate(state: GraphState) -> str:
    """Terminate immediately at END on SQL security validation failure."""
    if state.get("error_message"):
        return END
    return "execute_query"


def _route_after_reflection(state: GraphState) -> str:
    """Loop back to generate_sql if there is a retriable error and retries remain."""
    if state.get("error_message") and state.get("retry_count", 0) < 3:
        return "generate_sql"
    return END


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

graph = StateGraph(GraphState)

graph.add_node("inspect_schema", inspect_schema_node)
graph.add_node("guardrails",     guardrails_node)
graph.add_node("generate_sql",   generate_sql_node)
graph.add_node("validate_sql",   validate_sql_node)
graph.add_node("execute_query",  execute_query_node)
graph.add_node("reflection",     reflection_node)

graph.set_entry_point("inspect_schema")
graph.add_edge("inspect_schema", "guardrails")

# Conditional: if guardrails blocked input, go straight to END without calling LLM
graph.add_conditional_edges(
    "guardrails",
    _route_after_guardrails,
    {"generate_sql": "generate_sql", END: END},
)

graph.add_edge("generate_sql", "validate_sql")

# Conditional: if SQL validation blocked query, go straight to END without execution
graph.add_conditional_edges(
    "validate_sql",
    _route_after_validate,
    {"execute_query": "execute_query", END: END},
)

graph.add_edge("execute_query", "reflection")

# Conditional: if execution error, reflection decides whether to retry
graph.add_conditional_edges(
    "reflection",
    _route_after_reflection,
    {"generate_sql": "generate_sql", END: END},
)

runnable = graph.compile()


def run_query(user_query: str) -> dict:
    """Entry-point: run the full workflow and return the final state."""
    init_state: GraphState = {
        "user_query":    user_query,
        "generated_sql": "",
        "db_result":     [],
        "error_message": "",
        "retry_count":   0,
        "schema":        {},
    }
    return runnable.invoke(init_state)


__all__ = ["run_query", "runnable", "GraphState"]
