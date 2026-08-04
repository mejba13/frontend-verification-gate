# Stack playbooks — getting a real running app

How to start, build, and reach each stack, plus the startup noise that is normal and the
gotchas that waste the most time. Jump to your stack; skip the rest.

- [Detect the stack first](#detect-the-stack-first)
- [Port hygiene](#port-hygiene)
- [Next.js](#nextjs) · [Vite (React/Vue/Svelte)](#vite-reactvuesvelte) · [Create React App / Webpack](#create-react-app--webpack)
- [Laravel — Blade](#laravel--blade) · [Laravel — Inertia/Livewire](#laravel--inertia--livewire)
- [WordPress](#wordpress) · [Astro](#astro) · [Angular](#angular) · [Nuxt](#nuxt) · [Static / no build](#static--no-build)
- [Authenticated pages](#authenticated-pages)
- [Production builds for performance](#production-builds-for-performance)
- [Containers and remote hosts](#containers-and-remote-hosts)

## Detect the stack first

```bash
ls package.json composer.json wp-config.php angular.json astro.config.* nuxt.config.* 2>/dev/null
cat package.json 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('scripts'));print(list(d.get('dependencies',{})))"
```

The `scripts` block is authoritative — a project may use `pnpm`, `bun`, `yarn`, or a
`Makefile` wrapper. Match the lockfile: `pnpm-lock.yaml` → pnpm, `bun.lockb` → bun,
`yarn.lock` → yarn, `package-lock.json` → npm. Using the wrong package manager can install a
different dependency tree than the one the app actually runs on.

## Port hygiene

Before starting anything:

```bash
curl -sI -m 2 http://localhost:3000 | head -1   # already serving?
lsof -i :3000 -sTCP:LISTEN                       # who owns it?
```

If a server is already running the project under test, **reuse it**. Starting a second
instance means it silently binds a different port and you verify a stale build on the old
one. If you must start one, background it and wait for readiness rather than sleeping a
fixed number of seconds:

```bash
npm run dev > /tmp/dev.log 2>&1 &
for i in $(seq 1 60); do curl -sf -m 1 http://localhost:3000 >/dev/null && break; sleep 1; done
tail -20 /tmp/dev.log   # confirm it actually booted, not crash-looped
```

## Next.js

```bash
npm run dev                       # http://localhost:3000
npm run build && npm run start    # production, same port — use this for performance
```

- **Normal noise:** Fast Refresh messages, `<Image>` optimization warnings in dev.
- **Never normal:** `Hydration failed because the initial UI does not match`. That is a real
  bug — usually `Date`/`Math.random()`/`window` used during render, or invalid HTML nesting
  (`<div>` inside `<p>`, `<a>` inside `<a>`). It often renders fine and breaks interactivity.
- App Router: a change to `layout.tsx` affects every route beneath it — widen the blast
  radius accordingly. Server Component errors surface in the terminal, not the browser
  console, so tail the dev log too.
- `next dev --turbopack` and webpack dev can differ; verify with whatever the project's
  `dev` script actually uses.

## Vite (React/Vue/Svelte)

```bash
npm run dev                       # http://localhost:5173
npm run build && npm run preview  # http://localhost:4173 — production
```

- **Normal noise:** `[vite] connecting...`, `[vite] connected.`, HMR update logs.
- Vite dev does not type-check. Run `vue-tsc --noEmit` / `tsc --noEmit` separately — a type
  error that would break the build can hide behind a working dev server.
- `--host` is required to reach it from another machine or container.

## Create React App / Webpack

```bash
npm start                                    # http://localhost:3000
npm run build && npx serve -s build -l 5000  # production
```

CRA opens a browser automatically; suppress it with `BROWSER=none npm start` in headless
environments.

## Laravel — Blade

```bash
php artisan serve                 # http://127.0.0.1:8000
npm run dev                       # Vite asset server — must run alongside
npm run build                     # compiled assets; required for production-mode checks
```

- If styles are missing, the Vite dev server is not running or `@vite` directives are absent
  from the layout. That is an environment problem, not a change regression — say so.
- `APP_DEBUG=true` shows the Ignition error page; a 500 renders as a full error page rather
  than a blank screen, which makes screenshots genuinely diagnostic.
- Clear caches after config/route/view edits: `php artisan optimize:clear`.
- CSRF: a 419 response means an expired or missing token, not a broken feature.

## Laravel — Inertia / Livewire

- Inertia: page components live in `resources/js/Pages`. A change there needs the Vite dev
  server running; a hard refresh proves SSR/initial props, and client navigation proves the
  Inertia visit. Check both.
- Livewire: interactions round-trip to the server. Watch the **network** panel for
  `/livewire/update` calls — a silent 500 there looks like a dead button in the UI.
  `wire:loading` states are worth screenshotting.

## WordPress

```bash
wp server --host=localhost --port=8080   # WP-CLI built-in
# or: ddev start / valet link / docker compose up
```

- **Admin (`/wp-admin`) is a desktop-only surface.** Verify it at 1440×900 and note that
  scope in the report — flagging its mobile layout as a defect is noise.
- **Front end is verified across mobile/tablet/desktop**, logged out *and* logged in (the
  admin bar shifts layout by 32px and has broken sticky headers many times).
- Bust caches after template edits: object cache, page cache plugins (WP Rocket, W3TC), and
  a CDN if one is in front. Verifying a cached page is verifying nothing.
- Console noise from unrelated plugins is common — baseline first, then attribute only new
  messages to your change.
- Theme/plugin edits: check `WP_DEBUG` output in `wp-content/debug.log` alongside the
  browser console; PHP notices never reach the browser.

## Astro

```bash
npm run dev                        # http://localhost:4321
npm run build && npm run preview
```

Islands hydrate per `client:*` directive. If an interaction does nothing, the most likely
cause is a missing `client:load` / `client:visible` — the component renders as static HTML.

## Angular

```bash
ng serve                           # http://localhost:4200
ng build --configuration production && npx serve dist/<app> -l 5000
```

Zone.js swallows some errors into the console rather than crashing — read console output
carefully. Watch for `ExpressionChangedAfterItHasBeenCheckedError`, which is a real
change-detection bug even though the page looks fine.

## Nuxt

```bash
npm run dev                        # http://localhost:3000
npm run build && npm run preview
```

Same hydration-mismatch class of bug as Next.js; check the terminal for server-side errors.

## Static / no build

```bash
python3 -m http.server 8000        # from the directory containing index.html
```

Opening `file://` directly breaks `fetch`, ES modules, and service workers under CORS rules.
Always serve over HTTP, even for a single page.

## Authenticated pages

Save a session once, then reuse it across runs — far more reliable than scripting a login
into every flow:

```python
# save_session.py — run once, headed, and log in by hand
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    ctx = b.new_context()
    ctx.new_page().goto("http://localhost:3000/login")
    input("Log in in the browser window, then press Enter here...")
    ctx.storage_state(path=".verify/storage-state.json")
    b.close()
```

Then: `python scripts/verify_ui.py --url ... --storage-state .verify/storage-state.json`

Alternatives: `--header 'Authorization: Bearer ...'` for token auth, or a login flow file
(see `flows.md`) when credentials are test-only. **Never commit `storage-state.json` or put
real credentials in a flow file** — add both to `.gitignore`, and use env vars for secrets.

## Production builds for performance

Dev servers serve unminified code with source maps and a live-reload client attached. LCP
and TBT measured there are inflated by a factor that varies per project, which makes them
useless as a pass/fail signal. Two honest options:

1. Build and serve for real, then measure (preferred).
2. Measure against dev with `--dev-build` so budget misses are reported as warnings, and
   state in the report that the numbers are indicative only.

## Containers and remote hosts

- Bind to `0.0.0.0`, not `127.0.0.1`, or the port is unreachable from outside the container
  (`vite --host`, `php artisan serve --host=0.0.0.0`, `next dev -H 0.0.0.0`).
- A shell in a cloud sandbox cannot reach `localhost` on the user's machine. If the app runs
  on their machine and you are not, either have them expose a public URL or run the
  verification on their side — do not fabricate results from a URL you never loaded.
