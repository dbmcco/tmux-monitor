# Unexpected Restart Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend tmux-monitor so unexpected restarts leave a durable recovery manifest, a human-readable report, a restore script, and an optional launchd boot helper.

**Architecture:** Keep recovery in the existing resume module and CLI. Add focused pure functions for manifest enrichment and script/report generation, then wire them into the heartbeat and launchd service choices.

**Tech Stack:** Python 3.11+, pytest, tmux, launchd plist helpers.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/tmux_monitor/resume.py` | Rich recovery manifest, report formatting, restore script generation |
| `src/tmux_monitor/state.py` | Pass pane log paths and captured tails into manifest writer |
| `src/tmux_monitor/daemon.py` | Continue writing the richer manifest every heartbeat |
| `src/tmux_monitor/launchd.py` | Add `recovery` LaunchAgent service |
| `src/tmux_monitor/cli.py` | Add `recovery` subcommands |
| `tests/test_resume.py` | Manifest/report/script behavior |
| `tests/test_launchd.py` | Recovery plist behavior |
| `tests/test_cli_intelligence.py` | CLI command behavior |

## Tasks

- [ ] Add failing tests for git state enrichment, pane-tail/log-path capture, auto-resume safety, and recovery report output.
- [ ] Implement the minimal resume module changes to pass those tests.
- [ ] Add failing tests for recovery restore script generation.
- [ ] Implement script generation without auto-starting agents by default.
- [ ] Add failing tests for `launchd` recovery service plist.
- [ ] Implement recovery service support in `launchd.py` and CLI choices.
- [ ] Add failing tests for `tmux-monitor recovery` subcommands.
- [ ] Implement CLI wiring.
- [ ] Run focused tests and install/refresh the launchd recovery service if verification passes.
