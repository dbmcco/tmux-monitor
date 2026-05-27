# ABOUTME: Core daemon loop — heartbeat-driven tmux session monitoring.
from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.detection import classify_pane
from tmux_monitor.discovery import (
    PaneInfo,
    attach_pipe,
    capture_pane,
    detach_pipe,
    discover_all,
)
from tmux_monitor.logs import trim_all_logs
from tmux_monitor.state import (
    append_event,
    load_known_sessions,
    prune_old_daily,
    save_known_sessions,
    write_resume_manifest,
    write_status,
)
from tmux_monitor.summarizer import run_summarization_cycle


_RUNNING = True


def _handle_signal(signum: int, frame: Any) -> None:
    global _RUNNING
    _RUNNING = False


def _detach_all_pipes(known: dict[str, Any]) -> None:
    for sess_name, pane_ids in known.get("panes", {}).items():
        for pane_id in pane_ids:
            detach_pipe(pane_id)


def run_heartbeat(config: TmuxMonitorConfig) -> dict[str, Any]:
    known = load_known_sessions(config)
    current = discover_all()

    current_pane_ids: dict[str, list[str]] = {}
    classifications: dict[str, Any] = {}
    pane_tails: dict[str, str] = {}
    summaries: dict[str, dict[str, Any]] = known.get("summaries", {})
    active_since: dict[str, str] = known.get("active_since", {})
    session_created_at: dict[str, str] = known.get("session_created_at", {})

    events_emitted: list[str] = []

    known_sessions = set(known.get("sessions", []))
    current_sessions = set(current.keys())

    import datetime as _dt
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()

    for sess in current_sessions - known_sessions:
        append_event(config, "session.appeared", session=sess, pane_id="")
        events_emitted.append(f"session.appeared:{sess}")
        session_created_at[sess] = now_iso

    for sess in known_sessions - current_sessions:
        append_event(config, "session.disappeared", session=sess, pane_id="")
        events_emitted.append(f"session.disappeared:{sess}")
        session_created_at.pop(sess, None)

    for sess_name, panes in current.items():
        current_pane_ids[sess_name] = []

        known_pane_ids = set(
            known.get("panes", {}).get(sess_name, [])
        )

        for pane in panes:
            current_pane_ids[sess_name].append(pane.pane_id)

            if pane.pane_id not in known_pane_ids:
                log_path = config.panes_dir / pane.log_filename
                attach_pipe(pane.pane_id, log_path)
                append_event(
                    config, "pane.created",
                    session=sess_name, pane_id=pane.qualified_id,
                    cwd=pane.cwd,
                )
                events_emitted.append(f"pane.created:{pane.qualified_id}")

            content = capture_pane(pane.pane_id, lines=200)
            pane_tails[pane.qualified_id] = content
            prev_cls = known.get("classifications", {}).get(pane.pane_id, {})
            cls = classify_pane(
                content, pane.tty,
                current_command=pane.current_command,
                pane_title=pane.title,
            )
            classifications[pane.pane_id] = cls

            prev_type = prev_cls.get("type", "") if isinstance(prev_cls, dict) else ""
            if cls.pane_type != prev_type and prev_type:
                if prev_type != "idle" and prev_type != "shell":
                    append_event(
                        config, "agent.stopped",
                        session=sess_name, pane_id=pane.qualified_id,
                        agent_type=prev_type,
                    )
                    events_emitted.append(f"agent.stopped:{pane.qualified_id}")
                if cls.pane_type not in ("idle", "shell", "unknown"):
                    append_event(
                        config, "agent.started",
                        session=sess_name, pane_id=pane.qualified_id,
                        agent_type=cls.pane_type,
                    )
                    active_since[pane.qualified_id] = (
                        __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat()
                    )
                    events_emitted.append(f"agent.started:{pane.qualified_id}")
            elif cls.pane_type not in ("idle", "shell", "unknown"):
                if pane.qualified_id not in active_since:
                    active_since[pane.qualified_id] = (
                        __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat()
                    )

        current_pane_set = {p.pane_id for p in panes}
        for old_id in known_pane_ids - current_pane_set:
            detach_pipe(old_id)
            append_event(
                config, "pane.destroyed",
                session=sess_name, pane_id=old_id,
            )
            events_emitted.append(f"pane.destroyed:{old_id}")

    trimmed = trim_all_logs(config)
    pruned = prune_old_daily(config)

    agent_panes: dict[str, Path] = {}
    for sess_name, panes in current.items():
        for pane in panes:
            cls = classifications.get(pane.pane_id)
            if cls and cls.pane_type not in ("idle", "shell", "unknown"):
                log_path = config.panes_dir / pane.log_filename
                if log_path.exists() and log_path.stat().st_size > 0:
                    agent_panes[pane.qualified_id] = log_path

    _last_summary_at = known.get("last_summary_at", "")
    _should_summarize = bool(agent_panes)
    if _should_summarize and _last_summary_at:
        import datetime as _dt2
        try:
            _last_dt = _dt2.datetime.fromisoformat(_last_summary_at)
            _elapsed = (_dt2.datetime.now(_dt2.timezone.utc) - _last_dt).total_seconds()
            _should_summarize = _elapsed >= config.llm_summary_interval_seconds
        except ValueError:
            _should_summarize = True

    if _should_summarize and agent_panes:
        try:
            summaries = run_summarization_cycle(config, agent_panes, summaries)
            _last_summary_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        except Exception as exc:
            print(f"tmux-monitor: summarization error: {exc}", file=sys.stderr)

    new_known: dict[str, Any] = {
        "sessions": list(current_sessions),
        "panes": current_pane_ids,
        "classifications": {
            pid: cls.to_dict() for pid, cls in classifications.items()
        },
        "summaries": summaries,
        "active_since": active_since,
        "session_created_at": session_created_at,
        "last_summary_at": _last_summary_at,
    }
    save_known_sessions(config, new_known)

    write_status(
        config, current,
        {pid: cls for pid, cls in classifications.items()},
        summaries,
        active_since,
        session_created_at=session_created_at,
    )

    write_resume_manifest(
        config, current,
        {pid: cls for pid, cls in classifications.items()},
        summaries,
        active_since,
        session_created_at=session_created_at,
        pane_tails=pane_tails,
    )

    return {
        "sessions": len(current_sessions),
        "panes": sum(len(p) for p in current.values()),
        "events": events_emitted,
        "logs_trimmed": trimmed,
        "daily_pruned": pruned,
    }


def run_daemon(config: TmuxMonitorConfig) -> None:
    global _RUNNING
    _RUNNING = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.panes_dir.mkdir(parents=True, exist_ok=True)
    config.daily_dir.mkdir(parents=True, exist_ok=True)
    config.save(config.state_dir / "config.json")

    print(f"tmux-monitor: daemon started (state_dir={config.state_dir})", file=sys.stderr)

    while _RUNNING:
        try:
            result = run_heartbeat(config)
            import datetime
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(
                f"[{now}] heartbeat: {result['sessions']} sessions, "
                f"{result['panes']} panes, "
                f"{len(result['events'])} events"
                + (f", {result['logs_trimmed']} trimmed" if result["logs_trimmed"] else ""),
                file=sys.stderr,
            )
        except Exception as exc:
            print(f"tmux-monitor: heartbeat error: {exc}", file=sys.stderr)

        import datetime as _dt
        hour = _dt.datetime.now().hour
        interval = config.heartbeat_interval(hour)

        deadline = time.monotonic() + interval
        while _RUNNING and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    _detach_all_pipes(load_known_sessions(config))
    print("tmux-monitor: daemon stopped", file=sys.stderr)
