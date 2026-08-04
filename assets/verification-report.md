# UI verification — <feature or change name>

**Verdict:** PASS / FAIL / BLOCKED
**Change:** <one sentence: what was changed and where>
**Environment:** <dev server | production build> at <URL> · <framework + version> · <browser/instrument>

## Claim under test

> <The user-visible behaviour, as a testable sentence. e.g. "Clicking Like increments the
> count and flips the label to Liked, and the state survives a page refresh.">

## Evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Loads without error | PASS | `.verify/after/report.md` |
| Renders as intended | PASS | `screenshots/desktop-01-initial.png` |
| Interaction behaves | PASS | 4/4 flow steps — `screenshots/desktop-flow-*.png` |
| Console clean | PASS | 0 new errors, 0 new warnings |
| Network clean | PASS | 0 failed requests, 0 4xx/5xx |
| Responsive | PASS | mobile 390×844, tablet 820×1180, desktop 1440×900 |
| Accessibility | PASS | axe-core WCAG 2.1 AA — 0 violations; keyboard path verified manually |
| Performance | PASS | LCP 1180ms · CLS 0.01 · TBT 40ms (production build) |

## Findings

<Only real findings. Remove the section entirely if there were none.>

1. **<Severity> — <short title>**
   <What is wrong, where, and the user impact.>
   *Fixed in:* `path/to/file.tsx` — <what the fix does>
   *or* *Deferred:* <why, and what it would take>

## Not verified

<Everything outside the scope you ran, with the reason. Never omit this section — if
everything was verified, write "Nothing — all applicable checks ran.">

- <Check> — <reason: out of scope / environment limitation / needs credentials>

## Blast radius checked

- `<route>` — primary, full verification
- `<route>` — smoke: loads, renders, clean console

## Reproduce

```bash
<exact commands to re-run this verification>
```
