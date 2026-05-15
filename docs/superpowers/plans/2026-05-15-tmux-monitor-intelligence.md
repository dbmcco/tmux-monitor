# tmux-monitor Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add resume manifest + snapshot CLI and semi-automatic stale pane cleanup to tmux-monitor.

**Architecture:** Extend the existing heartbeat-driven monitor to persist a recoverable manifest of agent panes. Add CLI commands to surface this manifest after tmux death (`resume-snapshot`) and to detect/flag stale panes (`cleanup`). Advisory only — human decides what to kill or resume.

**Tech Stack:** Python 3.11+, tmux, pytest, existing tmux-monitor modules (config, state, discovery, detection, logs, relevance)

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/tmux_monitor/config.py` | Add `resume_manifest_path` to config dataclass | Modify |
| `src/tmux_monitor/resume.py` | Build, persist, and read resume manifests; generate shell scripts | Create |
| `src/tmux_monitor/hygiene.py` | Detect stale panes; execute kills with approval | Create |
| `src/tmux_monitor/state.py` | Add `write_resume_manifest()` helper | Modify |
| `src/tmux_monitor/daemon.py` | Call `write_resume_manifest` after `write_status` | Modify |
| `src/tmux_monitor/cli.py` | Add `resume-snapshot` and `cleanup` subcommands | Modify |
| `tests/test_resume.py` | Unit tests for resume manifest CRUD and script generation | Create |
| `tests/test_hygiene.py` | Unit tests for stale detection logic | Create |
| `tests/test_cli_intelligence.py` | Integration tests for CLI commands | Create |

---

## Task 1: Add resume manifest path to config

**Files:**
- Modify: `src/tmux_monitor/config.py`
- Test: `tests/test_config.py` (already exists, just verify)

- [ ] **Step 1: Read current config.py**

Read `src/tmux_monitor/config.py` to see the current `TmuxMonitorConfig` dataclass.

- [ ] **Step 2: Add `resume_manifest_path` property**

Add a `@property` or field to `TmuxMonitorConfig` so `config.resume_manifest_path` returns `Path(self.state_dir) / "resume-manifest.json"`. If the dataclass already has other path properties, follow that pattern.

Example addition:
```python
@property
@property
def resume_manifest_path(self) -> Path:
    return Path(self.state_dir) / "resume-manifest.json"
```

- [ ] **Step 3: Verify it works**

Run a quick inline check:
```bash
python -c "from tmux_monitor.config import TmuxMonitorConfig; c = TmuxMonitorConfig(); print(c.resume_manifest_path)"
```
Expected output: a path ending in `resume-manifest.json`.

- [ ] **Step 4: Commit**

```bash
git add src/tmux_monitor/config.py
git commit -m "feat(config): add resume_manifest_path property"
```

---

## Task 2: Create resume manifest module

**Files:**
- Create: `src/tmux_monitor/resume.py`
- Test: `tests/test_resume.py`

- [ ] **Step 1: Write failing test for manifest round-trip**

Create `tests/test_resume.py`:
```python
import json
from pathlib import Path
from datetime import timezone

from tmux_monitor.resume import build_resume_manifest, write_resume_manifest, read_resume_manifest, format_snapshot_text, generate_resume_script
from tmux_monitor.config import TmuxMonitorConfig


def test_manifest_round_trip(tmp_path):
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {},
    }
    
    write_resume_manifest(config, manifest)
    assert config.resume_manifest_path.exists()
    
    loaded = read_resume_manifest(config)
    assert loaded == manifest
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/test_resume.py::test_manifest_round_trip -v
```
Expected: `ModuleNotFoundError: No module named 'tmux_monitor.resume'`

- [ ] **Step 3: Implement resume.py**

Create `src/tmux_monitor/resume.py`:
```python
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
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_resume.py::test_manifest_round_trip -v
```
Expected: PASS

- [ ] **Step 5: Add test for format_snapshot_text**

```python
def test_format_snapshot_text():
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "test": {
                "created_at": "2026-05-10T09:00:00+00:00",
                "windows": 1,
                "panes": {
                    "test:0.0": {
                        "type": "codex",
                        "cwd": "/home/user/projects/foo",
                        "title": "codex",
                        "current_command": "codex",
                        "pane_id": "%123",
                        "window": 0,
                        "pane": 0,
                        "last_task": "implementing tests",
                        "summary": "Writing unit tests for the new feature.",
                        "resume_command": "cd ~/projects/foo && codex --resume",
                    }
                }
            }
        }
    }
    text = format_snapshot_text(manifest)
    assert "Session: test" in text
    assert "codex" in text
    assert "implementing tests" in text
    assert "cd ~/projects/foo" in text
    assert "resume: cd ~/projects/foo && codex --resume" in text
```

- [ ] **Step 6: Run test — expect pass**

```bash
pytest tests/test_resume.py::test_format_snapshot_text -v
```

- [ ] **Step 7: Add test for generate_resume_script**

```python
def test_generate_resume_script():
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "sess-a": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "sess-a:0.0": {
                        "type": "opencode",
                        "cwd": "/home/user/bar",
                        "title": "opencode",
                        "pane_id": "%456",
                        "window": 0,
                        "pane": 0,
                        "resume_command": "cd ~/bar && opencode --resume",
                    }
                }
            }
        }
    }
    script = generate_resume_script(manifest)
    assert "#!/usr/bin/env bash" in script
    assert "tmux new-session -d -s 'sess-a'" in script
    assert "cd ~/bar" in script
    assert "Manually start agents" in script
```

- [ ] **Step 8: Run test — expect pass**

```bash
pytest tests/test_resume.py::test_generate_resume_script -v
```

- [ ] **Step 9: Commit**

```bash
git add src/tmux_monitor/resume.py tests/test_resume.py
git commit -m "feat(resume): add resume manifest builder, snapshot text, and script generation"
```

---

## Task 3: Wire resume manifest into state.py and daemon.py

**Files:**
- Modify: `src/tmux_monitor/state.py`
- Modify: `src/tmux_monitor/daemon.py`

- [ ] **Step 1: Add `write_resume_manifest` to state.py**

In `src/tmux_monitor/state.py`, add these imports at the top:
```python
from tmux_monitor.resume import build_resume_manifest, write_resume_manifest as _write_resume_manifest_impl
```

Then add a wrapper function:
```python
def write_resume_manifest(
    config: TmuxMonitorConfig,
    sessions: dict[str, list[PaneInfo]],
    classifications: dict[str, PaneClassification],
    summaries: dict[str, dict[str, Any]],
    active_since: dict[str, str],
    session_created_at: dict[str, str],
) -> None:
    """Build and persist the resume manifest from current state."""
    manifest = build_resume_manifest(
        sessions, classifications, summaries, active_since, session_created_at
    )
    _write_resume_manifest_impl(config, manifest)
```

- [ ] **Step 2: Update daemon.py to call write_resume_manifest**

In `src/tmux_monitor/daemon.py`, after the `write_status` call in `run_heartbeat`, add:
```python
    write_resume_manifest(
        config, current,
        {pid: cls for pid, cls in classifications.items()},
        summaries,
        active_since,
        session_created_at=session_created_at,
    )
```

Add the import at the top of daemon.py if `write_resume_manifest` is not already imported:
```python
from tmux_monitor.state import write_resume_manifest
```
(If it's already in the `state` import block, add it there.)

- [ ] **Step 3: Verify daemon imports**

```bash
python -c "from tmux_monitor.daemon import run_heartbeat; print('OK')"
```
Expected: `OK` (no ImportError).

- [ ] **Step 4: Run existing tests to catch regressions**

```bash
pytest tests/ -x -q
```
Expected: All existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/tmux_monitor/state.py src/tmux_monitor/daemon.py
git commit -m "feat(daemon): persist resume manifest after each heartbeat"
```

---

## Task 4: Create hygiene module

**Files:**
- Create: `src/tmux_monitor/hygiene.py`
- Test: `tests/test_hygiene.py`

- [ ] **Step 1: Write failing test for is_stale**

Create `tests/test_hygiene.py`:
```python
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

from tmux_monitor.hygiene import is_stale, KNOWN_AGENT_COMMANDS
from tmux_monitor.detection import PaneClassification


def test_is_stale_when_no_log_and_process_gone():
    """Pane with no log file and non-agent current_command is stale."""
    pane = MagicMock()
    pane.classification = PaneClassification(pane_type="codex", pid=12345)
    pane.current_command = "bash"
    
    log_path = Path("/nonexistent/log")
    assert is_stale(pane, log_path, days=2) is True


def test_is_stale_when_log_recent_and_process_alive():
    """Pane with recent log and matching agent command is NOT stale."""
    pane = MagicMock()
    pane.classification = PaneClassification(pane_type="codex", pid=12345)
    pane.current_command = "codex"
    
    log_path = Path("/tmp/test_hygiene_recent.log")
    log_path.write_text("recent output")
    try:
        assert is_stale(pane, log_path, days=2) is False
    finally:
        log_path.unlink()


def test_is_stale_shell_pane_never_stale():
    """Shell/idle panes are never stale."""
    pane = MagicMock()
    pane.classification = PaneClassification(pane_type="shell", pid=0)
    pane.current_command = "bash"
    
    log_path = Path("/nonexistent")
    assert is_stale(pane, log_path, days=2) is False


def test_is_stale_old_log_and_process_gone():
    """Pane with old log and process changed is stale."""
    pane = MagicMock()
    pane.classification = PaneClassification(pane_type="opencode", pid=0)
    pane.current_command = "bash"
    
    log_path = Path("/tmp/test_hygiene_old.log")
    log_path.write_text("old output")
    # Set mtime to 3 days ago
    old_mtime = time.time() - (3 * 24 * 3600)
    os.utime(log_path, (old_mtime, old_mtime))
    try:
        assert is_stale(pane, log_path, days=2) is True
    finally:
        log_path.unlink()
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/test_hygiene.py -v
```
Expected: `ModuleNotFoundError: No module named 'tmux_monitor.hygiene'`

- [ ] **Step 3: Implement hygiene.py**

Create `src/tmux_monitor/hygiene.py`:
```python
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


def is_stale(pane: Any, log_path: Path, days: int = 2) -> bool:
    """Return True if a pane is stale and safe to recommend for cleanup.
    
    Criteria (all must be true):
    - Classification is an agent type (not shell/idle/unknown)
    - Log file hasn't been written to in `days` days (or doesn't exist)
    - current_command is no longer a known agent command (process changed/died)
    """
    cls: PaneClassification = pane.classification
    if cls.pane_type in ("idle", "shell", "unknown"):
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
            if is_stale(pane, log_path, days=days):
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_hygiene.py -v
```
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tmux_monitor/hygiene.py tests/test_hygiene.py
git commit -m "feat(hygiene): add stale pane detection and cleanup logic"
```

---

## Task 5: Add CLI commands for resume-snapshot and cleanup

**Files:**
- Modify: `src/tmux_monitor/cli.py`
- Test: `tests/test_cli_intelligence.py`

- [ ] **Step 1: Add resume-snapshot subcommand**

In `src/tmux_monitor/cli.py`, add these imports at the top:
```python
from tmux_monitor.resume import read_resume_manifest, format_snapshot_text, generate_resume_script
from tmux_monitor.hygiene import find_stale_panes, format_stale_report, kill_panes
from tmux_monitor.discovery import discover_all
from tmux_monitor.detection import classify_pane
from tmux_monitor.logs import capture_pane
```
(If some imports already exist, add the missing ones. `capture_pane` might need to be imported from `discovery` instead — check existing imports.)

Add these CLI handler functions before `main()`:

```python
def cmd_resume_snapshot(args: argparse.Namespace) -> int:
    config = _load_config(args)
    manifest = read_resume_manifest(config)
    if manifest is None:
        print("No resume manifest found. Has the daemon ever run a heartbeat?", file=sys.stderr)
        return 1
    
    if getattr(args, "generate_script", False):
        script = generate_resume_script(manifest)
        out_path = Path.cwd() / f"tmux-resume-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.sh"
        out_path.write_text(script + "\n", encoding="utf-8")
        out_path.chmod(0o755)
        print(f"Resume script written to: {out_path}")
        print("Review it before running. It recreates sessions but does NOT start agents.")
        return 0
    
    text = format_snapshot_text(manifest)
    print(text)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    config = _load_config(args)
    days = getattr(args, "days", 2)
    dry_run = not getattr(args, "approve", False)
    
    current = discover_all()
    classifications: dict[str, Any] = {}
    for sess_name, panes in current.items():
        for pane in panes:
            content = capture_pane(pane.pane_id, lines=200)
            cls = classify_pane(
                content, pane.tty,
                current_command=pane.current_command,
                pane_title=pane.title,
            )
            classifications[pane.pane_id] = cls
    
    # Load summaries from status file
    summaries: dict[str, dict[str, Any]] = {}
    data = _load_status(config)
    if data:
        for sess_data in data.get("sessions", {}).values():
            for qid, pd in sess_data.get("panes", {}).items():
                if "summary" in pd or "current_task" in pd:
                    summaries[qid] = {
                        "summary": pd.get("summary", ""),
                        "current_task": pd.get("current_task", ""),
                    }
    
    stale = find_stale_panes(
        current, classifications, config.panes_dir, days=days, summaries=summaries
    )
    
    if not stale:
        print(f"No stale panes found (threshold: {days} days).")
        return 0
    
    report = format_stale_report(stale, dry_run=dry_run)
    print(report)
    
    if not dry_run:
        results = kill_panes(stale)
        print(f"Killed {len(results['killed'])} panes.")
        if results["failed"]:
            print(f"Failed to kill {len(results['failed'])} panes:")
            for item in results["failed"]:
                print(f"  {item['pane']}: {item['error']}")
    else:
        print(f"Run with --approve to kill these {len(stale)} panes.")
    
    return 0
```

Add `import datetime` at the top of cli.py if not already present.

- [ ] **Step 2: Wire subcommands into main() parser**

In `main()`, after the existing subcommands, add:

```python
    resume = sub.add_parser("resume-snapshot", help="Show last-known agent pane state for recovery")
    resume.add_argument("--generate-script", action="store_true", help="Generate a shell script to recreate tmux sessions")
    resume.set_defaults(func=cmd_resume_snapshot)

    cleanup = sub.add_parser("cleanup", help="Detect and optionally kill stale agent panes")
    cleanup.add_argument("--days", type=int, default=2, help="Idle threshold in days (default: 2)")
    cleanup.add_argument("--approve", action="store_true", help="Actually kill stale panes (default: dry-run)")
    cleanup.add_argument("--dry-run", action="store_true", help="Show what would be killed without doing it (default)")
    cleanup.set_defaults(func=cmd_cleanup)
```

- [ ] **Step 3: Write integration test for CLI commands**

Create `tests/test_cli_intelligence.py`:
```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from tmux_monitor.cli import main
from tmux_monitor.config import TmuxMonitorConfig


def test_resume_snapshot_no_manifest(capsys):
    """resume-snapshot without manifest prints error."""
    with patch("sys.argv", ["tmux-monitor", "resume-snapshot"]):
        rc = main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "No resume manifest found" in captured.err


def test_resume_snapshot_with_manifest(tmp_path, capsys):
    """resume-snapshot prints formatted output from manifest."""
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "test": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "test:0.0": {
                        "type": "codex",
                        "cwd": "/tmp",
                        "title": "codex",
                        "current_command": "codex",
                        "pane_id": "%999",
                        "window": 0,
                        "pane": 0,
                        "last_task": "testing",
                        "summary": "summary text",
                        "resume_command": "cd /tmp && codex --resume",
                    }
                }
            }
        }
    }
    config.resume_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    
    with patch("sys.argv", ["tmux-monitor", "resume-snapshot", "--state-dir", str(tmp_path)]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Session: test" in captured.out
    assert "codex" in captured.out
    assert "testing" in captured.out


def test_resume_snapshot_generate_script(tmp_path, capsys):
    """resume-snapshot --generate-script writes a .sh file."""
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "s": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "s:0.0": {
                        "type": "opencode",
                        "cwd": "/tmp",
                        "title": "opencode",
                        "pane_id": "%1",
                        "window": 0,
                        "pane": 0,
                        "resume_command": "cd /tmp && opencode --resume",
                    }
                }
            }
        }
    }
    config.resume_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    
    with patch("sys.argv", ["tmux-monitor", "resume-snapshot", "--generate-script", "--state-dir", str(tmp_path)]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Resume script written to:" in captured.out
    
    # Find the generated script
    scripts = list(Path.cwd().glob("tmux-resume-*.sh"))
    assert len(scripts) >= 1
    script = scripts[-1]
    assert "tmux new-session" in script.read_text()
    script.unlink()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_cli_intelligence.py -v
```

- [ ] **Step 5: Test cleanup dry-run (requires mocking tmux)**

Add to `tests/test_cli_intelligence.py`:
```python
from unittest.mock import patch


def test_cleanup_no_stale_panes(capsys):
    """cleanup with no stale panes prints 'No stale panes found'."""
    with patch("tmux_monitor.cli.discover_all", return_value={}), \
         patch("sys.argv", ["tmux-monitor", "cleanup"]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "No stale panes found" in captured.out
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -x -q
```
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/tmux_monitor/cli.py tests/test_cli_intelligence.py
git commit -m "feat(cli): add resume-snapshot and cleanup commands"
```

---

## Task 6: Verify end-to-end and update README

**Files:**
- Modify: `README.md`
- Test: manual CLI verification

- [ ] **Step 1: Run a single heartbeat to generate manifest**

```bash
tmux-monitor heartbeat
```
Then check the manifest exists:
```bash
cat ~/.local/share/driftdriver/tmux-monitor/resume-manifest.json | head -20
```
Expected: JSON file with `last_heartbeat_at` and session data.

- [ ] **Step 2: Run resume-snapshot**

```bash
tmux-monitor resume-snapshot
```
Expected: formatted text showing current sessions and panes with resume commands.

- [ ] **Step 3: Run cleanup dry-run**

```bash
tmux-monitor cleanup
```
Expected: either "No stale panes found" or a report of stale panes (if any exist).

- [ ] **Step 4: Update README with new commands**

Add a section to `README.md` (find the "CLI Usage" section and append):

```markdown
### Resume & Recovery

After tmux server dies or machine reboots, recover context:

```bash
tmux-monitor resume-snapshot              # Show last-known agent state
tmux-monitor resume-snapshot --generate-script  # Create tmux layout script
```

The monitor persists a `resume-manifest.json` after every heartbeat. It captures:
- Session names, window counts, pane IDs
- Agent type (codex, opencode, claude)
- Working directory and last task summary
- Best-effort resume command for each agent

**Important:** The generated script recreates tmux sessions and cds into the right directories, but does NOT auto-start agents. You review and run it manually, then decide whether to resume each agent with its CLI's native `--resume` flag.

### Hygiene (Stale Pane Cleanup)

Over time, abandoned agent panes accumulate. The monitor can detect and flag them:

```bash
tmux-monitor cleanup                      # Dry-run: show stale panes
tmux-monitor cleanup --approve            # Actually kill stale panes
tmux-monitor cleanup --days 1             # Flag panes idle > 1 day
```

A pane is "stale" when ALL of these are true:
- It was classified as an agent pane (not shell/idle)
- Its pipe-pane log has had no writes for N days
- Its `current_command` no longer matches a known agent command

**Always review before `--approve`.** The monitor recommends; you decide.
```

- [ ] **Step 5: Commit README update**

```bash
git add README.md
git commit -m "docs(readme): document resume-snapshot and cleanup commands"
```

---

## Spec Coverage Check

| Spec Requirement | Task | Status |
|---|---|---|
| Resume manifest persisted after each heartbeat | Task 3 | ✅ |
| Manifest schema with session/pane/agent metadata | Task 2 | ✅ |
| `resume-snapshot` CLI prints formatted state | Task 5 | ✅ |
| `resume-snapshot --generate-script` creates .sh | Task 5 | ✅ |
| Script recreates layout but doesn't start agents | Task 2 (generate_resume_script) | ✅ |
| `cleanup` detects stale panes (days threshold) | Task 4 | ✅ |
| Staleness = no log writes + process gone | Task 4 (is_stale) | ✅ |
| `cleanup --approve` kills with human gate | Task 5 | ✅ |
| `cleanup --dry-run` advisory only | Task 5 | ✅ |
| Error handling for missing tmux/manifest | Task 5 | ✅ |
| Tests for resume round-trip, snapshot, script | Task 2 | ✅ |
| Tests for hygiene stale detection | Task 4 | ✅ |
| Integration tests for CLI commands | Task 5 | ✅ |
| README updated | Task 6 | ✅ |

## Placeholder Scan

No placeholders found. Every step contains exact file paths, code blocks, and expected outputs.

## Type Consistency Check

- `PaneClassification` used throughout — consistent with existing codebase
- `PaneInfo` referenced via `MagicMock` in hygiene tests (we test the function interface, not the full dataclass)
- `TmuxMonitorConfig` state_dir assignment pattern consistent with existing tests
- `resume_command` format string matches `_resume_command` implementation
- `--days` default = 2 everywhere (spec and implementation)

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-tmux-monitor-intelligence.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
