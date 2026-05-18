# ABOUTME: Pure dashboard row/filter helpers for the Streamlit web frontend.
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INACTIVE_PANE_TYPES = {"shell", "idle", "unknown"}
BUSY_TITLE_MARKERS = frozenset("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
DEFAULT_ACTIVE_WINDOW_SECONDS = 120


def format_duration(iso_str: str | None, now: datetime | None = None) -> str:
    if not iso_str:
        return "-"
    ts = _parse_iso(iso_str)
    if ts is None:
        return "-"
    current = now or datetime.now(timezone.utc)
    secs = max(0, int((current - ts).total_seconds()))
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _parse_iso(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        normalized = iso_str.replace("Z", "+00:00")
        ts = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _window_index_from_pane_key(pane_key: str) -> int | None:
    try:
        _, pane_ref = pane_key.rsplit(":", 1)
        window_ref, _ = pane_ref.split(".", 1)
        return int(window_ref)
    except (ValueError, TypeError):
        return None


def _activity_for_pane(
    pane_data: dict[str, Any],
    *,
    now: datetime,
    active_window_seconds: int,
) -> tuple[str, str]:
    pane_type = pane_data.get("type", "unknown")
    if pane_type in INACTIVE_PANE_TYPES:
        return "idle", "not agent"

    last_output_at = _parse_iso(pane_data.get("last_output_at"))
    if last_output_at is not None:
        age_seconds = (now - last_output_at).total_seconds()
        if 0 <= age_seconds <= active_window_seconds:
            return "active", "recent output"
        return "idle", "no recent output"

    title = pane_data.get("title", "")
    if any(marker in title for marker in BUSY_TITLE_MARKERS):
        return "active", "busy title"

    return "idle", "no recent output"


def build_dashboard_rows(
    status: dict[str, Any],
    *,
    now: datetime | None = None,
    active_window_seconds: int = DEFAULT_ACTIVE_WINDOW_SECONDS,
) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for sess_name, sess_data in status.get("sessions", {}).items():
        sess_created = sess_data.get("created_at", "")
        for pane_key, pane_data in sess_data.get("panes", {}).items():
            activity, activity_reason = _activity_for_pane(
                pane_data,
                now=current,
                active_window_seconds=active_window_seconds,
            )
            cwd = pane_data.get("cwd", "").replace(str(Path.home()), "~")
            window_index = pane_data.get("window")
            if window_index is None:
                window_index = _window_index_from_pane_key(pane_key)
            rows.append({
                "session": sess_name,
                "pane": pane_key,
                "pane_id": pane_data.get("pane_id", ""),
                "window": window_index,
                "window_name": pane_data.get("window_name", ""),
                "window_active": bool(pane_data.get("window_active", False)),
                "type": pane_data.get("type", "?"),
                "title": pane_data.get("title", ""),
                "tmux_session": format_duration(sess_created, current),
                "agent_duration": format_duration(pane_data.get("active_since"), current),
                "last_output": format_duration(pane_data.get("last_output_at"), current),
                "cwd_full": pane_data.get("cwd", ""),
                "cwd": cwd,
                "task": pane_data.get("current_task", ""),
                "summary": pane_data.get("summary", ""),
                "activity": activity,
                "activity_reason": activity_reason,
                "is_agent": pane_data.get("type") not in INACTIVE_PANE_TYPES,
            })

    return rows


def filter_dashboard_rows(
    rows: list[dict[str, Any]],
    pane_filter: str,
    activity_filter: str,
) -> list[dict[str, Any]]:
    if pane_filter == "agents only":
        display = [r for r in rows if r["is_agent"]]
    else:
        display = list(rows)

    if activity_filter == "active only":
        display = [r for r in display if r["activity"] == "active"]
    elif activity_filter == "idle only":
        display = [r for r in display if r["activity"] == "idle"]

    if activity_filter == "active first":
        display.sort(key=lambda r: (0 if r["activity"] == "active" else 1, r["session"], r["pane"]))

    return display
