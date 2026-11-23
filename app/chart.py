"""
app/chart.py – Dynamic Plotly visualization generator from query result DataFrames.
"""
from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def generate_plotly_chart(df: pd.DataFrame) -> go.Figure | None:
    """Dynamically generate a suitable Plotly chart based on DataFrame schema and data.

    Rules:
    - Never hardcodes chart data.
    - If empty, returns None.
    - If datetime + numeric -> line chart.
    - If categorical/text + numeric -> bar chart.
    - If two or more numeric columns -> scatter or bar chart.
    - If single numeric column -> bar or histogram.
    - If only categorical columns -> value count bar chart.
    """
    if df is None or df.empty:
        return None

    # Detect datetime columns
    datetime_cols: list[str] = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_cols.append(col)
        elif pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            # Try parsing a sample as datetime
            sample = df[col].dropna()
            if not sample.empty:
                try:
                    converted = pd.to_datetime(sample.iloc[:5], format="mixed", errors="coerce")
                    if converted.notna().all():
                        datetime_cols.append(col)
                except Exception:
                    pass

    # Detect numeric columns
    numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]

    # Detect categorical/string columns
    categorical_cols = [
        col for col in df.columns if col not in numeric_cols and col not in datetime_cols
    ]

    title = f"Query Data Visualization ({len(df)} rows)"

    # Case 1: Datetime + Numeric -> Line chart
    if datetime_cols and numeric_cols:
        x_col = datetime_cols[0]
        y_col = numeric_cols[0]
        fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
        return fig

    # Case 2: Categorical + Numeric -> Bar chart
    if categorical_cols and numeric_cols:
        x_col = categorical_cols[0]
        y_col = numeric_cols[0]
        fig = px.bar(df, x=x_col, y=y_col, title=title)
        return fig

    # Case 3: Multiple Numeric columns -> Scatter plot
    if len(numeric_cols) >= 2:
        fig = px.scatter(
            df,
            x=numeric_cols[0],
            y=numeric_cols[1],
            title=title,
        )
        return fig

    # Case 4: Single Numeric column -> Index vs Numeric bar chart
    if len(numeric_cols) == 1:
        y_col = numeric_cols[0]
        fig = px.bar(df, y=y_col, title=title)
        return fig

    # Case 5: Only Categorical columns -> Frequency count chart
    if categorical_cols:
        cat_col = categorical_cols[0]
        counts = df[cat_col].value_counts().reset_index()
        counts.columns = [cat_col, "count"]
        fig = px.bar(counts, x=cat_col, y="count", title=f"Distribution of {cat_col}")
        return fig

    return None
