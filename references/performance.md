# Performance verification

## Budgets

| Metric | Budget | What it measures |
| --- | --- | --- |
| **LCP** — Largest Contentful Paint | ≤ 2500 ms | When the main content becomes visible |
| **CLS** — Cumulative Layout Shift | ≤ 0.1 | How much the layout jumps during load |
| **TBT** — Total Blocking Time | ≤ 200 ms | Main-thread blocking; the lab proxy for INP |
| **TTFB** — Time to First Byte | ≤ 800 ms | Server + network latency before anything renders |

Override per project: `--budget-lcp 2000 --budget-cls 0.05`. Skip entirely for changes that
cannot affect performance (a copy edit, a colour token) with `--skip-budgets` — and say so
in the report rather than silently omitting the section.

## Measure on a production build

Dev servers serve unminified modules, source maps, and a live-reload client. LCP and TBT
measured there are inflated by an amount that varies per project, which makes them useless
as a pass/fail signal.

```bash
npm run build && npm run preview      # Vite
npm run build && npm run start        # Next.js
npm run build && npx serve -s dist    # generic
```

Verifying against dev is fine for everything else — use `--dev-build` so budget misses are
reported as warnings and clearly labelled as indicative.

## INP is not measurable in a lab

Interaction to Next Paint requires real user interaction and is only meaningful as field
data (CrUX, RUM). TBT is the lab proxy: high TBT reliably predicts poor INP. If the change
adds a heavy event handler, measure the handler directly instead:

```json
{"action": "eval", "value": "(()=>{const t=performance.now();document.querySelector('[data-testid=filter]').click();return Math.round(performance.now()-t)})()", "name": "handler cost ms"}
```

Anything over ~50ms on the main thread is a dropped frame the user can feel.

## Diagnosing a regression

Compare against the baseline run. A regression is almost always traceable to something
specific you just did.

### LCP got worse
- **An unoptimized image became the LCP element.** Serve WebP/AVIF, size it correctly, and
  add `fetchpriority="high"` to the hero. Never lazy-load the LCP image — a `loading="lazy"`
  hero is the single most common self-inflicted LCP regression.
- **A render-blocking resource was added.** A synchronous `<script>` in `<head>`, an
  additional stylesheet, or a font import. Defer, or inline the critical part.
- **A web font blocks text paint.** Use `font-display: swap` and preload the font used above
  the fold.
- **The LCP element now waits on client-side data.** Server-render it, or ship a skeleton
  with reserved dimensions.

### CLS got worse
- **Images or embeds without dimensions.** Always set `width`/`height` (or `aspect-ratio`) so
  the browser reserves space before the asset arrives.
- **Content injected above existing content** — banners, cookie notices, alerts. Reserve the
  space, or render them in an overlay that does not displace flow.
- **A font swap with different metrics.** Use `size-adjust` / `ascent-override`, or pick a
  fallback with similar metrics.
- **An element animated with `top`/`left`/`height`** instead of `transform`. Transform and
  opacity do not trigger layout and do not count toward CLS.

### TBT got worse
- **A heavy library imported at module scope.** Dynamic-import it at the point of use.
  Charting, date, editor, and icon libraries are the usual weight.
- **Work in an effect on every render.** Memoise, or move it off the critical path.
- **A large list rendered without virtualisation.** Above a few hundred rows, virtualise.
- **A synchronous JSON parse or heavy computation during hydration.** Move it to a worker or
  defer it past first paint.

### TTFB got worse
Server-side, not frontend — but still worth reporting. Common causes: an N+1 query added to
the page controller, a blocking third-party API call during render, a cache that stopped
being hit because the cache key changed.

## Bundle size

Metrics can look fine while the bundle quietly grows. When the change adds a dependency,
check the delta:

```bash
npm run build           # most build tools print per-chunk sizes
npx source-map-explorer 'dist/**/*.js'   # what actually landed in the bundle
```

A new dependency that adds more than ~20KB gzipped to the initial bundle deserves a line in
the report and, usually, a dynamic import.

## When a budget miss is acceptable

Sometimes it is — say so explicitly rather than quietly passing:

- The page was already over budget before the change, and the change did not make it worse
  (report both numbers).
- The regression is confined to an internal admin surface with a known trade-off.
- The measurement came from a dev build and the production number is unknown (state this
  plainly — never present a dev-server number as a verified production result).

What is never acceptable is raising the budget to make the report green.
