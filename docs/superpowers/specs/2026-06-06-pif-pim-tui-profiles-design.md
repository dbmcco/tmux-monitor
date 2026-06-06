# pif / pim TUI Profiles Design

Date: 2026-06-06

## Goal

Create two Pi launcher profiles that match how Braydon uses Pi across desktop and mobile:

- `pif`: a rich desktop/full-screen dashboard profile for focused work.
- `pim`: an ultra-minimal mobile profile for small screens.

Both profiles must share the same underlying Pi defaults, sessions, model choices, thinking level, and image behavior so desktop and mobile can be used together seamlessly.

## Current Context

Existing global Pi settings in `~/.pi/agent/settings.json` already define:

- default provider/model
- `defaultThinkingLevel: "high"`
- quiet startup
- existing scoped/enabled model list
- installed Pi packages/extensions

## Requirements

1. Preserve shared sessions between desktop and mobile.
2. Keep thinking level high everywhere.
3. Keep existing scoped model list unchanged.
4. Keep images enabled.
5. Keep global Pi configuration mostly unchanged.
6. Replace the existing `pim` alias with shell functions so arguments pass through cleanly.
7. Make `pim` mobile-first with reduced visual chrome while preserving capabilities.
8. Make `pif` desktop-only and richer by loading a desktop theme and dashboard extension.
9. Use a warm dark visual family: espresso/brown base with orange/gold accents.
10. Avoid cluttering the main chat; dashboard additions should be compact and useful.

## Non-Goals

- No separate session directories.
- No separate Pi config directories.
- No changes to scoped models.
- No lowering thinking level for mobile.
- No disabling images for mobile.
- No persistent mobile dashboard widgets.
- No mobile capability reduction; minimal means less chrome, not fewer tools/models/extensions.

## Profile Design

### `pim`: Mobile Profile

`pim` remains the clean small-screen launcher and adds only a visual-minimizer extension:

```sh
pim() {
  pi \
    --mobile \
    --extension ~/.pi/agent/extensions/pim-minimal.ts \
    "$@"
}
```

It intentionally does not change tools, models, thinking level, images, or session storage. It inherits global Pi defaults and uses `pim-minimal.ts` only to reduce TUI chrome.

### `pif`: Desktop Profile

`pif` is the desktop cockpit launcher:

```sh
pif() {
  pi \
    --theme ~/.pi/agent/themes/pif-espresso.json \
    --extension ~/.pi/agent/extensions/pif-dashboard.ts \
    "$@"
}
```

It uses the same global Pi defaults but layers on desktop-only UI resources.

## Desktop Dashboard Extension

Create `~/.pi/agent/extensions/pif-dashboard.ts`.

The extension should:

- run only when loaded by `pif`
- set a compact custom footer with useful desktop context
- provide status/progress indicators for turns
- keep widgets minimal and below/near the editor only when useful
- expose a small command such as `/pif-dashboard` or `/pif-status` if interactive inspection is useful
- avoid changing model, thinking, sessions, tools, or global behavior

Recommended initial dashboard content:

- active model
- current git branch when available
- current working directory basename
- turn/activity status
- token/cost summary if available from session usage

## Theme Design

Create `~/.pi/agent/themes/pif-espresso.json`.

Style:

- dark espresso / brown base
- orange/gold accent
- readable amber highlights
- green success and clear red error states
- strong enough contrast for desktop work

A calmer mobile sibling theme (`pim-espresso`) can be added later, but `pim` should not use a custom theme by default unless Braydon asks for it.

## Implementation Plan Summary

1. Create `pif-espresso.json` theme.
2. Create `pif-dashboard.ts` extension.
3. Create `pim-minimal.ts` visual-minimizer extension.
4. Update `~/.zshrc`:
   - remove `alias pim='pi --mobile'`
   - add `pif()` shell function
   - add `pim()` shell function
5. Validate:
   - `pif --help` starts Pi help path with the desktop resources accepted
   - `pim --help` confirms mobile flag path still works
   - extension TypeScript imports resolve under Pi
   - JSON theme is valid and contains all required color tokens

## Risks and Mitigations

- **Extension clutter:** Keep default dashboard compact and avoid persistent large widgets.
- **Global config drift:** Use CLI-loaded resources from shell functions instead of changing global settings.
- **Mobile/desktop divergence:** Keep sessions and core settings shared.
- **Theme validity:** Ensure all required Pi theme color tokens are present.

## Open Decisions

None. The user approved the recommended approach: shared config, less-chrome mobile `pim`, desktop dashboard `pif`, shell functions, warm dark theme family.
