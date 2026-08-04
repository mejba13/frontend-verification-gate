# Console and network triage

The bar is **no new errors**. Most real codebases already emit some noise, so the job is
attribution, not zero-tolerance. For every message ask: *did my change cause this?*

The cheapest way to answer that is a baseline run on the same route before the change
(`--out .verify/before`), then compare. Without a baseline, use judgment: does the message
name a file, component, or request you touched?

## Severity model

| Class | Examples | Action |
| --- | --- | --- |
| **Blocking** | Uncaught exception, hydration mismatch, failed chunk load, 5xx on a request the feature needs | Fix before reporting done |
| **Attributable** | Any new warning or 4xx traceable to the change | Fix, or justify explicitly in the report |
| **Pre-existing** | Present in the baseline, unrelated to the change | Note in the report; do not silently absorb into scope |
| **Tooling** | HMR/Fast Refresh logs, React DevTools nag, dev-only deprecations | Ignore (already filtered by default) |

`--ignore-console REGEX` is for pre-existing, understood noise only. Using it on a new
message is how a real bug gets shipped with a green report.

## Messages worth knowing

### `Hydration failed` / `Text content does not match server-rendered HTML`
Next.js, Nuxt, Remix, SvelteKit. The server HTML and the first client render disagree.
React discards the server tree and re-renders, so the page *looks* fine while event handlers
silently detach. Always a real bug.

Common causes: `Date`, `Math.random()`, `window`/`localStorage` read during render;
locale-dependent formatting; invalid nesting (`<div>` inside `<p>`, `<a>` inside `<a>`,
block elements inside `<button>`); browser extensions injecting DOM (verify in a clean
profile before blaming your code).

Fix: move non-deterministic values into `useEffect`, or gate with a mounted flag.

### `Warning: Each child in a list should have a unique "key" prop`
React reuses DOM nodes incorrectly without stable keys. Symptoms: input values jumping to
the wrong row, checkbox state sticking after a sort, animation glitches. Use a stable
identifier — never the array index for a list that reorders or filters.

### `Warning: A component is changing an uncontrolled input to be controlled`
A `value` prop started as `undefined` and became defined. React resets internal state at the
switch, which loses user input. Fix: initialise to `''`, not `undefined`.

### `Warning: Cannot update a component while rendering a different component`
A state setter is being called during render. It causes hard-to-trace re-render loops. Move
it into an effect or an event handler.

### `Warning: An update to X inside a test was not wrapped in act(...)`
Test-environment only. Signals unawaited async state updates; can make tests flaky but is
not a browser bug.

### `Maximum update depth exceeded` / page freeze
Infinite render loop — usually a `useEffect` whose dependency is a new object/array/function
identity on every render. Wrap in `useMemo`/`useCallback` or narrow the dependency list.

### `ExpressionChangedAfterItHasBeenCheckedError` (Angular)
Dev-mode only, but a genuine change-detection bug. The value changed after Angular checked
it — usually a parent mutated by a child. Move the update earlier or trigger detection
explicitly.

### `[Vue warn]: Failed to resolve component`
Component not registered/imported, or a name-casing mismatch. Renders as nothing at all —
easy to miss visually if the area is otherwise empty.

### `Failed to load resource: 404`
An asset path is wrong. Frequent causes: missing base path/subdirectory deployment, an
image referenced from CSS with a path relative to the source file rather than the output,
a font moved during a refactor. Always fix — 404s cost real latency and often mean the
production build is broken even when dev "works".

### `Refused to load … Content Security Policy`
A CSP directive blocks an inline script/style or a third-party origin. Either add the origin
to the policy or remove the inline usage (`nonce`/hash for legitimate inline scripts).
Common when adding an analytics snippet or an embedded widget.

### `Blocked by CORS policy`
The server did not return the required `Access-Control-Allow-*` headers. This is a server
configuration issue, not a frontend one — fix on the API side, and do not "work around" it
by disabling browser security.

### `Mixed Content: … requested an insecure resource`
An HTTPS page loading an HTTP asset. Browsers block it. Use protocol-relative or absolute
HTTPS URLs. Flag it — it also signals a misconfigured base URL.

### `Deprecation warning` / `[Deprecated] …`
Real but rarely urgent. Note it in the report with a suggested follow-up; do not expand
scope mid-change unless it is causing the failure you were sent to fix.

## Network triage

| Signal | Reading |
| --- | --- |
| **5xx** | Server error — always blocking, even if the UI degrades gracefully |
| **404** on an asset | Broken path; fix |
| **404** on an API call | Wrong endpoint or a route not registered |
| **401 / 403** | Auth issue — confirm whether your session setup is at fault before blaming the code |
| **419** (Laravel) | Expired/missing CSRF token |
| **422** | Validation rejection — often correct behaviour; confirm the UI surfaces it |
| **Pending forever** | Missing timeout or a request the client never resolves; check for a hung spinner |
| **Duplicate identical POSTs** | No double-submit guard — see the recipe in `flows.md` |
| **Request fires on every keystroke** | Missing debounce |

`report.json` lists every non-2xx response and failed request per viewport under
`viewports[].network`. Read it rather than eyeballing the summary when attribution is
unclear.

## Server-side output

The browser console never shows server errors. Tail the dev server log alongside:

- Next.js/Nuxt Server Components and route handlers → terminal running `npm run dev`
- Laravel → `storage/logs/laravel.log`
- WordPress → `wp-content/debug.log` with `WP_DEBUG_LOG` enabled

A page that renders correctly while the server log fills with warnings is not verified.
