# SQL & Database Analytics Agent

An intelligent, self-correcting SQL and Database Analytics Agent with AST security validation, input guardrails, and an interactive Streamlit & Plotly dashboard.

---

## Architecture & Technology Stack

- **Language & Runtime:** Python 3.11
- **State Management & Agent Flow:** [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph with conditional routing and self-correction reflection)
- **Database Layer:** [SQLAlchemy 2.x](https://www.sqlalchemy.org/) + [SQLite](https://sqlite.org/)
- **SQL Security & AST Parsing:** [SQLGlot 23.2.0](https://github.com/tobymao/sqlglot)
- **LLM Integration:** OpenAI API (`gpt-3.5-turbo` / mock for offline testing)
- **Interactive UI & Dashboard:** [Streamlit](https://streamlit.io/) + [Plotly](https://plotly.com/)
- **Testing:** [pytest](https://docs.pytest.org/)

---

## Workflow Graph

```
                   [inspect_schema]
                          │
                          ▼
                    [guardrails] ────────────► (Blocked Input) ──► [END]
                          │ (Safe)
                          ▼
                    [generate_sql]
                          │
                          ▼
                    [validate_sql] ──────────► (AST Violation) ──► [END]
                          │ (Valid SELECT)
                          ▼
                    [execute_query]
                          │
                          ▼
                    [reflection] ────────────► (DB Error & retry < 3) ──► [generate_sql]
                          │ (Success or max retries)
                          ▼
                        [END]
```

1. **`inspect_schema`**: Automatically extracts table and column metadata using SQLAlchemy.
2. **`guardrails`**: Evaluates raw user prompts before LLM generation to intercept SQL injection, comments, script tags, and prompt injection attempts.
3. **`generate_sql`**: Generates read-only SQLite SELECT queries based on the user query and schema.
4. **`validate_sql`**: Parses the SQL with official **SQLGlot AST**, strictly enforcing read-only `SELECT` statements and rejecting write operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, etc.) or multiple chained statements.
5. **`execute_query`**: Safely executes validated read-only SQL against SQLite.
6. **`reflection`**: On database runtime errors (e.g., non-existent columns), increments `retry_count` and passes the error back to the generator for self-correction (up to 3 retries).

---

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── database.py       # SQLite connection, session factory, schema inspection
│   ├── models.py         # SQLAlchemy Order model (id, order_date)
│   ├── graph.py          # LangGraph StateGraph workflow and conditional routing
│   ├── guardrails.py     # SQLGlot AST validation & pre-LLM input guardrails
│   └── chart.py          # Dynamic Plotly visualization generator
├── configs/
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── test_database.py  # Phase 1 SQLite & schema inspection tests
│   ├── test_graph.py     # Phase 2 LangGraph generation & self-correction tests
│   ├── test_security.py  # Phase 3 SQLGlot AST & security guardrails tests
│   └── test_ui.py        # Phase 4 Plotly chart & UI flow tests
├── app.py                # Streamlit web dashboard
├── database.db           # Seeded SQLite database with sample orders
├── requirements.txt      # Pinned project dependencies
├── .env.example          # Environment variable template
└── README.md             # Project documentation
```

---

## Setup & Running Instructions

### 1. Environment Setup

```powershell
# Clone or navigate to the repository
cd "Sql&database agent"

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Add your `OPENAI_API_KEY` in `.env` if using live OpenAI API calls. For testing and local offline use, mock responses are included.

### 3. Launching the Streamlit Dashboard

```powershell
streamlit run app.py
```

Features in the dashboard:
- Natural language input for database questions
- Sample query buttons (*Show all orders*, *Count total orders*, *Test blocked DROP query*)
- Interactive SQL code viewer
- Dynamic query result data tables
- Automatic interactive Plotly charts (time-series lines, category bars, scatter plots)
- Collapsible self-correction & execution diagnostics
- Database schema inspector in the sidebar

### 4. Running the Test Suite

```powershell
python -m pytest -q
```

All 23 automated unit and integration tests execute headlessly against an in-memory SQLite database.

---

## Security & Implementation Notes

- **SQLGlot AST Validation:** Uses the official `sqlglot==23.2.0` package to inspect query Abstract Syntax Trees. Only top-level `exp.Select` expressions are allowed. Recursive AST walking blocks write operations nested within subqueries.
- **Input Guardrails & NeMo Guardrails Status:** Raw user input is guarded by deterministic fail-closed filters intercepting injection patterns before LLM invocation. While `nemoguardrails` is listed in requirements, pre-trained neural embedding rails rely on external model downloads over network connections. The local fail-closed input guardrail ensures safe, zero-latency, offline execution.
