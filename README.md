# tmux-monitor

Heartbeat daemon that watches all tmux panes, detects coding agents (Claude Code, Codex, OpenCode, Kilocode, pi.dev), maintains rolling pane logs, generates Ollama-powered LLM summaries, and writes file-based state for agent coordination.

## Install

```bash
pip install -e .
```

## Usage

```bash
# Start the daemon (runs forever, managed by launchd)
tmux-monitor start

# Run a single heartbeat
tmux-monitor heartbeat

# Which agents are working in my repo?
tmux-monitor status

# Specific repo
tmux-monitor status --repo driftdriver

# JSON output
tmux-monitor status --json

# All agents
tmux-monitor status --all

# List sessions
tmux-monitor sessions

# View a pane's captured log
tmux-monitor logs "fresh_7.1"

# Web dashboard
tmux-monitor web --port 8901

# Stop daemon
tmux-monitor stop
```

## How It Works

1. **Discovery**: On each heartbeat, enumerates all tmux sessions and panes via `tmux list-sessions` / `list-panes`
2. **Capture**: Attaches `tmux pipe-pane` to each pane, streaming output to rolling log files (max 512KB)
3. **Detection**: Classifies each pane by `pane_current_command` and `pane_title` metadata (codex, opencode, claude-code, etc.)
4. **Summarization**: Periodic Ollama calls (default: hermes3:8b) generate paragraph summaries, extract current_task, and detect cross-session collaboration
5. **State**: Writes `status.json` with full session/pane/agent state, plus daily event logs (auto-pruned at midnight)

## Output

### status.json

```json
{
  "timestamp": "2026-05-14T14:30:00Z",
  "sessions": {
    "fresh": {
      "created_at": "2026-05-14T13:00:00Z",
      "panes": {
        "fresh:7.1": {
          "type": "opencode",
          "pane_id": "%298",
          "title": "OC | Tmux agent monitor...",
          "cwd": "/Users/braydon/projects/experiments/driftdriver",
          "current_task": "building tmux monitor",
          "summary": "Agent has been implementing the tmux monitor daemon...",
          "active_since": "2026-05-14T13:45:00Z"
        }
      }
    }
  }
}
```

### Relevance-aware CLI

`tmux-monitor status --repo paia-program --json` returns:

```json
{
  "my_repo": "paia-program",
  "relevant_agents": [
    {
      "session": "paia",
      "pane": "paia:4.1",
      "pane_id": "%272",
      "type": "codex",
      "current_task": "fixing OAuth flow",
      "relevance": "same_repo",
      "controllable": true
    }
  ],
  "relevant_count": 1,
  "total_agents": 18
}
```

Use `pane_id` to control another agent: `tmux send-keys -t %272 "command" Enter`

## Configuration

Config stored at `~/.local/share/driftdriver/tmux-monitor/config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `heartbeat_day_seconds` | 30 | Heartbeat interval 4am–10pm |
| `heartbeat_night_seconds` | 3600 | Heartbeat interval 10pm–4am |
| `llm_summary_interval_seconds` | 300 | Ollama summarization interval |
| `max_pane_log_bytes` | 524288 | Max pane log size (512KB) |
| `state_dir` | `~/.local/share/driftdriver/tmux-monitor` | State directory |

## State Directory

```
~/.local/share/driftdriver/tmux-monitor/
├── status.json          # Current snapshot
├── config.json          # Configuration
├── known_sessions.json  # Previous cycle state (internal)
├── panes/               # Per-pane pipe logs
│   ├── fresh_7.1.log
│   └── paia_4.1.log
└── daily/               # Daily event log (pruned daily)
    └── 2026-05-14.jsonl
```

## Launchd

```bash
# Install (plist already at ~/Library/LaunchAgents/)
launchctl load ~/Library/LaunchAgents/com.braydon.driftdriver-tmux-monitor.plist

# Check status
launchctl list | grep tmux-monitor

# Stop
launchctl unload ~/Library/LaunchAgents/com.braydon.driftdriver-tmux-monitor.plist
```

## License

MIT
