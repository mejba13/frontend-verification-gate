# Responsive verification

## Default viewport set

| Name | Size | Represents |
| --- | --- | --- |
| `mobile` | 390×844 | iPhone 14/15 class — the most common real-world width |
| `tablet` | 820×1180 | iPad Air portrait — where two-column layouts collapse badly |
| `desktop` | 1440×900 | Standard laptop |

Override when the project's breakpoints differ:
`--viewport small=360x640 --viewport wide=1920x1080`

Two widths worth adding when the layout is dense: **320px** (smallest phone still in real
use — the width where text overflows first) and **1920px** (where centred layouts sometimes
stretch to unreadable line lengths).

## Surface scope conventions

Not every surface deserves every viewport. Scoping deliberately is professional; scoping
silently is not — state the scope in the report either way.

| Surface | Verify at | Reason |
| --- | --- | --- |
| Marketing / public pages | mobile, tablet, desktop | Majority of traffic is mobile |
| App / product UI | mobile, tablet, desktop | Unless the product is explicitly desktop-only |
| Admin panels, dashboards, `/wp-admin`, CMS back ends | desktop only | Operated at a desk; flagging their mobile layout produces noise, not signal |
| Email templates | separate discipline | Browser rendering does not predict Outlook/Gmail |
| Print stylesheets | desktop + print emulation | |

## What automation misses

The screenshots prove *what* rendered. These five failures need your eyes on them:

1. **Horizontal overflow.** The page scrolls sideways on mobile. Usually a fixed width, an
   unconstrained image, a long unbroken string (URL, token, ID), or a table without an
   overflow wrapper. Detect it directly:
   ```json
   {"action": "eval", "value": "document.documentElement.scrollWidth - document.documentElement.clientWidth", "name": "horizontal overflow px — expect 0"}
   ```
   To find the culprit element:
   ```json
   {"action": "eval", "value": "[...document.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right > document.documentElement.clientWidth + 1).slice(0,5).map(e=>e.tagName+'.'+e.className).join(' | ')", "name": "overflowing elements"}
   ```

2. **Clipped or overlapping text.** Fixed-height containers plus longer copy at narrow
   widths. Look for cut descenders and text sitting on top of other text. Test with the
   longest realistic content, not the demo string.

3. **Touch targets below 44×44px.** WCAG 2.5.5 / platform guidance. Icon-only buttons,
   close "×" controls, and tightly packed link lists are the usual offenders. Padding
   counts toward the target; the visual icon does not have to grow.

4. **Content hidden behind fixed chrome.** Sticky headers, bottom nav bars, cookie banners,
   and the mobile browser URL bar all steal viewport height. Check that the first heading is
   not tucked under a fixed header after an in-page anchor jump.

5. **Interactions that only exist on hover.** Hover has no equivalent on touch. A dropdown,
   tooltip, or action row that appears on `:hover` is unreachable on mobile unless there is
   a tap equivalent. This is the single most common responsive defect in dashboards.

## Additional checks worth running

- **Zoom to 200%** (WCAG 1.4.4): set a 640×480 viewport as a proxy. Content must reflow
  without horizontal scrolling and without losing functionality.
- **Landscape phone** (844×390): fixed-height heroes and full-screen modals commonly break
  here; modal content becomes unreachable because the container does not scroll.
- **Long content**: verify with realistic worst-case data — a 60-character name, a
  three-line product title, an empty list, a list of 500.
- **RTL**, if shipped: `--user-agent` will not do it; set `dir="rtl"` via an `eval` step and
  screenshot. Icons with directional meaning and non-symmetric padding are the usual breaks.

## Reading the pixel diff

`--baseline` reports the percentage of pixels that changed versus the previous run. Interpret
it, do not just check the number:

- **0%** on a route you did not intend to touch — good, the blast radius held.
- **A few percent, localised** — check the `bbox` in `report.json`. Does the changed region
  match where you expected the change?
- **Large percentage** — usually a layout shift, a font that failed to load, or a theme
  variable change. Open the diff image before assuming it is intended.
- **`size-mismatch`** — the page height changed, which is expected when adding an element,
  but confirm nothing else moved with it.

Antialiasing noise is absorbed by a per-channel tolerance, so a diff above ~0.5% is real
change, not rendering jitter.
