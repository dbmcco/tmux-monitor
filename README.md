# tmux-monitor

A heartbeat daemon that watches all tmux panes across all sessions, detects which coding agents are running (Claude Code, Codex, OpenCode, Kilocode, pi.dev), captures their output, generates AI-powered summaries of what each agent is doing, and exposes file-based state for other agents to consume.

Built for the speedrift ecosystem — coding agents and paia-agents use this to coordinate, avoid conflicts, and understand what work is happening across tmux.

## What It Does

When you have 20+ coding agents running in tmux, you need to answer:

- **Which agents are running?** — what type, in which session/pane, working in which repo
- **What are they doing?** — current task, trajectory over time, cross-session collaboration
- **Which ones are relevant to me?** — filtering by repo relevance
- **How do I control them?** — pane IDs for `tmux send-keys` control

tmux-monitor answers all four. It runs as a background daemon, continuously capturing pane output via `tmux pipe-pane`, classifying agents via process metadata and content heuristics, summarizing activity via Ollama, and writing structured state to disk.

## Architecture

```
tmux sessions
    │
    ▼
┌──────────────────────────────────────────────┐
│  Heartbeat Loop (30s day / 1hr night)        │
│                                              │
│  1. Discover sessions/panes (tmux list-*)    │
│  2. Attach pipe-pane to new panes            │
│  3. Detach from gone panes                   │
│  4. Trim pane logs (512KB max)               │
│  5. Classify each pane (process + title)     │
│  6. Summarize agent panes (Ollama hermes3)   │
│  7. Write status.json + daily events         │
│  8. Prune old daily logs                     │
└──────────┬───────────────────────────────────┘
           │
           ▼
   ~/.local/share/driftdriver/tmux-monitor/
   ├── status.json          ← agents read this
   ├── panes/*.log          ← rolling pane output
   └── daily/*.jsonl        ← event timeline
```

## Install

```bash
pip install -e .
```

Requires: Python 3.11+, tmux, [Ollama](https://ollama.ai) with `hermes3:8b` loaded.

## Usage

```bash
# Start the daemon (runs forever)
tmux-monitor start

# Single heartbeat (debugging)
tmux-monitor heartbeat

# Which agents are working in my repo?
tmux-monitor status

# Specific repo
tmux-monitor status --repo driftdriver

# JSON for programmatic consumption
tmux-monitor status --json

# All agents including unrelated repos
tmux-monitor status --all

# List all sessions
tmux-monitor sessions

# View a pane's captured log
tmux-monitor logs "fresh_7.1"

# Web dashboard (Streamlit)
tmux-monitor web --port 8901

# Stop daemon
tmux-monitor stop
```

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

## How Detection Works

The daemon uses three signals to classify each pane:

1. **`pane_current_command`** (primary) — tmux reports the foreground process. `codex-aarch64-a` → codex, `opencode` → opencode, `2.1.129` → claude-code
2. **`pane_title`** — terminal title often contains agent branding. `✳ Claude Code` → claude-code, `OC | ...` → opencode
3. **Content patterns** (fallback) — regex on captured pane output for prompt markers

| Agent Type | `pane_current_command` | Title pattern |
|---|---|---|
| Claude Code | `2.1.128`, `2.1.129`, `claude` | `✳ Claude Code` |
| Codex | `codex-aarch64-a`, `codex` | — |
| OpenCode | `opencode` | `OC \| ...` |
| Kilocode | `kilocode` | — |
| pi.dev | `pi`, `pi.dev` | — |
| Shell | `zsh`, `bash` | — |
| Idle | *(none)* | — |

## How Summarization Works

For each agent-type pane with captured output, the daemon calls Ollama (`hermes3:8b` by default, already loaded in VRAM) every heartbeat cycle with:

- The last 15KB of pane output
- The previous summary (for continuity)
- A structured prompt requesting: paragraph summary, current_task, related_panes

The prompt explicitly asks the model to detect agent drift (task switching over time) and cross-session collaboration (agents working in the same repo or referencing each other).

Model is configurable in `config.json`. Any Ollama model works.

## Output

### `status.json` — the primary output

Written every heartbeat. Location: `~/.local/share/driftdriver/tmux-monitor/status.json`

```json
{
  "timestamp": "2026-05-14T14:30:00Z",
  "heartbeat_interval": 30.0,
  "sessions": {
    "fresh": {
      "windows": 7,
      "created_at": "2026-05-14T13:00:00Z",
      "panes": {
        "fresh:7.1": {
          "type": "opencode",
          "pane_id": "%298",
          "title": "OC | Tmux agent session monitor...",
          "current_command": "opencode",
          "pid": 48231,
          "cwd": "/Users/braydon/projects/experiments/driftdriver",
          "current_task": "building tmux monitor daemon",
          "summary": "Agent has been implementing the tmux monitor daemon, working on the core heartbeat loop and pipe-pane attachment...",
          "active_since": "2026-05-14T13:45:00Z",
          "llm_summary_at": "2026-05-14T14:25:00Z",
          "related_panes": []
        }
      }
    }
  }
}
```

### Relevance-filtered output

`tmux-monitor status --repo paia-program --json` returns only agents relevant to that repo:

```json
{
  "my_repo": "paia-program",
  "relevant_agents": [
    {
      "session": "paia",
      "pane": "paia:4.1",
      "pane_id": "%272",
      "type": "codex",
      "title": "paia-program",
      "current_task": "fixing OAuth flow",
      "summary": "Agent has been working on the OAuth authentication module...",
      "relevance": "same_repo",
      "controllable": true
    }
  ],
  "relevant_count": 1,
  "total_agents": 18
}
```

Relevance scoring:
- `same_repo` — agent's cwd matches the target repo name
- `related` — partial name match between cwd and target
- `unrelated` — excluded by default, shown with `--all`

### Controlling agents

Use the `pane_id` to send commands to another agent:

```bash
tmux send-keys -t %272 "your command" Enter
```

### Daily event log

Events are appended to `daily/YYYY-MM-DD.jsonl` and auto-pruned at midnight:

```jsonl
{"timestamp":"...","event_type":"session.appeared","session":"fresh","pane_id":""}
{"timestamp":"...","event_type":"agent.started","session":"fresh","pane_id":"fresh:7.1","agent_type":"opencode"}
{"timestamp":"...","event_type":"agent.summary","session":"fresh","pane_id":"fresh:7.1","summary":"...","current_task":"..."}
```

Event types: `session.appeared`, `session.disappeared`, `pane.created`, `pane.destroyed`, `agent.started`, `agent.stopped`, `agent.summary`, `agent.task_changed`

## State Directory

```
~/.local/share/driftdriver/tmux-monitor/
├── status.json              # Current snapshot (overwritten each heartbeat)
├── config.json              # Configuration (auto-generated)
├── known_sessions.json      # Previous cycle state for diffing
├── panes/                   # Per-pane pipe logs (trimmed to 512KB)
│   ├── fresh_7.1.log
│   └── paia_4.1.log
└── daily/                   # Daily event log (current day only)
    └── 2026-05-14.jsonl
```

## Configuration

`config.json` is auto-generated on first run. Edit or override:

| Setting | Default | Description |
|---|---|---|
| `heartbeat_day_seconds` | 30 | Heartbeat interval 4am–10pm |
| `heartbeat_night_seconds` | 3600 | Heartbeat interval 10pm–4am |
| `night_start_hour` | 22 | Night mode starts at 10pm |
| `night_end_hour` | 4 | Night mode ends at 4am |
| `llm_summary_interval_seconds` | 300 | How often to summarize (not yet interval-gated) |
| `max_pane_log_bytes` | 524288 | Max pane log before trim (512KB) |
| `state_dir` | `~/.local/share/driftdriver/tmux-monitor` | Where all state lives |

## Running as a Daemon (macOS)

A launchd plist keeps the daemon running across reboots and crashes:

```bash
# Load
launchctl load ~/Library/LaunchAgents/com.braydon.driftdriver-tmux-monitor.plist

# Check
launchctl list | grep tmux-monitor

# Stop
launchctl unload ~/Library/LaunchAgents/com.braydon.driftdriver-tmux-monitor.plist

# Logs
tail -f ~/.local/log/driftdriver-tmux-monitor.log
```

The plist uses `KeepAlive: true` and `RunAtLoad: true` — it restarts automatically on crash and starts at login.

## Agent Integration

### For coding CLI agents (Claude Code, Codex, OpenCode)

The skill `tmux-monitor` is registered in `~/.config/opencode/skills/` and `~/.claude/skills/`. Agents invoke:

```bash
tmux-monitor status --repo my-repo --json
```

Before starting work on a repo, agents check for existing workers. If `relevant_count > 0`, they read `current_task` to decide whether to coordinate or defer.

### For paia-agents

A tool class is registered in `paia-agent-runtime/tools/tmux_monitor.py` with three actions:

- **`status`** — relevance-filtered agent discovery
- **`sessions`** — list all tmux sessions
- **`send_keys`** — send commands to another agent's pane

### For anything else

Read `status.json` directly from `~/.local/share/driftdriver/tmux-monitor/status.json`. It's always current.

## Module Structure

```
src/tmux_monitor/
├── __init__.py
├── cli.py          # Standalone CLI entry point (tmux-monitor command)
├── config.py       # Configuration loading/saving, heartbeat schedule
├── daemon.py       # Core heartbeat loop, session lifecycle, SIGTERM handling
├── detection.py    # Agent classification (process + title + content heuristics)
├── discovery.py    # tmux session/pane enumeration, pipe-pane attach/detach
├── logs.py         # Log file trimming (head removal, keep tail)
├── relevance.py    # Repo relevance scoring, formatted output
├── state.py        # status.json writer, daily event log, session persistence
├── summarizer.py   # Ollama API calls for pane summarization
└── web.py          # Streamlit dashboard (single table view)
```

## License

MIT
