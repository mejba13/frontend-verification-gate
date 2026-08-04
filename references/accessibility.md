# Accessibility verification

Target: **WCAG 2.1 Level AA** for the elements you added or restyled. You are not auditing
the whole product — you are proving your change did not make it worse and is usable by
everyone who reaches it.

## Automated pass

```bash
python scripts/verify_ui.py --url ... --a11y
python scripts/verify_ui.py --url ... --a11y --axe-path ./node_modules/axe-core/axe.min.js  # offline/CI
```

axe-core catches roughly 30–40% of WCAG issues — the deterministic ones. `critical` and
`serious` violations are reported as errors; `moderate` and `minor` as warnings.

If the scan cannot run (no network for the CDN, no local copy), the report says so
explicitly as a warning rather than passing silently. Install a local copy to close the gap:
`npm i -D axe-core` then pass `--axe-path`.

## Manual pass — the part automation cannot do

Roughly a third of an accessibility failure surface is invisible to a scanner. Five checks,
two minutes:

### 1. Keyboard reachability
Tab through the page. Every interactive element you added must be reachable and activatable
with `Enter` (buttons, links) or `Space` (buttons, checkboxes).

A `<div onClick>` is the classic failure: it is invisible to keyboard and screen-reader
users. Use a real `<button>`. If you cannot, it needs `role="button"`, `tabindex="0"`, and
handlers for both `Enter` and `Space` — three things to get right instead of zero.

### 2. Visible focus indicator
`outline: none` without a replacement makes the page unusable for keyboard navigation. Tab
to your element and screenshot it — the focus state must be visibly distinct with at least
3:1 contrast against the adjacent background. `:focus-visible` gives keyboard users the ring
without showing it on mouse click.

### 3. Focus management for dynamic UI
- Modal/dialog opens → focus moves into the dialog; `Escape` closes it; focus returns to
  the trigger.
- Focus is trapped inside an open modal — tabbing must not wander into the page behind it.
- Content removed → focus does not land on `document.body` (screen readers lose their place).
- Route change in an SPA → focus moves to the new heading or main landmark.

```json
{"action": "eval", "value": "document.activeElement.tagName + ' ' + (document.activeElement.getAttribute('aria-label')||document.activeElement.textContent||'').slice(0,60)", "name": "where focus is"}
```

### 4. Accessible names
Every control needs a name a screen reader can announce. Icon-only buttons are the most
common miss.

```html
<!-- no name at all -->
<button><svg>…</svg></button>

<!-- named -->
<button aria-label="Close dialog"><svg aria-hidden="true">…</svg></button>
```

Inputs need a real `<label for>`, or `aria-label` / `aria-labelledby`. Placeholder text is
not a label — it disappears on focus and many screen readers skip it. Verify by selecting
with `role=button[name="Close dialog"]`: if the selector matches, the accessible name exists.

### 5. State communicated non-visually
Colour alone cannot carry meaning (WCAG 1.4.1). An error field needs text or an icon, not
just a red border. Toggles need `aria-pressed` or `aria-checked`; expandable sections need
`aria-expanded`; loading regions need `aria-busy` or a live region so the change is
announced.

## Fixing the violations axe reports most often

| Rule | Meaning | Fix |
| --- | --- | --- |
| `color-contrast` | Below 4.5:1 for body text, 3:1 for ≥18.66px bold or ≥24px | Darken the foreground or lighten the background; do not fix with a font-weight change alone |
| `button-name` / `link-name` | No accessible name | `aria-label`, or visually-hidden text |
| `image-alt` | `<img>` without `alt` | Describe the content; `alt=""` for purely decorative images |
| `label` | Form field unlabelled | `<label for>` bound to the input `id` |
| `aria-required-attr` | ARIA role missing its required attributes | Add them, or drop the role and use the native element |
| `aria-valid-attr-value` | `aria-labelledby`/`describedby` points at a missing id | Fix the reference |
| `heading-order` | Heading levels skip (h2 → h4) | Headings convey structure, not size — style with CSS |
| `landmark-one-main` | No `<main>` | Wrap the primary content |
| `region` | Content outside any landmark | Use `<header>`, `<nav>`, `<main>`, `<footer>` |
| `duplicate-id` | Repeated ids | Breaks label and ARIA references |
| `nested-interactive` | Button inside a link, etc. | Flatten; the inner control is unreachable |

## Contrast, quickly

Ratios: **4.5:1** normal text, **3:1** large text and UI component boundaries/focus rings,
**7:1** for AAA if the project targets it.

Frequent misses: placeholder text, disabled-looking-but-enabled controls, light grey
secondary text (`#999` on white is 2.8:1 — fails), white text on a mid-tone brand colour,
and text over a photographic background without a scrim.

## Reduced motion

If the change adds animation, respect the OS preference:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

Verify by launching Chromium with the preference forced, or emulate it in an `eval` step.
Parallax and autoplaying motion can cause genuine vestibular symptoms — this is a real
accessibility requirement, not a preference.

## Reporting

State which pass you ran: automated only, automated + manual keyboard, or manual only when
the scanner was unavailable. "Accessibility checked" without saying how is the kind of claim
this skill exists to prevent.
