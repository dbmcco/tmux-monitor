# ABOUTME: Resume manifest builder and snapshot generator.
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.detection import PaneClassification
from tmux_monitor.discovery import PaneInfo


# Mapping of agent types to their best-effort resume commands.
# These are advisory — the human decides whether to run them.
_RESUME_COMMANDS: dict[str, str] = {
    "codex": "{cwd} && codex --resume",
    "opencode": "{cwd} && opencode --resume",
    "claude-code": "{cwd} && claude --resume",
    "claude": "{cwd} && claude --resume",
    "unknown": "{cwd}",
}


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _resume_command(agent_type: str, cwd: str) -> str:
    cmd_template = _RESUME_COMMANDS.get(agent_type, "{cwd}")
    short_cwd = cwd.replace(str(Path.home()), "~") if cwd else ""
    return cmd_template.format(cwd=f"cd {short_cwd}")


def build_resume_manifest(
    sessions: dict[str, list[PaneInfo]],
    classifications: dict[str, PaneClassification],
    summaries: dict[str, dict[str, Any]],
    active_since: dict[str, str],
    session_created_at: dict[str, str],
    tmux_version: str = "",
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "last_heartbeat_at": _iso_now(),
        "tmux_version": tmux_version or "unknown",
        "sessions": {},
    }
    
    for sess_name, panes in sessions.items():
        session_data: dict[str, Any] = {
            "created_at": session_created_at.get(sess_name, ""),
            "windows": len({p.window for p in panes}),
            "panes": {},
        }
        for pane in panes:
            qid = pane.qualified_id
            cls = classifications.get(pane.pane_id)
            if cls and cls.pane_type in ("idle", "shell", "unknown"):
                continue  # only track agent panes in resume manifest
            
            entry: dict[str, Any] = {
                "type": cls.pane_type if cls else "unknown",
                "cwd": pane.cwd,
                "title": pane.title,
                "current_command": pane.current_command,
                "pane_id": pane.pane_id,
                "window": pane.window,
                "pane": pane.pane_index,
                "active_since": active_since.get(qid, ""),
            }
            if qid in summaries:
                entry["last_task"] = summaries[qid].get("current_task", "")
                entry["summary"] = summaries[qid].get("summary", "")
            entry["resume_command"] = _resume_command(
                entry["type"], pane.cwd
            )
            session_data["panes"][qid] = entry
        manifest["sessions"][sess_name] = session_data
    
    return manifest


def write_resume_manifest(config: TmuxMonitorConfig, manifest: dict[str, Any]) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    tmp = config.resume_manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config.resume_manifest_path)


def read_resume_manifest(config: TmuxMonitorConfig) -> dict[str, Any] | None:
    path = config.resume_manifest_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def format_snapshot_text(manifest: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Last heartbeat: {manifest.get('last_heartbeat_at', 'unknown')}")
    lines.append(f"tmux version: {manifest.get('tmux_version', 'unknown')}")
    lines.append("")
    
    for sess_name, sess_data in manifest.get("sessions", {}).items():
        panes = sess_data.get("panes", {})
        if not panes:
            continue
        lines.append(f"Session: {sess_name}  (created {sess_data.get('created_at', '?')})")
        for qid, pd in panes.items():
            lines.append(f"  {qid}  [{pd.get('type', '?')}]")
            if pd.get("last_task"):
                lines.append(f"    task:   {pd['last_task']}")
            if pd.get("summary"):
                lines.append(f"    summary: {pd['summary'][:120]}")
            short_cwd = pd.get("cwd", "").replace(str(Path.home()), "~")
            lines.append(f"    cwd:    {short_cwd}")
            lines.append(f"    resume: {pd.get('resume_command', '')}")
            lines.append("")
    
    return "\n".join(lines)


def generate_resume_script(manifest: dict[str, Any]) -> str:
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Auto-generated tmux resume script",
        f"# Generated from heartbeat at {manifest.get('last_heartbeat_at', 'unknown')}",
        "",
        "set -euo pipefail",
        "",
    ]
    
    first = True
    for sess_name, sess_data in manifest.get("sessions", {}).items():
        panes = sess_data.get("panes", {})
        if not panes:
            continue
        
        if first:
            lines.append(f"tmux new-session -d -s '{sess_name}'")
            first = False
        else:
            lines.append(f"tmux new-session -d -s '{sess_name}'")
        
        for qid, pd in panes.items():
            cwd = pd.get("cwd", "")
            if cwd:
                short_cwd = cwd.replace(str(Path.home()), "~")
                lines.append(f"  tmux send-keys -t '{sess_name}' 'cd {short_cwd}' C-m")
            # Do NOT auto-start the agent — user decides
        lines.append("")
    
    lines.append("echo 'Sessions recreated. Manually start agents in each pane.'")
    return "\n".join(lines)
