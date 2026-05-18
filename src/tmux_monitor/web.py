# ABOUTME: Streamlit web frontend for tmux-monitor — single table dashboard.
import json
import time
from pathlib import Path

import streamlit as st

from tmux_monitor.actions import kill_window, new_session, new_window, start_codex_window
from tmux_monitor.web_model import (
    build_dashboard_rows,
    filter_dashboard_rows,
    find_row_by_key,
    format_duration,
)

_STATE_DIR = Path.home() / ".local" / "share" / "driftdriver" / "tmux-monitor"


def _load_status() -> dict | None:
    p = _STATE_DIR / "status.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _selected_rows(event: object) -> list[int]:
    if not event:
        return []
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return []
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows", [])
    return list(rows or [])


def _selected_row_key(display: list[dict], indexes: list[int]) -> str | None:
    if not indexes:
        return None
    idx = indexes[0]
    if idx < 0 or idx >= len(display):
        return None
    return display[idx].get("row_key")


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

with st.expander("Create tmux session or window"):
    create_cols = st.columns(4)
    session_names = sorted(sessions.keys())
    with create_cols[0]:
        create_session = st.selectbox("Session", session_names, index=0) if session_names else ""
    with create_cols[1]:
        create_window_name = st.text_input("Window name", value="")
    with create_cols[2]:
        create_cwd = st.text_input("Directory", value=str(Path.home()))
    with create_cols[3]:
        new_session_name = st.text_input("New session", value="")

    create_path = Path(create_cwd).expanduser()
    make_window, make_session = st.columns(2)
    with make_window:
        if st.button("New window", disabled=not create_session or not create_path.exists()):
            result = new_window(create_session, create_window_name, create_path)
            if result.ok:
                st.success("Created tmux window.")
                st.rerun()
            else:
                st.error(result.message)
    with make_session:
        if st.button("New session", disabled=not new_session_name or not create_path.exists()):
            result = new_session(new_session_name, create_path)
            if result.ok:
                st.success("Created tmux session.")
                st.rerun()
            else:
                st.error(result.message)

if not display:
    st.info("No panes match the filter.")
    st.stop()

table_data = []
selected_key = st.session_state.get("selected_window_key")
selected_display_index = None
for r in display:
    if r.get("row_key") == selected_key:
        selected_display_index = len(table_data)
    table_data.append({
        "Selected": "*" if r.get("row_key") == selected_key else "",
        "Session": r["session"],
        "Window": r["window_name"] or r["title"],
        "Window #": r["window"] if r["window"] is not None else "",
        "Pane": r["pane"].split(":")[-1] if ":" in r["pane"] else r["pane"],
        "Pane Title": r["title"],
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

event = st.dataframe(
    table_data,
    width="stretch",
    hide_index=True,
    key="monitor_table",
    on_select="rerun",
    selection_mode="single-row",
    selection_default=(
        {"selection": {"rows": [selected_display_index]}}
        if selected_display_index is not None
        else None
    ),
    column_config={
        "Selected": st.column_config.TextColumn(width="small"),
        "Session": st.column_config.TextColumn(width="medium"),
        "Window": st.column_config.TextColumn(width="medium"),
        "Window #": st.column_config.TextColumn(width="small"),
        "Pane": st.column_config.TextColumn(width="small"),
        "Pane Title": st.column_config.TextColumn(width="large"),
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

selected_indexes = _selected_rows(event)
clicked_key = _selected_row_key(display, selected_indexes)
if clicked_key:
    st.session_state["selected_window_key"] = clicked_key

selected = find_row_by_key(rows, st.session_state.get("selected_window_key"))
if selected is not None:
    st.divider()
    st.subheader("Selected window")
    st.caption(
        f'{selected["session"]}:{selected["window"]} '
        f'| {selected["window_name"] or selected["title"]} '
        f'| {selected["cwd"]}'
    )

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("Start Codex here"):
            cwd = Path(selected["cwd_full"]).expanduser()
            if not cwd.exists():
                st.error(f"Directory does not exist: {cwd}")
            else:
                result = start_codex_window(selected["session"], cwd)
                if result.ok:
                    st.success("Started Codex in a new tmux window.")
                    st.rerun()
                else:
                    st.error(result.message)
    with action_cols[1]:
        confirm_key = f'confirm_kill_{selected["session"]}_{selected["window"]}'
        confirm = st.checkbox("Confirm kill", key=confirm_key)
    with action_cols[2]:
        can_kill = confirm and selected["window"] is not None
        if st.button("Kill window", disabled=not can_kill):
            result = kill_window(selected["session"], int(selected["window"]))
            if result.ok:
                st.session_state.pop("selected_window_key", None)
                st.success("Killed tmux window.")
                st.rerun()
            else:
                st.error(result.message)
    if st.button("Clear selection"):
        st.session_state.pop("selected_window_key", None)
        st.rerun()

# Auto-refresh inline — no sidebar
auto = st.checkbox("Auto-refresh (5s)", value=True)
if auto:
    time.sleep(5)
    st.rerun()
