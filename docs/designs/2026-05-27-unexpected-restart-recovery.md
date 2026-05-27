# Unexpected Restart Recovery

**Date:** 2026-05-27
**Status:** Approved for implementation

## Goal

Make unexpected machine restarts recoverable by continuously writing enough tmux, pane, agent, repository, and service state to disk that a boot-time helper can reconstruct the workspace and relaunch agents cautiously.

## Design

`tmux-monitor` remains the owner because it already discovers panes, captures pane logs, classifies agents, summarizes work, and installs launchd services. The existing `resume-manifest.json` becomes a richer recovery manifest rather than adding a parallel recorder.

On each heartbeat the monitor records:

- session/window/pane identity and cwd
- pane log path and recent captured pane tail
- agent type, task summary, active time, and resume command
- lightweight git state for pane cwd when it is inside a repository
- whether the pane is eligible for cautious auto-resume
- machine boot/session metadata used to detect unclean restarts

Recovery is advisory by default. The boot helper runs at login, waits briefly for tmux-monitor to be available, reads the latest manifest, writes a recovery report, and exits unless `--restore-layout` or `--relaunch-agents` is explicitly requested. The generated restore script recreates sessions/windows and opens shells in the right directories; agent relaunch commands include a context prompt and are marked as paused unless the manifest says auto-resume is safe.

## Non-Goals

- Preserve process memory after a hard restart.
- Auto-commit or auto-push dirty repositories.
- Blindly relaunch all agents after login.
- Replace `agentmem`; this layer may ingest events later, but the manifest remains the canonical restore artifact.

## CLI Shape

```bash
tmux-monitor recovery snapshot
tmux-monitor recovery report
tmux-monitor recovery script --output restore.sh
tmux-monitor recovery boot-check
tmux-monitor launchd install --service recovery
```

Existing `resume-snapshot` remains as a compatibility alias.
