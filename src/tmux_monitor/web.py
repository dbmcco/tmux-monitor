# ABOUTME: Streamlit web frontend for tmux-monitor — single table dashboard.
import json
import time
from pathlib import Path

import streamlit as st

from tmux_monitor.web_model import build_dashboard_rows, filter_dashboard_rows, format_duration

_STATE_DIR = Path.home() / ".local" / "share" / "driftdriver" / "tmux-monitor"


def _load_status() -> dict | None:
    p = _STATE_DIR / "status.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


st.set_page_config(page_title="tmux monitor", page_icon=":satellite:", layout="wide")

status = _load_status()
if status is None:
    st.warning("No status file. Run `driftdriver tmux-monitor heartbeat` first.")
    st.stop()

sessions = status.get("sessions", {})
rows = build_dashboard_rows(status)

col1, col2, col3, col4, col5 = st.columns(5)
agent_count = sum(1 for r in rows if r["is_agent"])
with col1:
    st.metric("Sessions", len(sessions))
with col2:
    st.metric("Total Panes", len(rows))
with col3:
    st.metric("Agent Panes", agent_count)
with col4:
    st.metric("Active Agents", sum(1 for r in rows if r["is_agent"] and r["activity"] == "active"))
with col5:
    ts = status.get("timestamp", "")
    st.metric("Updated", format_duration(ts) if ts else "never")

show_filter, activity_filter = st.columns(2)
with show_filter:
    pane_filter = st.selectbox("Show", ["agents only", "all"], index=0)
with activity_filter:
    activity = st.selectbox("Activity", ["active first", "all activity", "active only", "idle only"], index=0)

display = filter_dashboard_rows(rows, pane_filter, activity)

if not display:
    st.info("No panes match the filter.")
    st.stop()

table_data = []
for r in display:
    table_data.append({
        "Session": r["session"],
        "Pane": r["pane"].split(":")[-1] if ":" in r["pane"] else r["pane"],
        "Title": r["title"],
        "Type": r["type"],
        "Activity": r["activity"],
        "Activity Signal": r["activity_reason"],
        "tmux up": r["tmux_session"],
        "agent up": r["agent_duration"],
        "last output": r["last_output"],
        "CWD": r["cwd"].split("/")[-1] if r["cwd"] else "",
        "Current Task": r["task"],
        "Summary": r["summary"][:200] + ("..." if len(r["summary"]) > 200 else ""),
        "Control": f'tmux send-keys -t {r["pane_id"]}' if r["pane_id"] else "",
    })

st.dataframe(
    table_data,
    width="stretch",
    hide_index=True,
    column_config={
        "Session": st.column_config.TextColumn(width="medium"),
        "Pane": st.column_config.TextColumn(width="small"),
        "Title": st.column_config.TextColumn(width="large"),
        "Type": st.column_config.TextColumn(width="small"),
        "Activity": st.column_config.TextColumn(width="small"),
        "Activity Signal": st.column_config.TextColumn(width="small"),
        "tmux up": st.column_config.TextColumn(width="small"),
        "agent up": st.column_config.TextColumn(width="small"),
        "last output": st.column_config.TextColumn(width="small"),
        "CWD": st.column_config.TextColumn(width="small"),
        "Current Task": st.column_config.TextColumn(width="medium"),
        "Summary": st.column_config.TextColumn(width="large"),
        "Control": st.column_config.TextColumn(width="medium"),
    },
)

# Auto-refresh inline — no sidebar
auto = st.checkbox("Auto-refresh (5s)", value=True)
if auto:
    time.sleep(5)
    st.rerun()
