# Flow files — driving and asserting the interaction

A flow file is a JSON array of steps executed in order at every viewport. Each step is
screenshotted; a failure captures a `-FAILED.png` at the exact moment of failure and stops
the flow (unless `continue_on_failure` is set), so the screenshot always shows the broken
state rather than whatever came after.

Pass it with `--flow path/to/flow.json`.

## Action reference

| Action | Fields | Notes |
| --- | --- | --- |
| `goto` | `value` (URL) | Navigate mid-flow; waits for network idle |
| `click` | `selector` | |
| `fill` | `selector`, `value` | Clears the field first |
| `press` | `value` (key), `selector` optional | `Enter`, `Tab`, `Escape`, `Control+A` |
| `hover` | `selector` | For tooltips, dropdowns, hover-only affordances |
| `select` | `selector`, `value` | `<select>` option value |
| `wait` | `value` (ms) | Last resort — prefer `wait_for` |
| `wait_for` | `selector` | Waits for the element to attach |
| `assert_visible` | `selector` | Visible, not merely present in the DOM |
| `assert_hidden` | `selector` | Gone or hidden — proves close/dismiss actually works |
| `assert_text` | `selector`, `value` | Substring match on `innerText` |
| `assert_url` | `value` | Substring match on the current URL |
| `eval` | `value` (JS expression) | Escape hatch; result is stored in the report |
| `screenshot` | — | Explicit capture point |

Every step also accepts:

- `name` — a human label; it becomes the screenshot filename and the failure message, so
  write it as the claim being tested ("count increments"), not the mechanics ("click div").
- `timeout` — per-step timeout in ms (default 10000).
- `screenshot: false` — skip the capture for a noisy intermediate step.
- `full_page: true` — full-page capture for this step.
- `continue_on_failure: true` — keep going after this step fails; use when later steps are
  independent and you want the full picture in one run.

## Selector strategy

Ranked by resilience:

1. `[data-testid=submit]` — survives redesigns; add one if it is missing.
2. `role=button[name="Save changes"]` — asserts the accessible name at the same time, so a
   passing selector is also partial a11y evidence.
3. `text=Save changes` — readable, but breaks on copy changes and i18n.
4. `#id` — fine when the id is stable and not framework-generated.
5. `.some-class` — avoid. Class names change every time someone touches the styles, and a
   Tailwind class selector is essentially a coin flip.

## Recipes

### Login before verifying

Prefer `--storage-state` for repeated runs. Use this when you need to verify the login path
itself, and keep credentials in env vars rather than the file.

```json
[
  {"action": "fill",  "selector": "[name=email]",    "value": "test@example.com", "name": "enter email"},
  {"action": "fill",  "selector": "[name=password]", "value": "password",         "name": "enter password", "screenshot": false},
  {"action": "click", "selector": "button[type=submit]", "name": "submit login"},
  {"action": "assert_url", "value": "/dashboard", "name": "lands on dashboard"},
  {"action": "assert_visible", "selector": "[data-testid=user-menu]", "name": "session is live"}
]
```

### Modal opens and closes

Closing matters as much as opening — a modal that traps the user is a worse bug than one
that will not open.

```json
[
  {"action": "click", "selector": "[data-testid=open-settings]", "name": "open modal"},
  {"action": "assert_visible", "selector": "[role=dialog]", "name": "dialog appears"},
  {"action": "press", "value": "Escape", "name": "press escape"},
  {"action": "assert_hidden", "selector": "[role=dialog]", "name": "dialog dismisses"}
]
```

### Form validation

Assert the error appears *and* that a valid submission clears it. Half a flow proves half a
feature.

```json
[
  {"action": "click", "selector": "button[type=submit]", "name": "submit empty form"},
  {"action": "assert_text", "selector": "[data-testid=email-error]", "value": "required", "name": "shows required error"},
  {"action": "fill", "selector": "[name=email]", "value": "not-an-email", "name": "enter invalid email"},
  {"action": "click", "selector": "button[type=submit]", "name": "submit invalid"},
  {"action": "assert_text", "selector": "[data-testid=email-error]", "value": "valid email", "name": "shows format error"},
  {"action": "fill", "selector": "[name=email]", "value": "ok@example.com", "name": "enter valid email"},
  {"action": "click", "selector": "button[type=submit]", "name": "submit valid"},
  {"action": "assert_hidden", "selector": "[data-testid=email-error]", "name": "error clears"}
]
```

### Theme toggle

```json
[
  {"action": "click", "selector": "[data-testid=theme-toggle]", "name": "switch to dark"},
  {"action": "eval", "value": "document.documentElement.className", "name": "read theme class"},
  {"action": "screenshot", "name": "dark mode", "full_page": true},
  {"action": "click", "selector": "[data-testid=theme-toggle]", "name": "switch back to light"}
]
```

Read the `eval` result in `report.json` to confirm the class actually flipped — the
screenshot proves the paint, the eval proves the state.

### Async data and loading states

```json
[
  {"action": "click", "selector": "[data-testid=load-more]", "name": "load more"},
  {"action": "assert_visible", "selector": "[data-testid=spinner]", "name": "spinner shows", "timeout": 2000},
  {"action": "assert_hidden",  "selector": "[data-testid=spinner]", "name": "spinner clears", "timeout": 15000},
  {"action": "eval", "value": "document.querySelectorAll('[data-testid=row]').length", "name": "row count after load"}
]
```

### Double-submit guard

The single most common bug that ships past a happy-path check.

```json
[
  {"action": "click", "selector": "button[type=submit]", "name": "first click", "screenshot": false},
  {"action": "click", "selector": "button[type=submit]", "name": "second click (should be a no-op)", "continue_on_failure": true},
  {"action": "eval", "value": "document.querySelectorAll('[data-testid=toast]').length", "name": "toast count — expect 1"}
]
```

### Keyboard-only path

```json
[
  {"action": "press", "value": "Tab", "name": "tab to first control"},
  {"action": "press", "value": "Tab", "name": "tab to the new button"},
  {"action": "eval", "value": "document.activeElement.outerHTML.slice(0,120)", "name": "focus landed where expected"},
  {"action": "press", "value": "Enter", "name": "activate with keyboard"},
  {"action": "assert_visible", "selector": "[data-testid=result]", "name": "keyboard activation works"}
]
```

## Writing good flows

- **One claim per step name.** The report reads as a list of proven claims; vague names make
  it worthless to anyone reviewing it later.
- **Assert the change, not the click.** `click` succeeding only means an element accepted a
  click. The following `assert_*` is what proves the feature.
- **Cover the reverse.** Open/close, add/remove, enable/disable — state that only moves one
  way is a common regression.
- **Keep flows under ~15 steps.** Split by feature; three focused flows diagnose faster than
  one long one, and a failure at step 3 does not blind you to steps 8–15.
- **Do not encode secrets.** Use `--storage-state`, `--header`, or env-var-injected test
  credentials.
