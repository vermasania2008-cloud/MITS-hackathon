"""Streamlit page for office sustainability records and analytics."""

from datetime import date, datetime
import math
import os
import sqlite3

import pandas as pd
import streamlit as st

import backend


st.set_page_config(page_title="Sustainability records", page_icon=":material/eco:", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f7f9f7; color: #202824; }
    [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e6ebe7; }
    h1, h2, h3 { color: #202824; }
    [data-testid="stMetric"] {
        background: #fff; border: 1px solid #e6ebe7; border-radius: 6px;
        min-height: 120px; padding: 14px;
    }
    [data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    backend.initialize_database()
    emission_factor = float(os.environ["ELECTRICITY_EMISSION_FACTOR_KG_PER_KWH"])
    if not math.isfinite(emission_factor) or emission_factor <= 0:
        raise ValueError("The configured electricity emission factor must be positive.")
except KeyError:
    emission_factor = None
except ValueError as error:
    st.error(f"Invalid electricity emission factor: {error}")
    st.stop()
except (OSError, sqlite3.Error) as error:
    st.error(f"Could not open the sustainability database: {error}")
    st.stop()

start, end, previous_start, previous_end = backend.reporting_period()
source = backend.get_source()

with st.sidebar:
    st.markdown("### Sustainability")
    st.caption("Records & analytics")
    if st.button("Refresh data", icon=":material/refresh:", width="stretch"):
        st.rerun()

try:
    with st.spinner("Loading records..."):
        current = backend.get_records(start, end, source)
        previous = backend.get_records(previous_start, previous_end, source)
        current = backend.prepare_records(current, emission_factor)
        previous = backend.prepare_records(previous, emission_factor)
        updated_at = backend.last_updated(source)
        metrics, insights = backend.summarize(current, previous)
except (OSError, sqlite3.Error) as error:
    st.error(f"Could not load sustainability records: {error}")
    st.stop()

title, report = st.columns((2.5, 1.2), vertical_alignment="top")
with title:
    st.title("Sustainability Overview")
    st.caption("Office resource use and environmental impact over the last 30 days.")
with report:
    st.markdown("**Reporting period**")
    st.write(f"{start:%b %d}–{end:%b %d, %Y}")
    if updated_at:
        try:
            timestamp = datetime.fromisoformat(updated_at).astimezone().strftime("%b %d, %H:%M")
            st.caption(f"Last updated {timestamp}")
        except ValueError:
            st.caption(f"Last updated {updated_at}")
    st.download_button(
        "Export records",
        current.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"),
        file_name=f"sustainability-{end.isoformat()}.csv",
        mime="text/csv",
        disabled=source is None,
        icon=":material/download:",
    )

if source == "sample":
    st.caption("Sample data — illustrative only, not office measurements.")
elif source is None:
    st.info("No records yet. Add daily data in the SQLite database to begin.")

st.subheader("Last 30 days")
kpi_columns = st.columns(4)
kpis = (
    ("Electricity", "electricity_kwh", "kWh"),
    ("Water", "water_litres", "L"),
    ("Waste", "total_waste_kg", "kg"),
    ("CO2e", "carbon_emissions_kg", "kg CO2e"),
)
for column, (label, metric, unit) in zip(kpi_columns, kpis, strict=True):
    values = metrics[metric]
    total = values["total"]
    value = "—" if total is None else f"{total:,.1f}"
    change = values["change"]
    delta = f"{change:+.1f}%" if change is not None else None
    with column:
        st.metric(label, value, delta=delta, delta_color="inverse")
        st.caption(unit)

st.caption("Change compares with the previous 30 days. A decrease is an improvement.")

st.subheader("Daily trends")
left, right = st.columns(2)
chart_metrics = (
    (left, "electricity_kwh", "Electricity", "kWh"),
    (right, "water_litres", "Water", "L"),
)
for column, metric, label, unit in chart_metrics:
    with column:
        values = pd.to_numeric(current[metric], errors="coerce")
        st.markdown(f"**{label} ({unit})**")
        if values.notna().any():
            chart_data = pd.DataFrame({label: values.to_numpy()}, index=current["record_date"])
            st.line_chart(chart_data, y=label, height=285)
        else:
            st.caption(f"No {label.lower()} data")

values = pd.to_numeric(current["total_waste_kg"], errors="coerce")
st.markdown("**Waste generated (kg)**")
if values.notna().any():
    waste_data = pd.DataFrame({"Waste": values.to_numpy()}, index=current["record_date"])
    st.bar_chart(waste_data, y="Waste", height=260)
else:
    st.caption("No waste data")

st.subheader("Daily records")
search_col, date_col = st.columns((1, 1.5))
with search_col:
    search = st.text_input("Search by date", placeholder="YYYY-MM-DD")
with date_col:
    chosen_dates = st.date_input(
        "Date range",
        value=(start, end),
        min_value=start,
        max_value=end,
    )

table = current.copy()
table["record_date"] = pd.to_datetime(table["record_date"]).dt.strftime("%Y-%m-%d")
table = table.rename(
    columns={
        "record_date": "Date",
        "electricity_kwh": "Electricity (kWh)",
        "water_litres": "Water (L)",
        "total_waste_kg": "Waste (kg)",
        "recyclable_waste_kg": "Recycled waste (kg)",
        "carbon_emissions_kg": "CO2e (kg)",
    }
)
if search.strip():
    table = table[table["Date"].str.contains(search.strip(), case=False, regex=False)]
if isinstance(chosen_dates, (tuple, list)) and chosen_dates:
    table = table[table["Date"] >= chosen_dates[0].isoformat()]
    if len(chosen_dates) == 2:
        table = table[table["Date"] <= chosen_dates[1].isoformat()]
elif isinstance(chosen_dates, date):
    table = table[table["Date"] == chosen_dates.isoformat()]
table = table[["Date", "Electricity (kWh)", "Water (L)", "Waste (kg)", "Recycled waste (kg)", "CO2e (kg)"]]
st.dataframe(table, hide_index=True, width="stretch")
st.download_button(
    "Download filtered CSV",
    table.to_csv(index=False).encode("utf-8"),
    file_name="sustainability-records.csv",
    mime="text/csv",
    disabled=table.empty,
)
st.caption("Blank values mean no measurement was recorded.")

st.subheader("Key insights")
if insights:
    for insight in insights:
        st.write(f"• {insight}")
else:
    st.caption("Insights appear when there is enough recorded data to compare.")

if emission_factor is not None:
    st.caption(
        f"CO2e uses reported emissions when available; missing values use electricity × "
        f"{emission_factor:g} kg CO2e/kWh."
    )
else:
    st.caption("CO2e uses reported values only. Set an authoritative electricity factor to estimate emissions.")
