# pif / pim TUI Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `pif` as a desktop Pi cockpit profile and keep `pim` as a pure mobile Pi profile with shared sessions/settings.

**Architecture:** Use shell functions as profile entrypoints. Keep global Pi settings unchanged, and layer desktop-only resources onto `pif` with a custom theme file and a single dashboard extension loaded via CLI flags.

**Tech Stack:** zsh shell functions, Pi TypeScript extension API, Pi JSON themes, Node-based validation scripts.

---

## File Structure

- Create: `~/.pi/agent/themes/pif-espresso.json`
  - Complete warm dark Pi theme with all required color tokens.
- Create: `~/.pi/agent/extensions/pif-dashboard.ts`
  - Desktop-only Pi extension with compact footer/status and command.
- Modify: `~/.zshrc`
  - Replace `alias pim='pi --mobile'` with `pif()` and `pim()` shell functions.
- Create: `docs/superpowers/plans/2026-06-06-pif-pim-tui-profiles.md`
  - This plan.

## Task 1: Validation Harness

**Files:**
- Create: `/tmp/validate-pif-pim.mjs`

- [ ] **Step 1: Write failing validation script**

Create `/tmp/validate-pif-pim.mjs`:

```js
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const home = os.homedir();
const themePath = path.join(home, '.pi/agent/themes/pif-espresso.json');
const extensionPath = path.join(home, '.pi/agent/extensions/pif-dashboard.ts');
const zshrcPath = path.join(home, '.zshrc');

const requiredColors = [
  'accent','border','borderAccent','borderMuted','success','error','warning','muted','dim','text','thinkingText',
  'selectedBg','userMessageBg','userMessageText','customMessageBg','customMessageText','customMessageLabel','toolPendingBg','toolSuccessBg','toolErrorBg','toolTitle','toolOutput',
  'mdHeading','mdLink','mdLinkUrl','mdCode','mdCodeBlock','mdCodeBlockBorder','mdQuote','mdQuoteBorder','mdHr','mdListBullet',
  'toolDiffAdded','toolDiffRemoved','toolDiffContext',
  'syntaxComment','syntaxKeyword','syntaxFunction','syntaxVariable','syntaxString','syntaxNumber','syntaxType','syntaxOperator','syntaxPunctuation',
  'thinkingOff','thinkingMinimal','thinkingLow','thinkingMedium','thinkingHigh','thinkingXhigh','bashMode'
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(fs.existsSync(themePath), `Missing theme: ${themePath}`);
const theme = JSON.parse(fs.readFileSync(themePath, 'utf8'));
assert(theme.name === 'pif-espresso', 'Theme name must be pif-espresso');
assert(theme.colors && typeof theme.colors === 'object', 'Theme colors object missing');
for (const key of requiredColors) {
  assert(Object.prototype.hasOwnProperty.call(theme.colors, key), `Missing theme color: ${key}`);
}

assert(fs.existsSync(extensionPath), `Missing extension: ${extensionPath}`);
const extension = fs.readFileSync(extensionPath, 'utf8');
assert(extension.includes('setFooter'), 'Extension must set custom footer');
assert(extension.includes('setStatus'), 'Extension must set status indicators');
assert(extension.includes('registerCommand("pif-status"'), 'Extension must register /pif-status');
assert(extension.includes('default function'), 'Extension must export default function');

const zshrc = fs.readFileSync(zshrcPath, 'utf8');
assert(!zshrc.includes("alias pim='pi --mobile'"), 'Old pim alias must be removed');
assert(zshrc.includes('pif() {'), 'Missing pif shell function');
assert(zshrc.includes('--theme ~/.pi/agent/themes/pif-espresso.json'), 'pif must load desktop theme');
assert(zshrc.includes('--extension ~/.pi/agent/extensions/pif-dashboard.ts'), 'pif must load desktop extension');
assert(zshrc.includes('pim() {'), 'Missing pim shell function');
assert(zshrc.includes('pi --mobile "$@"'), 'pim must remain pure mobile');

console.log('pif/pim validation passed');
```

- [ ] **Step 2: Run script to verify RED**

Run:

```bash
node /tmp/validate-pif-pim.mjs
```

Expected: FAIL because `pif-espresso.json` and/or `pif-dashboard.ts` do not exist yet and `~/.zshrc` still has the old `pim` alias.

## Task 2: Theme

**Files:**
- Create: `~/.pi/agent/themes/pif-espresso.json`

- [ ] **Step 1: Create theme directory**

Run:

```bash
mkdir -p ~/.pi/agent/themes
```

- [ ] **Step 2: Write complete theme JSON**

Write a complete theme named `pif-espresso` with all required Pi color tokens, using espresso/brown base colors and orange/gold accents.

- [ ] **Step 3: Validate JSON syntax**

Run:

```bash
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.pi/agent/themes/pif-espresso.json","utf8")); console.log("theme json ok")'
```

Expected: `theme json ok`.

## Task 3: Dashboard Extension

**Files:**
- Create: `~/.pi/agent/extensions/pif-dashboard.ts`

- [ ] **Step 1: Create extension directory**

Run:

```bash
mkdir -p ~/.pi/agent/extensions
```

- [ ] **Step 2: Write extension**

Create a TypeScript Pi extension that:

- exports `default function pifDashboard(pi: ExtensionAPI)`
- on `session_start`, sets footer/status/title when UI is available
- tracks turn count/activity via `turn_start`, `turn_end`, and `agent_end`
- registers `/pif-status`
- does not change sessions, model, thinking level, tools, or global settings

- [ ] **Step 3: Static content validation**

Run:

```bash
grep -E 'setFooter|setStatus|registerCommand\("pif-status"|default function' ~/.pi/agent/extensions/pif-dashboard.ts
```

Expected: all four patterns are present.

## Task 4: Shell Functions

**Files:**
- Modify: `~/.zshrc`

- [ ] **Step 1: Replace old alias with functions**

Replace:

```sh
alias pim='pi --mobile'
```

with:

```sh
pif() {
  pi \
    --theme ~/.pi/agent/themes/pif-espresso.json \
    --extension ~/.pi/agent/extensions/pif-dashboard.ts \
    "$@"
}

pim() {
  pi --mobile "$@"
}
```

- [ ] **Step 2: Check zsh syntax**

Run:

```bash
zsh -n ~/.zshrc
```

Expected: exit 0 and no output.

## Task 5: Full Validation

**Files:**
- Read/validate: `/tmp/validate-pif-pim.mjs`, `~/.zshrc`, theme, extension

- [ ] **Step 1: Run validation script to verify GREEN**

Run:

```bash
node /tmp/validate-pif-pim.mjs
```

Expected: `pif/pim validation passed`.

- [ ] **Step 2: Verify shell functions resolve**

Run:

```bash
zsh -ic 'type pif; type pim'
```

Expected: both are shell functions, `pif` references `pif-espresso.json` and `pif-dashboard.ts`, `pim` runs `pi --mobile "$@"`.

- [ ] **Step 3: Verify Pi accepts both command paths without starting a paid/model turn**

Run:

```bash
zsh -ic 'pif --help >/tmp/pif-help.txt 2>&1 && pim --help >/tmp/pim-help.txt 2>&1 && grep -q -- "--mobile" /tmp/pim-help.txt && echo cli-help-ok'
```

Expected: `cli-help-ok`.

- [ ] **Step 4: Commit repo plan document only**

Run:

```bash
git add docs/superpowers/plans/2026-06-06-pif-pim-tui-profiles.md
git commit -m "Add pif pim TUI implementation plan"
```

Expected: one commit containing the plan file. Do not add home-directory config files to this repo.

## Self-Review

- Spec coverage: the plan covers shared sessions, high thinking, scoped models unchanged, images unchanged, pure `pim`, desktop `pif`, warm theme, dashboard extension, shell functions, and validation.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: extension uses documented Pi APIs: `ExtensionAPI`, `ctx.ui.setFooter`, `ctx.ui.setStatus`, `pi.registerCommand`, and session/turn events.
