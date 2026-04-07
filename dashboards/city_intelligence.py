"""
City Intelligence Dashboard — Task 16

Presents cross-source city analytics from the warehouse layer.
Shows what the pipeline produces — weather, transit, incidents, and
cross-source correlations.

Run locally:
    streamlit run dashboards/city_intelligence.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap — must happen before any other project imports
# ---------------------------------------------------------------------------
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_project_root / "gcp-credentials.json")
sys.path.insert(0, str(_project_root))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dags.utils.bigquery_client import query_bigquery

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ADORE City Intelligence — San Francisco", layout="wide")
st.title("San Francisco City Intelligence")
st.caption("Live data from Open-Meteo, 511.org GTFS-RT, SF 311")


# ---------------------------------------------------------------------------
# Cached data loaders — one per source table, 5-min TTL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_city_summary(start_date, end_date):
    rows = list(query_bigquery(
        f"SELECT * FROM `warehouse.fact_daily_city_summary` "
        f"WHERE date BETWEEN '{start_date}' AND '{end_date}' "
        f"ORDER BY date"
    ))
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_weather_transit_hourly(start_date, end_date):
    rows = list(query_bigquery(
        f"SELECT date_hour, date, hour, is_weekend, is_rush_hour, "
        f"temperature_c, precipitation_mm, avg_delay_seconds "
        f"FROM `warehouse.fact_weather_transit_hourly` "
        f"WHERE DATE(date_hour) BETWEEN '{start_date}' AND '{end_date}' "
        f"ORDER BY date_hour"
    ))
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_transit_performance():
    rows = list(query_bigquery(
        "SELECT route_id, "
        "ROUND(AVG(avg_delay_seconds), 1) AS avg_delay_seconds, "
        "MAX(max_delay_seconds) AS max_delay_seconds, "
        "SUM(trip_count) AS trip_count, "
        "ROUND(AVG(on_time_pct), 1) AS on_time_pct "
        "FROM `warehouse.fact_transit_performance` "
        "GROUP BY route_id "
        "ORDER BY avg_delay_seconds DESC "
        "LIMIT 10"
    ))
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_incident_trends(start_date, end_date):
    rows = list(query_bigquery(
        f"SELECT date, neighborhood, service_name, "
        f"incident_count, open_count, closed_count "
        f"FROM `warehouse.fact_incident_trends` "
        f"WHERE date BETWEEN '{start_date}' AND '{end_date}'"
    ))
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def load_date_range():
    rows = list(query_bigquery(
        "SELECT MIN(date) AS min_date, MAX(date) AS max_date "
        "FROM `warehouse.fact_daily_city_summary`"
    ))
    if rows and rows[0].min_date:
        return rows[0].min_date, rows[0].max_date
    return None, None


# ---------------------------------------------------------------------------
# Sidebar — date range + refresh
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    min_date, max_date = load_date_range()

    if min_date and max_date:
        start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
        end_date   = st.date_input("End date",   value=max_date, min_value=min_date, max_value=max_date)
    else:
        import datetime
        today = datetime.date.today()
        start_date = st.date_input("Start date", value=today - datetime.timedelta(days=14))
        end_date   = st.date_input("End date",   value=today)

    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_summary  = load_city_summary(start_date, end_date)
df_hourly   = load_weather_transit_hourly(start_date, end_date)
df_transit  = load_transit_performance()
df_incidents = load_incident_trends(start_date, end_date)


# ---------------------------------------------------------------------------
# SECTION 1 — City Pulse
# ---------------------------------------------------------------------------
st.header("City Pulse")

if df_summary.empty:
    st.info("No city summary data available for the selected date range.")
else:
    # Latest day's metrics
    latest = df_summary.iloc[-1]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Avg Temperature (°C)",  f"{latest.get('avg_temp_c', '—'):.1f}" if pd.notna(latest.get('avg_temp_c')) else "—")
    c2.metric("Total Precipitation (mm)", f"{latest.get('total_precip_mm', 0):.1f}" if pd.notna(latest.get('total_precip_mm')) else "—")
    c3.metric("Avg Transit Delay (s)", f"{latest.get('avg_delay_seconds', '—'):.0f}" if pd.notna(latest.get('avg_delay_seconds')) else "—")
    c4.metric("Total Incidents",       int(latest['total_incidents']) if pd.notna(latest.get('total_incidents')) else "—")
    c5.metric("Top Incident Category", str(latest.get('top_category', '—')) if pd.notna(latest.get('top_category')) else "—")

    st.caption(f"Latest day: {str(latest['date'])[:10]}")
    st.divider()

    # Daily trend charts
    col_left, col_right = st.columns(2)

    with col_left:
        # Weather trend
        df_weather = df_summary[["date", "avg_temp_c", "total_precip_mm"]].dropna(subset=["avg_temp_c"])
        if not df_weather.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_weather["date"], y=df_weather["avg_temp_c"],
                name="Avg Temp (°C)", mode="lines+markers", line=dict(color="#FF7043")
            ))
            fig.add_trace(go.Bar(
                x=df_weather["date"], y=df_weather["total_precip_mm"],
                name="Precipitation (mm)", marker_color="#42A5F5", opacity=0.5,
                yaxis="y2"
            ))
            fig.update_layout(
                title="Daily Weather",
                yaxis=dict(title="Temperature (°C)"),
                yaxis2=dict(title="Precipitation (mm)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=-0.2),
                height=300, margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No weather data in range.")

    with col_right:
        # Transit and incidents trend
        df_trans_trend = df_summary[["date", "avg_delay_seconds", "total_incidents"]].copy()
        if not df_trans_trend.dropna(subset=["avg_delay_seconds"]).empty or not df_trans_trend.dropna(subset=["total_incidents"]).empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_trans_trend["date"], y=df_trans_trend["avg_delay_seconds"],
                name="Avg Delay (s)", mode="lines+markers", line=dict(color="#7E57C2")
            ))
            fig.add_trace(go.Bar(
                x=df_trans_trend["date"], y=df_trans_trend["total_incidents"],
                name="Total Incidents", marker_color="#EF5350", opacity=0.5,
                yaxis="y2"
            ))
            fig.update_layout(
                title="Daily Transit Delays & Incidents",
                yaxis=dict(title="Avg Delay (s)"),
                yaxis2=dict(title="Incident Count", overlaying="y", side="right"),
                legend=dict(orientation="h", y=-0.2),
                height=300, margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No transit / incident data in range.")


# ---------------------------------------------------------------------------
# SECTION 2 — Weather Impact on Transit
# ---------------------------------------------------------------------------
st.divider()
st.header("Weather Impact on Transit")

if df_hourly.empty:
    st.info("No hourly weather/transit data available for the selected date range.")
else:
    # Ensure correct types
    df_hourly["is_rush_hour"] = df_hourly["is_rush_hour"].astype(bool)
    df_hourly["is_weekend"]   = df_hourly["is_weekend"].astype(bool)

    # Chart 1: Scatter — precipitation vs delay
    df_scatter = df_hourly.dropna(subset=["precipitation_mm", "avg_delay_seconds"])
    if not df_scatter.empty:
        df_scatter = df_scatter.copy()
        df_scatter["Rush Hour"] = df_scatter["is_rush_hour"].map({True: "Rush Hour", False: "Off-Peak"})
        fig = px.scatter(
            df_scatter,
            x="precipitation_mm",
            y="avg_delay_seconds",
            color="Rush Hour",
            color_discrete_map={"Rush Hour": "#FF7043", "Off-Peak": "#42A5F5"},
            labels={"precipitation_mm": "Precipitation (mm)", "avg_delay_seconds": "Avg Delay (s)"},
            title="Precipitation vs Transit Delays",
            opacity=0.7,
            height=380,
        )
        fig.update_traces(marker=dict(size=6))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Each point represents one hour. Rush hours (7–9am, 4–7pm) highlighted.")
    else:
        st.info("No data for scatter plot.")

    col_left, col_right = st.columns(2)

    # Chart 2: Avg delay by hour of day — weekday vs weekend
    with col_left:
        df_hour_pattern = (
            df_hourly.dropna(subset=["avg_delay_seconds"])
            .groupby(["hour", "is_weekend"])["avg_delay_seconds"]
            .mean()
            .reset_index()
        )
        if not df_hour_pattern.empty:
            df_hour_pattern["Day Type"] = df_hour_pattern["is_weekend"].map({True: "Weekend", False: "Weekday"})
            fig = px.line(
                df_hour_pattern,
                x="hour",
                y="avg_delay_seconds",
                color="Day Type",
                color_discrete_map={"Weekday": "#7E57C2", "Weekend": "#26A69A"},
                markers=True,
                labels={"hour": "Hour of Day", "avg_delay_seconds": "Avg Delay (s)"},
                title="Average Transit Delay by Hour of Day",
                height=350,
            )
            fig.update_layout(xaxis=dict(tickmode="linear", dtick=2))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hourly delay pattern data.")

    # Chart 3: Delays + precipitation over time (last 3 days)
    with col_right:
        df_hourly["date_hour"] = pd.to_datetime(df_hourly["date_hour"])
        cutoff = df_hourly["date_hour"].max() - pd.Timedelta(days=3)
        df_recent = df_hourly[df_hourly["date_hour"] >= cutoff].dropna(subset=["avg_delay_seconds"])
        if not df_recent.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_recent["date_hour"], y=df_recent["avg_delay_seconds"],
                name="Avg Delay (s)", mode="lines", line=dict(color="#7E57C2")
            ))
            fig.add_trace(go.Bar(
                x=df_recent["date_hour"], y=df_recent["precipitation_mm"],
                name="Precipitation (mm)", marker_color="#42A5F5", opacity=0.5,
                yaxis="y2"
            ))
            fig.update_layout(
                title="Transit Delays and Precipitation Over Time (Last 3 Days)",
                xaxis=dict(title=""),
                yaxis=dict(title="Avg Delay (s)"),
                yaxis2=dict(title="Precipitation (mm)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=-0.2),
                height=350, margin=dict(t=40, b=60),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No recent delay/precipitation data.")


# ---------------------------------------------------------------------------
# SECTION 3 — Transit Performance
# ---------------------------------------------------------------------------
st.divider()
st.header("Transit Performance")

if df_transit.empty:
    st.info("No transit performance data available.")
else:
    st.subheader("Top 10 Most Delayed Routes")

    col_chart, col_table = st.columns([3, 2])

    with col_chart:
        df_bar = df_transit.sort_values("avg_delay_seconds", ascending=True)
        fig = px.bar(
            df_bar,
            x="avg_delay_seconds",
            y="route_id",
            orientation="h",
            color="on_time_pct",
            color_continuous_scale="RdYlGn",
            labels={"avg_delay_seconds": "Avg Delay (s)", "route_id": "Route", "on_time_pct": "On-Time %"},
            title="Routes by Average Delay (color = on-time %)",
            height=420,
        )
        fig.update_layout(coloraxis_colorbar=dict(title="On-Time %"))
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        display_df = df_transit[["route_id", "avg_delay_seconds", "max_delay_seconds", "trip_count", "on_time_pct"]].copy()
        display_df.columns = ["Route", "Avg Delay (s)", "Max Delay (s)", "Trips", "On-Time %"]
        st.dataframe(display_df, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# SECTION 4 — Incident Analysis
# ---------------------------------------------------------------------------
st.divider()
st.header("Incident Analysis")

if df_incidents.empty:
    st.info("No incident data available for the selected date range.")
else:
    # Chart 1: Top 15 categories
    col_left, col_right = st.columns(2)

    with col_left:
        df_categories = (
            df_incidents.groupby("service_name")["incident_count"]
            .sum()
            .reset_index()
            .sort_values("incident_count", ascending=True)
            .tail(15)
        )
        if not df_categories.empty:
            fig = px.bar(
                df_categories,
                x="incident_count",
                y="service_name",
                orientation="h",
                labels={"incident_count": "Total Incidents", "service_name": "Category"},
                title="Top 15 Incident Categories",
                color="incident_count",
                color_continuous_scale="Reds",
                height=420,
            )
            fig.update_layout(showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No category data.")

    # Chart 2: Top 15 neighborhoods
    with col_right:
        df_neighborhoods = (
            df_incidents.groupby("neighborhood")["incident_count"]
            .sum()
            .reset_index()
            .sort_values("incident_count", ascending=True)
            .tail(15)
        )
        if not df_neighborhoods.empty:
            fig = px.bar(
                df_neighborhoods,
                x="incident_count",
                y="neighborhood",
                orientation="h",
                labels={"incident_count": "Total Incidents", "neighborhood": "Neighborhood"},
                title="Most Active Neighborhoods",
                color="incident_count",
                color_continuous_scale="Oranges",
                height=420,
            )
            fig.update_layout(showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No neighborhood data.")

    # Chart 3: Daily incident volume with closed count
    df_daily_inc = (
        df_incidents.groupby("date")[["incident_count", "closed_count"]]
        .sum()
        .reset_index()
        .sort_values("date")
    )
    if not df_daily_inc.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_daily_inc["date"], y=df_daily_inc["incident_count"],
            name="Total Incidents", mode="lines+markers", line=dict(color="#EF5350")
        ))
        fig.add_trace(go.Scatter(
            x=df_daily_inc["date"], y=df_daily_inc["closed_count"],
            name="Closed", mode="lines+markers", line=dict(color="#66BB6A", dash="dash")
        ))
        fig.update_layout(
            title="Daily Incident Volume",
            xaxis=dict(title=""),
            yaxis=dict(title="Incident Count"),
            legend=dict(orientation="h", y=-0.2),
            height=340, margin=dict(t=40, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No daily incident trend data.")
