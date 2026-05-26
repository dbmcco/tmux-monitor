# PAIA Desk Display Design

Date: 2026-05-26
Status: Approved design for user review

## Purpose

`paia-desk-display` is a separate local web service for using a Boox Note Air 4C as a glanceable desk display. It shows Braydon's workboard, schedule, and tmux agent state in an e-ink-friendly command center, with minimal immediate actions such as closing tasks or opening more detail.

This is not an extension of `eink-sync`. The notebook sync service remains focused on Supernote/Boox notebook synchronization. `paia-desk-display` treats the Boox as one display client over a normal browser.

## Goals

- Provide a Boox-friendly command center that can sit on the desk all day.
- Default to a workboard-dominant layout while keeping schedule and tmux monitor visible.
- Support alternate layouts: balanced grid and now-plus-feed.
- Support individual full-screen views for Workboard, Schedule, and tmux Monitor.
- Dynamically update without manual refresh.
- Route low-risk touch actions immediately to canonical systems.
- Preserve last good display state when one upstream source is stale or unavailable.

## Non-Goals

- Android/Kotlin app packaging in v1.
- Notebook synchronization or Supernote export behavior.
- Rich task editing, rescheduling, or tmux pane control in v1.
- Animated dashboard behavior or frequent visual churn that fights e-ink readability.
- New canonical task, calendar, or tmux state storage.

## Product Shape

The Boox opens a full-screen web dashboard served by `paia-desk-display`.

The default home screen is **Workboard Dominant Command Center**:

- Large Workboard panel with active priorities, blocked items, closing candidates, and tasks needing attention.
- Smaller Schedule panel with the current/next meeting and the day's timeline.
- Smaller tmux Monitor panel with active agents, idle/blocked agents, and agent sessions needing user input.

Two alternate command-center modes are available:

- **Balanced Grid**: equal panels for Now, Schedule, Workboard, and tmux Monitor.
- **Now + Feed**: a top strip for current task, next meeting, and alerts, with a unified attention feed below.

Each source also has an individual full-screen view:

- Workboard detail view
- Schedule detail view
- tmux Monitor detail view

## Architecture

`paia-desk-display` is a separate FastAPI service with a small web frontend.

Core units:

- **Source adapters** normalize upstream data into display panel models.
- **Snapshot store** keeps the latest known-good dashboard state in memory and optionally on disk.
- **Layout engine** composes command-center and full-screen view models from source panels.
- **Action router** validates Boox touch actions and forwards them to canonical systems.
- **WebSocket broadcaster** sends coarse update events to connected display clients.
- **Frontend client** renders e-ink-friendly HTML/CSS and applies update snapshots deliberately.

The first frontend should be intentionally simple: server-rendered shell plus lightweight JavaScript for WebSocket updates and touch actions is enough. A larger frontend framework is not required unless later interaction complexity justifies it.

## Data Sources

### Workboard

Canonical source: `paia-work`.

Initial integration:

- Read tasks through the `paia-work` HTTP API.
- Subscribe to `paia-work` `/ws/events` for task-created and task-updated events.
- Use `POST /api/tasks/{id}/done` for close-task actions.
- Use task detail endpoints when opening a task detail panel.

`paia-desk-display` does not copy task state into a new model. It presents selected fields and sends mutations back to `paia-work`.

### Schedule

Canonical source: Google Calendar or the existing local agenda/calendar service selected during implementation.

Initial integration:

- Poll a cached agenda endpoint or adapter on a conservative interval.
- Normalize today, current event, next event, and relevant prep/follow-up context.
- Store the latest good schedule snapshot with a visible stale indicator if refresh fails.

The schedule panel is read-only in v1.

### tmux Monitor

Canonical source: `tmux-monitor`.

Initial integration:

- Read `~/.local/share/driftdriver/tmux-monitor/status.json` directly or through `tmux-monitor status --json`.
- Poll or file-watch the status source.
- Normalize agents into counts, attention states, current tasks, summaries, and detail rows.

tmux pane control is out of scope for v1. The display may show pane IDs and status, but it should not kill panes, send keys, or start agents.

## Update Model

The Boox client connects to one WebSocket served by `paia-desk-display`.

Upstream updates:

- `paia-work`: WebSocket subscription.
- Schedule: timed refresh with cache.
- `tmux-monitor`: file polling or file watch.

Downstream updates:

- Send a full compact snapshot on connect.
- Send panel-level replacement snapshots when a source changes.
- Avoid high-frequency updates. Coalesce bursts and prefer deliberate refreshes over animation.
- Include `generated_at`, `source_updated_at`, and `stale_since` metadata per panel.

If WebSocket disconnects, the browser keeps the last rendered state and periodically attempts reconnect. A manual refresh button is available.

## Actions

V1 touch actions are immediate:

- Close a workboard task.
- Open item detail.
- Switch command-center layout.
- Switch to a full-screen source view.
- Return home.
- Manual refresh.
- Acknowledge or hide non-destructive display alerts.

Action rules:

- Actions route to the canonical owner, not to display-local state.
- Workboard completion uses `paia-work`.
- Read-only panels should reject mutation actions explicitly.
- Failed actions show a concise error and leave the previous state visible.
- Riskier actions, including rescheduling, task reprioritization, tmux pane control, and destructive cleanup, remain out of v1.

## E-Ink UI Requirements

- High contrast, mostly monochrome, with sparse accent use that degrades cleanly on e-ink.
- Large touch targets.
- No continuous animation.
- Stable panel dimensions to avoid layout shift during updates.
- Text-first density for glanceability.
- Explicit stale/unavailable labels per panel.
- Manual refresh and reconnect affordances.
- Layout choice persisted per client.

## Error Handling

The dashboard should degrade per source, not globally.

- If `paia-work` is unavailable, keep the last workboard snapshot and mark it stale.
- If schedule refresh fails, keep the last schedule snapshot and mark it stale.
- If `tmux-monitor` status is missing or old, show the last known agent summary and age.
- If a touch action fails, show an inline action error and refetch that panel.
- If all sources are unavailable, show the last full snapshot plus source health.

## Testing

Testing should focus on source normalization, action routing, and update behavior.

Initial tests:

- Unit tests for Workboard, Schedule, and tmux source adapters using fixtures.
- Unit tests for layout composition across the three command-center modes.
- Unit tests for action routing, including close-task success and failure.
- WebSocket tests for initial snapshot and panel update broadcast.
- Browser smoke test for Boox-sized viewport with no text overlap and stable layout.

Manual validation:

- Open dashboard on desktop browser.
- Open dashboard on Boox browser.
- Confirm WebSocket reconnect behavior.
- Confirm closing a task updates `paia-work` and the displayed panel.
- Confirm stale-source states are visible and non-blocking.

## Open Implementation Decisions

- Final repository name: `paia-desk-display` unless Braydon prefers another name.
- Calendar adapter source: direct Google Calendar profile, `paia-meetings`, Folio agenda, or another existing agenda facade.
- Frontend stack: server-rendered templates plus lightweight JavaScript by default, unless implementation context favors an existing framework.
- Whether to persist layout preferences server-side or only in browser local storage.
