# frontend-verification-gate

[![smoke](https://github.com/mejba13/frontend-verification-gate/actions/workflows/smoke.yml/badge.svg)](https://github.com/mejba13/frontend-verification-gate/actions/workflows/smoke.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A Claude skill that stops "the edit applied" from being reported as "the UI works."

A clean diff proves a file changed. It proves nothing about whether the button renders, the
click handler fires, the layout survives a 390px viewport, or the page still hydrates
without throwing. This skill is the gate between those two claims — it makes Claude run the
app, drive the interaction in a real browser, and collect evidence before declaring a
frontend change done.

Works with Claude Code and Cowork. The verification script is standalone Python, so it also
runs on its own and in CI.

## What it checks

| | |
| --- | --- |
| **Renders** | Screenshots at mobile (390×844), tablet (820×1180), desktop (1440×900) |
| **Behaves** | Scripted interactions with assertions — proves state changed, not just that a click landed |
| **Clean** | Console errors/warnings, uncaught exceptions, failed requests, 4xx/5xx responses |
| **Accessible** | axe-core WCAG 2.1 AA scan + a manual keyboard/focus checklist |
| **Fast** | LCP, CLS, TBT, TTFB against budgets |
| **Unchanged elsewhere** | Optional pixel diff against a baseline run |

## Install

**As a Claude skill**

```bash
git clone https://github.com/mejba13/frontend-verification-gate.git
# Claude Code
cp -r frontend-verification-gate ~/.claude/skills/
# or per-project
cp -r frontend-verification-gate .claude/skills/
```

Cowork: download `frontend-verification-gate.skill` from
[Releases](https://github.com/mejba13/frontend-verification-gate/releases) and save it from
the file card.

**Dependencies for the script**

```bash
pip install -r requirements.txt
playwright install chromium
```

## Quick start

```bash
# Baseline the page before your change (optional, makes the diff meaningful)
python scripts/verify_ui.py --url http://localhost:3000/posts/1 --out .verify/before

# After the change
python scripts/verify_ui.py \
  --url http://localhost:3000/posts/1 \
  --flow flow.json \
  --baseline .verify/before \
  --out .verify/after \
  --a11y --dev-build
```

Writes `report.md`, `report.json`, and `screenshots/` to `--out`, and exits non-zero when a
check fails — so it drops into CI unchanged.

A flow file drives the interaction and asserts the result:

```json
[
  {"action": "assert_visible", "selector": "[data-testid=like]", "name": "button renders"},
  {"action": "click",          "selector": "[data-testid=like]", "name": "click like"},
  {"action": "assert_text",    "selector": "[data-testid=count]", "value": "1", "name": "count increments"}
]
```

Common flags — full list via `--help`:

| Flag | Purpose |
| --- | --- |
| `--flow FILE` | Interaction steps with assertions |
| `--viewport name=WxH` | Override the default viewport trio (repeatable) |
| `--a11y` / `--axe-path` | WCAG scan; `--axe-path` injects a local `axe.min.js` for offline/CI |
| `--baseline DIR` | Pixel-diff against a previous run |
| `--storage-state FILE` | Verify authenticated pages with a saved session |
| `--dev-build` | Performance budget misses become warnings, not failures |
| `--fail-on-warning` | Strict mode |

## Layout

```
SKILL.md                      The verification contract and workflow Claude follows
scripts/verify_ui.py          Standalone Playwright sweep (no other project deps)
references/
  stack-playbooks.md          Next.js, Vite, Laravel, WordPress, Astro, Angular, Nuxt, static
  flows.md                    Action reference + interaction recipes
  triage.md                   What each console/network message actually means
  responsive.md               Viewport matrix and the failures automation misses
  accessibility.md            Manual a11y pass and common fixes
  performance.md              Core Web Vitals budgets and regression causes
assets/                       Report template, example flow file
tests/                        Fixtures and smoke test
```

## Design notes

- **Evidence over assertion.** Anything Claude could not check is listed under *Not verified*
  with a reason, rather than silently omitted.
- **Three-attempt cap.** After three failed fixes on the same symptom, the skill stops and
  reports the blocker. A fourth speculative patch means the diagnosis is wrong, not the fix.
- **Never loosen a check to make it pass.** Budgets and rules that do not fit a project get
  flagged for a human, not edited away.
- **Progressive disclosure.** `SKILL.md` stays small; references load only when relevant.

## Contributing

Issues and PRs welcome — especially stack playbooks for frameworks not yet covered. Run
`tests/smoke_test.sh` before submitting.

## License

MIT © [Engr Mejba Ahmed](https://mejba.me)
