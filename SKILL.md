---
name: frontend-verification-gate
description: Verify a frontend or UI change end-to-end in a real browser before reporting it as done — run the app, interact with the change, check the console and network, sweep desktop/tablet/mobile, scan accessibility, and measure Core Web Vitals. Use this skill whenever you finish editing any UI code (React/Vue/Svelte component, Next.js page, Blade or Twig template, CSS/Tailwind, WordPress theme file), whenever the user says "is it done", "ship it", "verify this", "check it works", "did that fix it", or asks for a QA pass on a page, and before writing any summary that claims a visual or interactive change works. Use it even when the edit looks trivial — a clean diff is not evidence that the UI works.
license: MIT
---

# Frontend Verification Gate

A code edit that applies cleanly tells you the file changed. It tells you nothing about
whether the button renders, the click handler fires, the layout survives a 390px viewport,
or the page still hydrates without throwing. Those are separate claims, and each one needs
its own evidence.

This skill is the gate between "I made the change" and "the change works." Run it before
you report a UI change as complete.

## The contract

Do not describe a UI change as done, working, fixed, or verified unless every applicable
line below is backed by evidence you actually collected in this session:

1. **It runs.** The app builds and the affected route loads without a navigation error.
2. **It renders.** You have a screenshot of the changed UI in its real surroundings.
3. **It behaves.** You drove the interaction (click, type, submit, toggle) and observed the
   expected state change — not just the element's presence in the DOM.
4. **It is clean.** No new console errors, no new uncaught exceptions, no new failed
   requests or 4xx/5xx responses attributable to the change.
5. **It holds up responsively.** Verified at the viewports that apply to this surface.
6. **It is reachable.** Keyboard-operable, labelled, and contrast-passing for anything
   interactive you added or restyled.
7. **It did not get slower.** Core Web Vitals measured, or explicitly declared out of scope
   with a reason.

Anything you could not check is not a silent omission — it is a line in your report under
**Not verified**, with the reason. Understating coverage is recoverable; overstating it is
what erodes trust in every future report.

## Workflow

### Step 0 — Scope the blast radius

Before touching a browser, write down the answer to three questions. This takes thirty
seconds and prevents the most common failure mode: verifying the one page you edited while
a shared component quietly breaks four others.

- **Which routes render this change?** Grep for imports/usages of the edited component,
  template, or class. A change to a shared `Button`, layout, or global stylesheet has a
  blast radius far beyond the file you touched.
- **What is the user-visible claim?** State it as a testable sentence: "clicking Like
  increments the count and flips the label to Liked." That sentence becomes your flow steps.
- **Which viewports and states matter?** Logged in vs. out, empty vs. populated, light vs.
  dark, RTL if the product ships it.

Verify the primary route in full. Smoke-check each secondary route in the blast radius —
load it, screenshot it, confirm a clean console.

### Step 1 — Get a real running app

Verification against a build that never ran is not verification. Start the dev server (or
serve a production build — see below) and confirm the URL responds before going further.

Read `references/stack-playbooks.md` for the exact commands, default ports, expected
startup noise, and gotchas for Next.js, Vite/React, Laravel (Blade and Inertia), WordPress,
Astro, Angular, and static sites.

Two rules that matter more than the command:

- **Never start a second server on an occupied port.** Check what is already listening
  (`lsof -i :3000` or `curl -sI http://localhost:3000`) and reuse it. Two dev servers on
  shifted ports is how you end up verifying a stale build.
- **Measure performance on a production build, not the dev server.** Dev servers ship
  unminified bundles, source maps, and HMR clients; their LCP and TBT numbers are fiction.
  Functional and visual checks are fine against dev. For Step 6, build and serve for real.

### Step 2 — Run the automated sweep

`scripts/verify_ui.py` does the mechanical part: loads the route at each viewport, captures
screenshots, records every console message and failed request, measures Core Web Vitals,
optionally runs an axe-core accessibility scan, and optionally pixel-diffs against a
previous run. It writes `report.json` + `report.md` + `screenshots/` and exits non-zero when
a check fails, so it works as a gate in a loop or in CI.

```bash
# First run: install once per environment
pip install playwright && playwright install chromium

# Baseline the page BEFORE your change when you can — it makes the diff meaningful
python scripts/verify_ui.py --url http://localhost:3000/posts/1 --out .verify/before

# After the change
python scripts/verify_ui.py \
  --url http://localhost:3000/posts/1 \
  --flow .verify/like-button.json \
  --baseline .verify/before \
  --out .verify/after \
  --a11y --dev-build
```

Useful flags (full list via `--help`):

| Flag | Why you would reach for it |
| --- | --- |
| `--flow FILE` | Drive the interaction and assert the result (Step 3) |
| `--viewport name=WxH` | Override the default mobile/tablet/desktop trio (repeatable) |
| `--a11y` / `--axe-path` | WCAG scan; `--axe-path` injects a local `axe.min.js` for offline/CI |
| `--baseline DIR` | Pixel-diff against a previous run to catch unintended visual drift |
| `--storage-state FILE` | Verify authenticated pages using a saved Playwright session |
| `--dev-build` | Report performance budget misses as warnings, not failures |
| `--ignore-console REGEX` | Silence a *known, understood* pre-existing warning — never a new one |
| `--fail-on-warning` | Strict mode for CI |
| `--wait-selector SEL` | Wait for a real render signal before measuring |

Add `.verify/` to `.gitignore`. It is evidence, not source.

**If Playwright is unavailable** (locked-down environment, no install rights), fall back to
browser MCP tools — Claude in Chrome (`mcp__claude-in-chrome__*`) or a Chrome DevTools MCP.
Perform the same checks manually: navigate, screenshot, click, read console messages, read
network requests, resize the window per viewport. The evidence standard does not change,
only the instrument. Note in your report which instrument you used.

### Step 3 — Prove the behavior, not the markup

The check that catches real bugs is the one that drives the UI and asserts what the user
would see. An element existing in the DOM proves the render path; only an interaction
proves the handler is wired, the state updates, and the UI re-renders.

Flow files are JSON arrays of steps. Every step is screenshotted, and a failure captures a
`-FAILED.png` at the moment things went wrong:

```json
[
  {"action": "assert_visible", "selector": "[data-testid=like]", "name": "like button renders"},
  {"action": "click",          "selector": "[data-testid=like]", "name": "click like"},
  {"action": "assert_text",    "selector": "[data-testid=like-count]", "value": "1", "name": "count increments"},
  {"action": "assert_text",    "selector": "[data-testid=like]", "value": "Liked", "name": "label flips"}
]
```

Prefer stable selectors — `data-testid`, `role=`, `text=` — over CSS classes, which change
every time someone touches the styles. Read `references/flows.md` for the full action
reference and copy-paste recipes: login, modal open/close, form validation errors, dark-mode
toggle, infinite scroll, file upload, toast assertions.

Also verify the negative cases the happy path hides: double-click (does it double-submit?),
rapid toggle (does state desync?), and the disabled/loading state.

### Step 4 — Triage the console and network

Zero new errors is the bar. But "zero messages" is unrealistic in most real codebases, so
triage rather than either panicking or ignoring.

The question for every message is: **did my change cause it?** Compare against the baseline
run. Pre-existing noise gets acknowledged in the report; anything new gets fixed or
explicitly justified.

`references/triage.md` covers what specific messages mean and how urgent they are —
hydration mismatches, missing `key` props, `act()` warnings, controlled/uncontrolled
switches, CORS failures, mixed content, 404s on assets, and the deprecation warnings that
are genuinely safe to defer.

### Step 5 — Responsive and accessibility

Default viewports: **390×844 mobile**, **820×1180 tablet**, **1440×900 desktop**. Adjust to
the project's real breakpoints when you know them.

At each viewport look for the four failures automated tools miss: horizontal overflow,
text clipped or overlapping, touch targets under 44×44px, and content hidden behind a
fixed header. `references/responsive.md` has the checklist plus the admin-surface
convention (admin panels and dashboards are desktop-only surfaces — verify them at desktop
and say so, rather than reporting a phantom mobile failure).

For accessibility, `--a11y` catches contrast, labels, ARIA misuse, and landmark problems.
It cannot catch focus order, keyboard traps, or a focus indicator you removed with
`outline: none`. Tab through anything interactive you added.
`references/accessibility.md` has the manual checklist and the fixes.

### Step 6 — Performance

Budgets, enforced against a production build: **LCP ≤ 2500ms**, **CLS ≤ 0.1**,
**TBT ≤ 200ms**, **TTFB ≤ 800ms**.

A regression here is usually traceable to something concrete you just did — an unoptimized
image, a render-blocking font, a heavy library imported at module scope, an element without
reserved dimensions. `references/performance.md` maps each metric to its likely causes and
fixes, and explains when a budget miss is genuinely acceptable.

If measuring properly is out of scope (no production build available, no time), say so in
the report rather than reporting dev-server numbers as if they were real.

### Step 7 — Report

Use `assets/verification-report.md` as the structure. Keep it short: what you claimed, what
you ran, what you found, what you did not check. Include screenshot paths — the screenshots
are the evidence, the prose is the index.

## The fix loop, and when to stop

When a check fails: fix the cause, then **rerun from Step 1** — not from the failing step.
A fix that resolves the reported failure while introducing a new console error is a lateral
move, and only a full rerun catches that.

Cap the loop at **three attempts on the same failure**. A fourth attempt on an unchanged
symptom means the diagnosis is wrong, not the fix. Stop and report: what fails, what you
tried, what you ruled out, and what you would investigate next. A precise blocker is far
more useful to a developer than a fourth speculative patch.

Never disable, skip, or loosen a check to make it pass. Never delete a test to turn a build
green. If a check is genuinely wrong for this project — a budget that does not fit, a lint
rule that misfires — say so explicitly and let the human decide.

## Honesty rules

These exist because the failure mode this skill prevents is not a bad UI — it is a
confident report about a UI nobody looked at.

- Never write "verified", "tested", or "confirmed working" about something you did not
  observe in a browser this session.
- "Should work" and "the change is straightforward" are not verification. Either check it
  or list it under **Not verified**.
- Screenshots taken before an interaction do not prove the interaction works.
- If the server would not start, the route 404s, or the environment blocks the browser, the
  outcome is **blocked**, not done. Report the blocker with the exact command and error, and
  say what you need to proceed.
- When you skip a check by choice (performance on a copy tweak, mobile on an admin screen),
  name the check and the reason. Deliberate scoping is professional; silent omission is not.

## Reference files

Read these as needed rather than upfront — each is self-contained.

| File | Read it when |
| --- | --- |
| `references/stack-playbooks.md` | Starting the app: per-framework commands, ports, prod builds, auth |
| `references/flows.md` | Writing a flow file — action reference and interaction recipes |
| `references/triage.md` | Deciding whether a console or network message matters |
| `references/responsive.md` | Choosing viewports and running the layout checklist |
| `references/accessibility.md` | Running the manual a11y pass and fixing violations |
| `references/performance.md` | Interpreting Core Web Vitals and fixing regressions |
| `assets/verification-report.md` | Writing the final report |
| `assets/flow.example.json` | Starting a flow file from a working example |
