# ABOUTME: Resume manifest builder and snapshot generator.
from __future__ import annotations

import datetime
import json
import socket
import subprocess
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


def _boot_id() -> str:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "kern.boottime"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _git_state(cwd: str) -> dict[str, Any]:
    if not cwd or not Path(cwd).exists():
        return {"is_repo": False}

    def run_git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    try:
        root = run_git("rev-parse", "--show-toplevel")
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return {"is_repo": False}

    status = ""
    branch = ""
    head = ""
    try:
        status = run_git("status", "--short")
        branch = run_git("branch", "--show-current")
        head = run_git("rev-parse", "--short", "HEAD")
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        pass

    return {
        "is_repo": True,
        "root": root,
        "branch": branch,
        "head": head,
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _auto_resume(agent_type: str, git_state: dict[str, Any], last_task: str) -> dict[str, Any]:
    reasons: list[str] = []
    if agent_type in ("idle", "shell", "unknown"):
        reasons.append("pane is not a known agent")
    if git_state.get("is_repo") and git_state.get("dirty"):
        reasons.append("dirty git worktree")
    if not last_task:
        reasons.append("missing last task summary")
    if not reasons:
        reasons.append("manual approval required")
    return {"safe": False, "reasons": reasons}


def _resume_command(agent_type: str, cwd: str) -> str:
    cmd_template = _RESUME_COMMANDS.get(agent_type, "{cwd}")
    short_cwd = cwd.replace(str(Path.home()), "~") if cwd else ""
    return cmd_template.format(cwd=f"cd {short_cwd}")


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_resume_manifest(
    sessions: dict[str, list[PaneInfo]],
    classifications: dict[str, PaneClassification],
    summaries: dict[str, dict[str, Any]],
    active_since: dict[str, str],
    session_created_at: dict[str, str],
    tmux_version: str = "",
    pane_tails: dict[str, str] | None = None,
    pane_log_paths: dict[str, Path | str] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "last_heartbeat_at": _iso_now(),
        "tmux_version": tmux_version or "unknown",
        "host": socket.gethostname(),
        "boot_id": _boot_id(),
        "sessions": {},
    }
    tails = pane_tails or {}
    log_paths = pane_log_paths or {}
    
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
                "window_name": pane.window_name,
                "pane": pane.pane_index,
                "active_since": active_since.get(qid, ""),
            }
            last_task = ""
            if qid in summaries:
                last_task = summaries[qid].get("current_task", "")
                entry["last_task"] = last_task
                entry["summary"] = summaries[qid].get("summary", "")
            if qid in tails:
                entry["pane_tail"] = tails[qid]
            if qid in log_paths:
                entry["pane_log_path"] = str(log_paths[qid])
            git_state = _git_state(pane.cwd)
            entry["git"] = git_state
            entry["auto_resume"] = _auto_resume(entry["type"], git_state, last_task)
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
            if pd.get("pane_log_path"):
                lines.append(f"    log:    {pd['pane_log_path']}")
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


def format_recovery_report(manifest: dict[str, Any]) -> str:
    lines: list[str] = [
        "Recovery Report",
        f"Last heartbeat: {manifest.get('last_heartbeat_at', 'unknown')}",
        f"Host: {manifest.get('host', 'unknown')}",
    ]
    if manifest.get("boot_id"):
        lines.append(f"Boot ID: {manifest['boot_id']}")
    lines.append("")

    for sess_name, sess_data in manifest.get("sessions", {}).items():
        panes = sess_data.get("panes", {})
        if not panes:
            continue
        lines.append(f"Session: {sess_name}")
        for qid, pd in panes.items():
            lines.append(f"  {qid} [{pd.get('type', '?')}]")
            if pd.get("last_task"):
                lines.append(f"    task: {pd['last_task']}")
            if pd.get("summary"):
                lines.append(f"    summary: {pd['summary'][:160]}")
            lines.append(f"    cwd: {pd.get('cwd', '')}")
            if pd.get("pane_log_path"):
                lines.append(f"    log: {pd['pane_log_path']}")
            auto = pd.get("auto_resume", {})
            reasons = ", ".join(auto.get("reasons", []))
            lines.append(f"    auto-resume: {'safe' if auto.get('safe') else 'paused'}")
            if reasons:
                lines.append(f"    reasons: {reasons}")
        lines.append("")

    lines.extend([
        "Next actions:",
        "  tmux-monitor recovery script --output restore.sh",
        "  Review the script before running it.",
    ])
    return "\n".join(lines)


def generate_recovery_script(manifest: dict[str, Any]) -> str:
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Auto-generated tmux recovery script",
        f"# Generated from heartbeat at {manifest.get('last_heartbeat_at', 'unknown')}",
        "# Post-restart recovery: recreate layout only; agent commands are comments.",
        "",
        "set -euo pipefail",
        "",
    ]

    for sess_name, sess_data in manifest.get("sessions", {}).items():
        panes = list(sess_data.get("panes", {}).items())
        if not panes:
            continue

        first_qid, first_pd = panes[0]
        first_cwd = first_pd.get("cwd") or str(Path.home())
        first_window = first_pd.get("window_name") or str(first_pd.get("window", 0))
        lines.append(
            "tmux has-session -t "
            f"{_single_quote(sess_name)} 2>/dev/null || "
            "tmux new-session -d "
            f"-s {_single_quote(sess_name)} "
            f"-n {_single_quote(first_window)} "
            f"-c {_single_quote(first_cwd)}"
        )
        if first_pd.get("resume_command"):
            lines.append(f"# {first_qid}: agent resume command omitted; inspect recovery report first")

        for qid, pd in panes[1:]:
            cwd = pd.get("cwd") or str(Path.home())
            window = pd.get("window_name") or str(pd.get("window", 0))
            lines.append(
                "tmux new-window "
                f"-t {_single_quote(sess_name)} "
                f"-n {_single_quote(window)} "
                f"-c {_single_quote(cwd)}"
            )
            if pd.get("resume_command"):
                lines.append(f"# {qid}: agent resume command omitted; inspect recovery report first")
        lines.append("")

    lines.append("echo 'Layout restored. Agent resume commands are comments in this script.'")
    return "\n".join(lines)
