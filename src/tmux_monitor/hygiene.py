# ABOUTME: Stale pane detection and semi-automatic cleanup.
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tmux_monitor.detection import PaneClassification


# Agent commands that indicate the process is still alive.
KNOWN_AGENT_COMMANDS = {"codex", "opencode", "claude", "claude-code"}


@dataclass
class StalePane:
    session: str
    qualified_id: str
    pane_id: str
    agent_type: str
    cwd: str
    last_task: str
    summary: str
    idle_hours: float
    recommendation: str  # "kill" or "keep"


def is_stale(pane: Any, classification: PaneClassification, log_path: Path, days: int = 2) -> bool:
    """Return True if a pane is stale and safe to recommend for cleanup.
    
    Criteria (all must be true):
    - Classification is an agent type (not shell/idle/unknown)
    - Log file hasn't been written to in `days` days (or doesn't exist)
    - current_command is no longer a known agent command (process changed/died)
    """
    if classification.pane_type in ("idle", "shell", "unknown"):
        return False
    
    if not log_path.exists():
        return True
    
    mtime = log_path.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    if age_hours < days * 24:
        return False
    
    cmd = pane.current_command or ""
    # Strip path prefix if present (e.g. /Users/.../.local/bin/codex -> codex)
    cmd_name = Path(cmd).name if "/" in cmd else cmd
    if cmd_name in KNOWN_AGENT_COMMANDS:
        return False
    
    return True


def find_stale_panes(
    sessions: dict[str, list[Any]],
    classifications: dict[str, PaneClassification],
    logs_dir: Path,
    days: int = 2,
    summaries: dict[str, dict[str, Any]] | None = None,
) -> list[StalePane]:
    """Scan all panes and return those that are stale."""
    stale: list[StalePane] = []
    summaries = summaries or {}
    
    for sess_name, panes in sessions.items():
        for pane in panes:
            cls = classifications.get(pane.pane_id)
            if not cls or cls.pane_type in ("idle", "shell", "unknown"):
                continue
            
            log_path = logs_dir / pane.log_filename
            if is_stale(pane, cls, log_path, days=days):
                qid = pane.qualified_id
                idle_hours = 0.0
                if log_path.exists():
                    idle_hours = (time.time() - log_path.stat().st_mtime) / 3600
                
                summary_data = summaries.get(qid, {})
                stale.append(StalePane(
                    session=sess_name,
                    qualified_id=qid,
                    pane_id=pane.pane_id,
                    agent_type=cls.pane_type,
                    cwd=pane.cwd,
                    last_task=summary_data.get("current_task", ""),
                    summary=summary_data.get("summary", ""),
                    idle_hours=idle_hours,
                    recommendation="kill",
                ))
    
    return stale


def format_stale_report(panes: list[StalePane], dry_run: bool = True) -> str:
    lines: list[str] = []
    action = "(dry-run) would kill" if dry_run else "will kill"
    lines.append(f"Stale pane report — {len(panes)} panes flagged for cleanup")
    lines.append("")
    for p in panes:
        lines.append(f"[{p.agent_type}] {p.qualified_id} in session '{p.session}'")
        lines.append(f"  idle:     {p.idle_hours:.1f} hours")
        lines.append(f"  cwd:      {p.cwd}")
        if p.last_task:
            lines.append(f"  task:     {p.last_task}")
        if p.summary:
            lines.append(f"  summary:  {p.summary[:120]}")
        lines.append(f"  action:   {action}")
        lines.append("")
    return "\n".join(lines)


def kill_panes(panes: list[StalePane]) -> dict[str, Any]:
    """Execute tmux kill-pane for each stale pane. Return results."""
    results: dict[str, Any] = {"killed": [], "failed": []}
    for p in panes:
        try:
            subprocess.run(
                ["tmux", "kill-pane", "-t", p.pane_id],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            results["killed"].append(p.qualified_id)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            results["failed"].append({"pane": p.qualified_id, "error": str(exc)})
    return results
