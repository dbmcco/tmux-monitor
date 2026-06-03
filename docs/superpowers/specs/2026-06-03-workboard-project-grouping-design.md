# Workboard Project Grouping — Design Spec

**Date:** 2026-06-03
**Status:** Approved
**Repos affected:** `experiments/paia-work`, `experiments/paia-os`

---

## Problem

Work on the PAIA workboard exists only as individual tasks. There is no human-facing way to view or manage tasks grouped by project/initiative. The `Initiative` model and storage exist in `paia-work` but have no web surface. Agents (Sam, Caroline, Derek, Helena) and Braydon need a project-level view to understand what a collection of tasks is working toward and how it's progressing.

---

## Goal

Add a Projects view to the workboard that shows initiatives as project containers — with goal, milestones, task progress, and assigned agent — accessible from the existing workboard nav.

---

## Audience

Braydon and his PAIA agents. Not external stakeholders.

---

## Architecture

Two repos, three layers:

```
paia-os/web (port 3601)          paia-work (port 3560)
─────────────────────────        ──────────────────────
workboard-projects-surface   →   GET /v1/initiatives?include_progress=true
useInitiatives() hook        →   GET /v1/initiatives/{id}/summary
(new milestone actions)      →   POST /v1/initiatives/{id}/milestones
                             →   PATCH /v1/initiatives/{id}/milestones/{mid}
```

---

## Section 1: Data Model (paia-work)

### `initiative.py` additions

**`Milestone` model** (new):
```python
class Milestone(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    due_date: str | None = None
    completed: bool = False
    completed_at: str | None = None
    created_at: str = Field(default_factory=_now_iso)
```

**`Initiative` model additions:**
- `goal: str | None = None` — what done looks like for this project
- `milestones: list[Milestone] = Field(default_factory=list)`

**`InitiativeProgress` response model** (computed, not stored):
```python
class InitiativeProgress(BaseModel):
    total: int
    open: int
    in_progress: int
    done: int
    percent_complete: float  # done / total * 100, 0 if total == 0
```

Progress is computed at read time by joining `initiative.tasks` task IDs against the workgraph task store.

### `InitiativeStore` additions
- `add_milestone(initiative_id, milestone)` — appends milestone to initiative
- `complete_milestone(initiative_id, milestone_id)` — marks milestone completed
- `update_milestone(initiative_id, milestone_id, **kwargs)` — update due_date or title

---

## Section 2: API Surface (paia-work)

### Existing routes (unchanged)
- `POST /v1/initiatives` — create initiative (add `goal` and `milestones` to request model)
- `GET /v1/initiatives` — list initiatives (add `?include_progress=true` param)
- `GET /v1/initiatives/{id}` — get single initiative

### New routes
- `GET /v1/initiatives/{id}/summary` — initiative + computed `progress` block + full milestone list
- `POST /v1/initiatives/{id}/milestones` — add milestone (`title`, `due_date?`)
- `PATCH /v1/initiatives/{id}/milestones/{milestone_id}` — update milestone (`title?`, `due_date?`, `completed?`)

### `?include_progress=true` behavior
When present on `GET /v1/initiatives`, each initiative in the list response includes an injected `progress` object. Omitted by default to avoid N+1 cost when not needed.

---

## Section 3: UX (paia-os/web)

### New files
- `src/components/surfaces/workboard-projects-surface.tsx` — main surface component
- `src/hooks/use-initiatives.ts` — data fetching hook, hits paia-work at port 3560

### `useInitiatives()` hook
Follows `usePortfolioNodes()` pattern. Fetches from paia-work (separate client from paia-os backend). Returns `{ data: Initiative[], loading, error }`. Polls on a 30s interval via `useApiQuery` — same pattern as existing workboard data hooks.

### `WorkboardProjectsSurface` layout

Split-panel layout matching `portfolio-surface.tsx`:

**Left panel (project list, `w-80`):**
- Header: "Projects" + count
- Grouped by status: active → waiting/paused → complete (collapsed by default)
- Per project card:
  - Title + status badge
  - Goal snippet (1 line, truncated)
  - Progress bar: `X/Y tasks` with filled bar
  - Assigned agent badge (if set)

**Right panel (project detail):**
- Header: title, status badge, phase badge, assigned agent
- Goal section: full text
- Progress bar: prominent, with open/in-progress/done breakdown
- Milestones section: checklist — title, due date, check-to-complete button
- Tasks section: grouped by status (open / in-progress / done), each row shows task title + state badge. Clicking a task sets it as the selected page in the workboard page stack surface (via shared state or navigation to `/workboard` with the task ID).
- Timestamps footer

**Empty state:** "No projects yet. Create one via the API or CLI."

### Workboard nav integration

`workboard-page-stack-surface.tsx` has an existing lane/view switcher. Add a "Projects" tab that swaps the main content area to `WorkboardProjectsSurface`. No new route — stays at `/workboard`.

### Milestone interactions

- Check a milestone → `PATCH /v1/initiatives/{id}/milestones/{mid}` with `{ completed: true }`
- Optimistic update in UI, revert on error

---

## Section 4: CLI (paia-work)

New `workboard projects` subcommand group:

```bash
uv run workboard projects list                          # list active projects
uv run workboard projects show <id>                     # detail + task counts
uv run workboard projects add "Title" --goal "..."      # create project
uv run workboard projects milestone <id> "Title" --due 2026-07-01
uv run workboard projects milestone-done <id> <mid>     # complete milestone
uv run workboard projects done <id>                     # complete project
```

---

## What This Is Not

- Not a replacement for the workboard page stack — tasks still live there
- Not a roadmap or Gantt view — no timeline visualization in this iteration
- Not multi-user / stakeholder-facing — internal tool only
- Not a rebuild of `PortfolioSurface` — that remains a separate higher-level concept (OKR/entity graph)

---

## Testing

- `paia-work`: unit tests for `Milestone` model, `add_milestone` / `complete_milestone` store ops, `include_progress` list param, `/summary` endpoint
- `paia-os/web`: `useInitiatives` hook mock tests, `WorkboardProjectsSurface` render tests (empty state, list, detail panel)
- Coverage target: >90% for new `paia-work` code, >70% for new UI components

---

## Open Questions / Future Work

- **Milestone due date notifications** — agents could watch `not_before` dates; deferred
- **Create project from UI** — form in the detail panel; deferred to follow-up
- **Task → project assignment from workboard** — tag a task with a project inline; deferred
- **Agent heartbeat on project detail** — show live agent session status; blocked on heartbeat registry
