# tmux-monitor Intelligence Layer: Resume + Hygiene

**Date:** 2026-05-15  
**Status:** Design approved, awaiting implementation plan  
**Approach:** Snapshot + resume manifest (Approach A)

## Problem Statement

The monitor currently observes, classifies, and summarizes agent panes passively. It does not address two real operational pain points:

1. **Continuity loss:** When tmux server dies, machine reboots, or an agent crashes, the user loses the context of which agents were running where and what they were doing. The agent CLIs (codex, opencode, claude) have `--resume` flags, but the user needs the right session IDs and repo locations to use them.
2. **Window proliferation:** tmux windows and panes accumulate over days. Stale panes (idle for 2+ days, agent process gone) clutter the workspace and the user's mental model.

## Goals

- **Resume snapshot:** On each heartbeat, persist a recoverable manifest of agent panes including session identity, repo, agent type, and any detectable tool session ID. Provide a CLI command to print this snapshot after tmux death.
- **Hygiene loop:** Detect stale panes (no output for 2+ days AND agent process absent). Surface them with last-known context. Allow semi-automatic cleanup via `--approve`.
- **Advisory only:** The monitor is a librarian, not an operator. It surfaces information and generates scripts. The human decides what to kill or resume.

## Non-Goals

- Auto-restarting agents or auto-killing panes without human approval.
- Fragile regex extraction of tool session IDs from terminal output (we'll capture what we can from pane metadata and command lines, not try to parse every CLI's internal state).
- Event-sourced timeline replay or complex TTL registries.

## Architecture

### New Module: `resume.py`

Responsible for:
- Building the resume manifest from the current state on each heartbeat.
- Persisting it to `~/.local/share/driftdriver/tmux-monitor/resume-manifest.json`.
- Reading the manifest after tmux death to produce a human-readable snapshot.
- Generating a shell script to recreate tmux layout (sessions, windows, panes, `cd` commands) without starting agents.

### Resume Manifest Schema

```json
{
  "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
  "tmux_version": "3.4",
  "sessions": {
    "codex-session": {
      "created_at": "2026-05-10T09:00:00+00:00",
      "windows": 2,
      "panes": {
        "codex-session:0.0": {
          "type": "codex",
          "cwd": "/Users/braydon/projects/experiments/driftdriver",
          "title": "codex-aarch64-a: /Users/braydon/projects/experiments/driftdriver",
          "current_command": "codex",
          "last_task": "implementing heartbeat interval config",
          "pane_id": "%123",
          "window": 0,
          "pane": 0,
          "active_since": "2026-05-15T13:00:00+00:00",
          "resume_command": "cd /Users/braydon/projects/experiments/driftdriver && codex --resume"
        }
      }
    }
  }
}
```

### Changes to `daemon.py`

- After `write_status`, call `write_resume_manifest(config, current, classifications, summaries, active_since)`.
- The manifest is a snapshot of the *last successful heartbeat* — overwritten each cycle.

### Changes to `cli.py`

**New subcommands:**

- `tmux-monitor resume-snapshot`
  - Reads `resume-manifest.json`.
  - Prints formatted summary: session, window, pane, repo, agent type, last task, resume command.
  - Exit code 0 if manifest exists, 1 if not.

- `tmux-monitor resume-snapshot --generate-script`
  - Reads manifest, produces `tmux-resume-$(date).sh`.
  - Script creates sessions and windows, cd's to correct dirs, but does NOT run agents.
  - User reviews and runs it manually.

- `tmux-monitor cleanup [--approve] [--dry-run] [--days N]`
  - Scans all current panes for staleness.
  - Staleness criteria (ALL must be true):
    - No new output in the pipe-pane log for `--days` (default 2) days.
    - Agent classification is not "idle" / "shell" / "unknown" (it was an agent pane).
    - The `current_command` from tmux metadata does NOT match known agent commands (process is gone or changed).
  - Advisory output lists each stale pane with:
    - Session, window, pane
    - Agent type, last task, summary
    - Idle duration
    - Recommendation: kill or keep
  - `--approve`: actually kills the recommended panes via `tmux kill-pane`.
  - `--dry-run`: shows what would be done without doing it.

### New Module: `hygiene.py`

Responsible for:
- Checking staleness of a single pane given its log path, classification, and tmux metadata.
- Building the list of stale panes for the `cleanup` command.
- Executing kill commands if `--approve` is passed.

### Staleness Detection Logic

```python
def is_stale(pane: PaneInfo, log_path: Path, days: int = 2) -> bool:
    if pane.classification.pane_type in ("idle", "shell", "unknown"):
        return False  # only flag former agent panes
    if not log_path.exists():
        return True  # no log = no evidence of life
    mtime = log_path.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    if age_hours < days * 24:
        return False  # still writing output
    # Process check: is current_command still the agent?
    if pane.current_command in KNOWN_AGENT_COMMANDS:
        return False  # process still alive
    return True
```

### Changes to `state.py`

- Add `resume_manifest_path` to `TmuxMonitorConfig`.
- `write_resume_manifest(...)` writes the manifest atomically (tmp + replace).

### Error Handling

- If manifest write fails on heartbeat, log error but do not fail the heartbeat.
- If `--approve` kills fail (e.g., pane already dead), log and continue.
- If tmux is not running, `resume-snapshot` still works (reads last manifest). `cleanup` exits with error.

## Testing

- Unit test `hygiene.is_stale` with mocked `stat()` and classification.
- Unit test `resume.write_resume_manifest` and `read_resume_manifest` round-trip.
- Integration test: start a tmux session, attach monitor, kill tmux server, run `resume-snapshot` and verify output.
- Integration test: create a pane, let it idle, run `cleanup --dry-run`, verify it flags the pane. Run `--approve`, verify pane is killed.

## Migration

- No breaking changes to existing CLI or status file format.
- Resume manifest is additive.
- `cleanup` is new; existing users are unaffected.
