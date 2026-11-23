"""
app.py – Streamlit Interface & Plotly Dashboard for SQL & Database Analytics Agent.
"""
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.database import init_db, inspect_schema, engine
from app.graph import run_query
from app.chart import generate_plotly_chart

# Page configuration
st.set_page_config(
    page_title="SQL & Database Analytics Agent",
    page_icon="🔍",
    layout="wide",
)

# Initialize database on startup
init_db()

# Sidebar: Schema information and database tools
with st.sidebar:
    st.header("🗄️ Database Inspector")
    schema = inspect_schema()
    if schema:
        st.success("Connected to SQLite Database")
        for table_name, columns in schema.items():
            with st.expander(f"Table: `{table_name}`", expanded=True):
                st.write("**Columns:**")
                for col in columns:
                    st.markdown(f"- `{col}`")
    else:
        st.warning("No tables found. Initializing database...")

    st.divider()
    st.markdown("### ⚙️ Environment")
    st.caption(f"DB Engine: `{engine.url.drivername}`")
    api_key_status = "Configured" if os.getenv("OPENAI_API_KEY") else "Mock / Not Set"
    st.caption(f"OpenAI Key: `{api_key_status}`")

# Main Page Header
st.title("📊 SQL & Database Analytics Agent")
st.markdown(
    "Ask natural language questions about your database. "
    "The agent generates validated SQL, reflects on errors, and renders dynamic visualizations."
)

# ── Session state bootstrap ──────────────────────────────────────────────────
if "pending_query" not in st.session_state:
    st.session_state.pending_query = ""
if "run_now" not in st.session_state:
    st.session_state.run_now = False

# Sample question pills (above the form so they fire on the SAME rerun)
st.markdown("**Sample queries:**")
sample_cols = st.columns(3)
if sample_cols[0].button("📋 Show all orders", use_container_width=True):
    st.session_state.pending_query = "Show all order IDs and their dates"
    st.session_state.run_now = True
if sample_cols[1].button("🔢 Count total orders", use_container_width=True):
    st.session_state.pending_query = "How many total orders are there"
    st.session_state.run_now = True
if sample_cols[2].button("🛡️ Test blocked DROP query", use_container_width=True):
    st.session_state.pending_query = "DROP TABLE orders; -- malicious"
    st.session_state.run_now = True

# User Query Input Form
with st.form("query_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        user_query = st.text_input(
            "Enter your database question:",
            placeholder="e.g. Show all order IDs and their dates",
            value=st.session_state.pending_query,
            label_visibility="collapsed",
        )
    with col2:
        submitted = st.form_submit_button("Run Query", use_container_width=True)

# When the form is submitted manually, store it in session state
if submitted and user_query:
    st.session_state.pending_query = user_query
    st.session_state.run_now = True

# Determine final query to run
run_now = st.session_state.run_now
user_query = st.session_state.pending_query if run_now else ""

# Reset the trigger so a page refresh doesn't re-execute
if run_now:
    st.session_state.run_now = False

if run_now and user_query:
    st.divider()
    with st.spinner("Processing query via LangGraph agent..."):
        state = run_query(user_query)

    generated_sql = state.get("generated_sql", "")
    db_result = state.get("db_result", [])
    error_message = state.get("error_message", "")
    retry_count = state.get("retry_count", 0)

    # 1. Security Alert or Error Display
    if error_message:
        if "Guardrails" in error_message:
            st.error(f"🛡️ **Security Alert (Guardrails Blocked Input):** {error_message}")
        elif "SQL validation error" in error_message:
            st.error(f"🛡️ **Security Alert (AST Validation Blocked Query):** {error_message}")
        else:
            st.error(f"⚠️ **Database / Execution Error:** {error_message}")

    # 2. Readable SQL Window
    if generated_sql:
        st.subheader("📝 Generated SQL")
        st.code(generated_sql, language="sql")
    elif not error_message:
        st.info("No SQL generated.")

    # 3. Results Table & Plotly Chart
    if db_result:
        df = pd.DataFrame(db_result)
        st.subheader("📋 Query Results")
        st.dataframe(df, use_container_width=True)
        st.caption(f"Returned {len(df)} row(s).")

        # Dynamic Plotly Visualization
        st.subheader("📈 Dynamic Visualization")
        fig = generate_plotly_chart(df)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Results table is not suitable for graphical visualization.")
    elif not error_message and generated_sql:
        st.info("Query executed successfully, but returned 0 rows.")

    # 4. Collapsible SQL Execution & Self-Correction Logs
    with st.expander("🔍 SQL Execution & Self-Correction Logs", expanded=bool(error_message)):
        st.markdown(f"- **User Query:** `{user_query}`")
        st.markdown(f"- **Self-Correction Retries Used:** `{retry_count}` / 3")
        status_label = "❌ Blocked / Failed" if error_message else "✅ Successful"
        st.markdown(f"- **Final Execution Status:** {status_label}")
        if error_message:
            st.markdown(f"- **Reported Error:** `{error_message}`")
        st.json(
            {
                "retry_count": retry_count,
                "error_message": error_message,
                "has_generated_sql": bool(generated_sql),
                "row_count": len(db_result),
            }
        )
