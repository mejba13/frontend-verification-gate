#!/usr/bin/env python3
"""
verify_ui.py — deterministic browser verification sweep for a frontend change.

Runs one page (or a scripted interaction flow) across multiple viewports and
collects the evidence a human reviewer would look for:

  * screenshots per viewport (and per flow step)
  * console errors / warnings, uncaught page exceptions
  * failed requests and >=400 responses
  * Core Web Vitals (LCP, CLS, TTFB) + long-task total blocking time
  * optional axe-core accessibility scan
  * optional pixel diff against a baseline screenshot set

Writes report.json + report.md + screenshots/ into --out, and exits non-zero
when a check fails, so it can be used as a gate in a loop or in CI.

Usage:
  python verify_ui.py --url http://localhost:3000/settings --out .verify/settings
  python verify_ui.py --url http://localhost:3000 --flow flow.json --a11y
  python verify_ui.py --url ... --baseline .verify/before --out .verify/after

Requires: playwright (`pip install playwright && playwright install chromium`).
Pillow is optional and only needed for --baseline diffs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_VIEWPORTS = ["mobile=390x844", "tablet=820x1180", "desktop=1440x900"]

# Noise that is a property of dev tooling, not of the change under test.
DEFAULT_IGNORES = [
    r"Download the React DevTools",
    r"\[vite\] connect(ing|ed)",
    r"\[HMR\]",
    r"webpack-dev-server",
    r"Lit is in dev mode",
    r"React Router Future Flag Warning",
    r"Fast Refresh",
]

# The a11y scanner is injected by this tool, so its own traffic is never a
# finding about the page under test.
TOOL_NOISE = [r"cdnjs\.cloudflare\.com/ajax/libs/axe-core"]

# Budgets follow Google's "good" thresholds. Tighten per project as needed.
DEFAULT_BUDGETS = {"lcp_ms": 2500.0, "cls": 0.1, "tbt_ms": 200.0, "ttfb_ms": 800.0}

VITALS_JS = """
() => new Promise((resolve) => {
  const out = { lcp_ms: null, cls: null, tbt_ms: 0, ttfb_ms: null, dcl_ms: null, load_ms: null };
  try {
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav) {
      out.ttfb_ms = nav.responseStart;
      out.dcl_ms = nav.domContentLoadedEventEnd;
      out.load_ms = nav.loadEventEnd || null;
    }
  } catch (e) {}

  let cls = 0;
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}

  let lcp = null;
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      if (entries.length) lcp = entries[entries.length - 1].startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {}

  let tbt = 0;
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.duration > 50) tbt += entry.duration - 50;
      }
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) {}

  setTimeout(() => {
    out.cls = Math.round(cls * 10000) / 10000;
    out.lcp_ms = lcp === null ? null : Math.round(lcp);
    out.tbt_ms = Math.round(tbt);
    resolve(out);
  }, 1200);
})
"""

AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    severity: str  # "error" | "warning" | "info"
    check: str
    message: str
    detail: str = ""


@dataclass
class ViewportResult:
    name: str
    width: int
    height: int
    screenshots: list[str] = field(default_factory=list)
    console: list[dict[str, Any]] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    vitals: dict[str, Any] = field(default_factory=dict)
    a11y: dict[str, Any] = field(default_factory=dict)
    flow: list[dict[str, Any]] = field(default_factory=list)
    diff: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_viewport(spec: str) -> tuple[str, int, int]:
    if "=" in spec:
        name, size = spec.split("=", 1)
    else:
        name, size = spec, spec
    w, h = size.lower().split("x", 1)
    return name, int(w), int(h)


def compile_ignores(extra: list[str], keep_defaults: bool) -> list[re.Pattern]:
    pats = list(extra) + TOOL_NOISE
    if keep_defaults:
        pats += DEFAULT_IGNORES
    return [re.compile(p, re.I) for p in pats]


def ignored(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text or "") for p in patterns)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "step"


# ---------------------------------------------------------------------------
# Flow execution
# ---------------------------------------------------------------------------


def run_flow(page, steps: list[dict], shots_dir: Path, vp_name: str) -> tuple[list[dict], list[Finding]]:
    """Execute scripted interaction steps. Each step:
    {"action": "click|fill|press|hover|select|goto|wait|wait_for|screenshot|
                assert_text|assert_visible|assert_hidden|assert_url|eval",
     "selector": "...", "value": "...", "name": "opens the modal"}
    Selectors accept Playwright syntax, including text= and role= engines.
    """
    log: list[dict] = []
    findings: list[Finding] = []

    for i, step in enumerate(steps):
        action = step.get("action", "").lower()
        sel = step.get("selector")
        val = step.get("value")
        name = step.get("name") or f"{action} {sel or val or ''}".strip()
        entry = {"index": i, "action": action, "name": name, "status": "ok", "error": ""}
        t0 = time.time()
        try:
            if action == "goto":
                page.goto(val, wait_until="networkidle")
            elif action == "click":
                page.click(sel, timeout=step.get("timeout", 10000))
            elif action == "fill":
                page.fill(sel, val, timeout=step.get("timeout", 10000))
            elif action == "press":
                (page.locator(sel) if sel else page.keyboard).press(val)
            elif action == "hover":
                page.hover(sel, timeout=step.get("timeout", 10000))
            elif action == "select":
                page.select_option(sel, val, timeout=step.get("timeout", 10000))
            elif action == "wait":
                page.wait_for_timeout(int(val or 500))
            elif action == "wait_for":
                page.wait_for_selector(sel, timeout=step.get("timeout", 10000))
            elif action == "eval":
                entry["result"] = page.evaluate(val)
            elif action == "assert_visible":
                page.wait_for_selector(sel, state="visible", timeout=step.get("timeout", 10000))
            elif action == "assert_hidden":
                page.wait_for_selector(sel, state="hidden", timeout=step.get("timeout", 10000))
            elif action == "assert_text":
                page.wait_for_selector(sel, timeout=step.get("timeout", 10000))
                actual = page.inner_text(sel)
                if val not in actual:
                    raise AssertionError(f"expected {val!r} in {actual[:200]!r}")
            elif action == "assert_url":
                if val not in page.url:
                    raise AssertionError(f"expected {val!r} in URL {page.url!r}")
            elif action == "screenshot":
                pass  # handled below
            else:
                raise ValueError(f"unknown action {action!r}")

            if step.get("screenshot", True):
                shot = shots_dir / f"{vp_name}-flow-{i:02d}-{slug(name)}.png"
                page.screenshot(path=str(shot), full_page=step.get("full_page", False))
                entry["screenshot"] = shot.name
        except Exception as exc:  # noqa: BLE001 - report, never crash the sweep
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            findings.append(
                Finding("error", "flow", f"[{vp_name}] step {i} failed: {name}", entry["error"])
            )
            try:
                shot = shots_dir / f"{vp_name}-flow-{i:02d}-{slug(name)}-FAILED.png"
                page.screenshot(path=str(shot))
                entry["screenshot"] = shot.name
            except Exception:
                pass
            log.append(entry)
            if step.get("continue_on_failure", False):
                continue
            break

        entry["ms"] = int((time.time() - t0) * 1000)
        log.append(entry)

    return log, findings


# ---------------------------------------------------------------------------
# Optional pixel diff
# ---------------------------------------------------------------------------


def pixel_diff(baseline: Path, current: Path, out: Path, tolerance: int = 8) -> dict[str, Any]:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {"status": "skipped", "reason": "Pillow not installed"}
    if not baseline.exists():
        return {"status": "skipped", "reason": f"no baseline {baseline.name}"}
    a = Image.open(baseline).convert("RGB")
    b = Image.open(current).convert("RGB")
    if a.size != b.size:
        return {"status": "size-mismatch", "baseline": a.size, "current": b.size}
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    # Tolerance absorbs sub-pixel antialiasing so genuine changes stand out.
    mask = diff.convert("L").point(lambda p: 255 if p > tolerance else 0)
    changed = mask.histogram()[255]
    total = a.size[0] * a.size[1]
    if bbox:
        diff.save(out)
    return {
        "status": "ok",
        "changed_pixels": changed,
        "changed_pct": round(100 * changed / total, 3),
        "bbox": bbox,
        "diff_image": out.name if bbox else None,
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------


def sweep(args) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    out_dir = Path(args.out)
    shots_dir = out_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    ignores = compile_ignores(args.ignore_console or [], not args.no_default_ignores)
    net_ignores = compile_ignores(args.ignore_network or [], False)
    viewports = [parse_viewport(v) for v in (args.viewport or DEFAULT_VIEWPORTS)]
    flow_steps: list[dict] = []
    if args.flow:
        flow_steps = json.loads(Path(args.flow).read_text())
        if isinstance(flow_steps, dict):
            flow_steps = flow_steps.get("steps", [])

    budgets = dict(DEFAULT_BUDGETS)
    for key in budgets:
        override = getattr(args, f"budget_{key.replace('_ms', '').replace('.', '')}", None)
        if override is not None:
            budgets[key] = override

    results: list[ViewportResult] = []

    with sync_playwright() as pw:
        launch_kwargs: dict[str, Any] = {"headless": not args.headed}
        if args.executable_path:
            launch_kwargs["executable_path"] = args.executable_path
        browser = pw.chromium.launch(**launch_kwargs)

        for name, width, height in viewports:
            vr = ViewportResult(name=name, width=width, height=height)
            ctx_kwargs: dict[str, Any] = {
                "viewport": {"width": width, "height": height},
                "device_scale_factor": 2 if width < 900 else 1,
                "is_mobile": width < 700,
                "has_touch": width < 700,
                "ignore_https_errors": True,
            }
            if args.storage_state and Path(args.storage_state).exists():
                ctx_kwargs["storage_state"] = args.storage_state
            if args.user_agent:
                ctx_kwargs["user_agent"] = args.user_agent
            context = browser.new_context(**ctx_kwargs)
            if args.header:
                context.set_extra_http_headers(
                    dict(h.split(":", 1) for h in args.header)  # type: ignore[arg-type]
                )
            page = context.new_page()

            page.on(
                "console",
                lambda msg, vr=vr: vr.console.append(
                    {
                        "type": msg.type,
                        "text": msg.text,
                        "location": f"{msg.location.get('url','')}:{msg.location.get('lineNumber','')}",
                    }
                ),
            )
            page.on("pageerror", lambda err, vr=vr: vr.page_errors.append(str(err)))
            page.on(
                "requestfailed",
                lambda req, vr=vr: vr.network.append(
                    {
                        "kind": "requestfailed",
                        "url": req.url,
                        "method": req.method,
                        "error": req.failure or "",
                    }
                ),
            )
            page.on(
                "response",
                lambda res, vr=vr: (
                    vr.network.append(
                        {
                            "kind": "http",
                            "url": res.url,
                            "method": res.request.method,
                            "status": res.status,
                        }
                    )
                    if res.status >= 400
                    else None
                ),
            )

            try:
                resp = page.goto(args.url, wait_until=args.wait_until, timeout=args.timeout)
                if resp is not None and resp.status >= 400:
                    vr.findings.append(
                        Finding("error", "navigation", f"[{name}] {args.url} returned HTTP {resp.status}")
                    )
                if args.wait_selector:
                    page.wait_for_selector(args.wait_selector, timeout=args.timeout)
                page.wait_for_timeout(args.settle)
            except Exception as exc:  # noqa: BLE001
                vr.findings.append(
                    Finding("error", "navigation", f"[{name}] could not load {args.url}", str(exc))
                )
                results.append(vr)
                context.close()
                continue

            # Vitals
            try:
                vr.vitals = page.evaluate(VITALS_JS)
            except Exception as exc:  # noqa: BLE001
                vr.vitals = {"error": str(exc)}

            # Baseline (pre-interaction) screenshot
            base_shot = shots_dir / f"{name}-01-initial.png"
            page.screenshot(path=str(base_shot), full_page=args.full_page)
            vr.screenshots.append(base_shot.name)

            # Flow
            if flow_steps:
                vr.flow, flow_findings = run_flow(page, flow_steps, shots_dir, name)
                vr.findings.extend(flow_findings)
                final_shot = shots_dir / f"{name}-99-final.png"
                page.screenshot(path=str(final_shot), full_page=args.full_page)
                vr.screenshots.append(final_shot.name)

            # Accessibility
            if args.a11y:
                vr.a11y = run_axe(page, args.a11y_tags, args.axe_path)
                if vr.a11y.get("status") != "ok":
                    # Silently skipping would leave a coverage gap the operator
                    # cannot see, so surface it as an explicit warning.
                    vr.findings.append(
                        Finding(
                            "warning",
                            "a11y",
                            f"[{name}] accessibility scan did not run",
                            f"{vr.a11y.get('reason', 'unknown')} — pass --axe-path with a local "
                            "axe.min.js, or verify accessibility manually.",
                        )
                    )
                for v in vr.a11y.get("violations", []):
                    sev = "error" if v["impact"] in ("critical", "serious") else "warning"
                    vr.findings.append(
                        Finding(
                            sev,
                            "a11y",
                            f"[{name}] {v['id']} ({v['impact']}): {v['help']}",
                            "; ".join(v["targets"][:3]),
                        )
                    )

            # Pixel diff
            if args.baseline:
                bl = Path(args.baseline) / "screenshots" / base_shot.name
                vr.diff = pixel_diff(bl, base_shot, shots_dir / f"{name}-diff.png")
                pct = vr.diff.get("changed_pct")
                if pct is not None and pct > args.diff_threshold:
                    vr.findings.append(
                        Finding(
                            "warning",
                            "visual-diff",
                            f"[{name}] {pct}% of pixels changed vs baseline",
                            "Confirm every changed region is intended.",
                        )
                    )

            # Console triage
            for msg in vr.console:
                if ignored(msg["text"], ignores) or ignored(msg["location"], ignores):
                    continue
                if msg["type"] == "error":
                    vr.findings.append(
                        Finding("error", "console", f"[{name}] console error", msg["text"][:400])
                    )
                elif msg["type"] == "warning":
                    vr.findings.append(
                        Finding("warning", "console", f"[{name}] console warning", msg["text"][:400])
                    )
            for err in vr.page_errors:
                if not ignored(err, ignores):
                    vr.findings.append(
                        Finding("error", "exception", f"[{name}] uncaught exception", err[:400])
                    )

            # Network triage
            for item in vr.network:
                if ignored(item["url"], net_ignores):
                    continue
                if item["kind"] == "requestfailed":
                    vr.findings.append(
                        Finding("error", "network", f"[{name}] request failed", f"{item['url']} — {item['error']}")
                    )
                else:
                    sev = "error" if item["status"] >= 500 or item["status"] == 404 else "warning"
                    vr.findings.append(
                        Finding(sev, "network", f"[{name}] HTTP {item['status']}", item["url"])
                    )

            # Budgets — only meaningful against a production build
            if not args.skip_budgets and isinstance(vr.vitals, dict):
                check_budgets(vr, budgets, args.dev_build)

            results.append(vr)
            context.close()

        browser.close()

    return build_report(args, results, budgets)


def run_axe(page, tags: str | None, axe_path: str | None = None) -> dict[str, Any]:
    # Prefer a local copy: it works offline, in locked-down CI, and pins the
    # ruleset so results do not drift between runs.
    try:
        if axe_path and Path(axe_path).exists():
            page.add_script_tag(content=Path(axe_path).read_text())
        else:
            page.add_script_tag(url=AXE_CDN)
        page.wait_for_function("() => !!window.axe", timeout=10000)
    except Exception as exc:  # noqa: BLE001
        return {"status": "skipped", "reason": f"axe-core unavailable ({str(exc)[:120]})"}
    tag_list = [t.strip() for t in (tags or "wcag2a,wcag2aa,wcag21a,wcag21aa").split(",")]
    try:
        raw = page.evaluate(
            """(tags) => axe.run(document, { runOnly: { type: 'tag', values: tags } })
                 .then(r => ({
                   violations: r.violations.map(v => ({
                     id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
                     targets: v.nodes.map(n => n.target.join(' ')).slice(0, 10),
                     count: v.nodes.length
                   })),
                   passes: r.passes.length
                 }))""",
            tag_list,
        )
        raw["status"] = "ok"
        return raw
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": str(exc)}


def check_budgets(vr: ViewportResult, budgets: dict[str, float], dev_build: bool) -> None:
    sev = "warning" if dev_build else "error"
    v = vr.vitals
    checks = [
        ("lcp_ms", "LCP", "ms"),
        ("cls", "CLS", ""),
        ("tbt_ms", "TBT", "ms"),
        ("ttfb_ms", "TTFB", "ms"),
    ]
    for key, label, unit in checks:
        actual = v.get(key)
        if actual is None:
            continue
        limit = budgets[key]
        if actual > limit:
            vr.findings.append(
                Finding(
                    sev,
                    "performance",
                    f"[{vr.name}] {label} {actual}{unit} exceeds budget {limit}{unit}",
                    "Dev-server timings are inflated — confirm on a production build."
                    if dev_build
                    else "",
                )
            )


def build_report(args, results: list[ViewportResult], budgets: dict[str, float]) -> dict[str, Any]:
    out_dir = Path(args.out)
    # A single broken asset can emit the same console line many times; collapse
    # exact duplicates so the findings list stays readable and actionable.
    seen: set[tuple] = set()
    all_findings = []
    for r in results:
        for f in r.findings:
            key = (f.severity, f.check, f.message, f.detail)
            if key in seen:
                continue
            seen.add(key)
            all_findings.append(f)
    errors = [f for f in all_findings if f.severity == "error"]
    warnings = [f for f in all_findings if f.severity == "warning"]
    passed = not errors and not (warnings and args.fail_on_warning)

    report = {
        "url": args.url,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": passed,
        "budgets": budgets,
        "summary": {
            "viewports": len(results),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "viewports": [asdict(r) for r in results],
        "findings": [asdict(f) for f in all_findings],
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "report.md").write_text(render_markdown(report, results))
    return report


def render_markdown(report: dict, results: list[ViewportResult]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"# UI verification — {status}",
        "",
        f"- **URL:** {report['url']}",
        f"- **Run:** {report['generated_at']}",
        f"- **Errors:** {report['summary']['errors']} | **Warnings:** {report['summary']['warnings']}",
        "",
        "## Viewports",
        "",
        "| Viewport | Size | LCP | CLS | TBT | Console errors | Net issues | Flow |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        v = r.vitals or {}
        cons = sum(1 for m in r.console if m["type"] == "error") + len(r.page_errors)
        flow_status = "—"
        if r.flow:
            failed = [s for s in r.flow if s["status"] == "failed"]
            flow_status = f"{len(r.flow) - len(failed)}/{len(r.flow)} ok"
        lines.append(
            f"| {r.name} | {r.width}x{r.height} | {v.get('lcp_ms', '—')}ms | {v.get('cls', '—')} "
            f"| {v.get('tbt_ms', '—')}ms | {cons} | {len(r.network)} | {flow_status} |"
        )

    lines += ["", "## Findings", ""]
    if not report["findings"]:
        lines.append("None. Every automated check passed.")
    for f in report["findings"]:
        icon = {"error": "FAIL", "warning": "WARN", "info": "INFO"}[f["severity"]]
        lines.append(f"- **{icon}** `{f['check']}` — {f['message']}" + (f"\n  - {f['detail']}" if f["detail"] else ""))

    lines += ["", "## Screenshots", ""]
    for r in results:
        for s in r.screenshots:
            lines.append(f"- `screenshots/{s}`")
        for s in r.flow:
            if s.get("screenshot"):
                lines.append(f"- `screenshots/{s['screenshot']}` ({s['name']})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Browser verification sweep for a frontend change.")
    p.add_argument("--url", required=True, help="URL of the page under test")
    p.add_argument("--out", default=".verify/run", help="Output directory (default: .verify/run)")
    p.add_argument("--viewport", action="append", help="name=WIDTHxHEIGHT (repeatable)")
    p.add_argument("--flow", help="JSON file describing interaction steps")
    p.add_argument("--wait-selector", help="Wait for this selector before measuring")
    p.add_argument("--wait-until", default="networkidle",
                   choices=["load", "domcontentloaded", "networkidle", "commit"])
    p.add_argument("--settle", type=int, default=1000, help="Extra settle time in ms after load")
    p.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in ms")
    p.add_argument("--full-page", action="store_true", help="Capture full-page screenshots")
    p.add_argument("--a11y", action="store_true", help="Run an axe-core WCAG scan")
    p.add_argument("--a11y-tags", help="Comma-separated axe tags (default wcag2a,wcag2aa,wcag21a,wcag21aa)")
    p.add_argument("--axe-path", default=os.environ.get("AXE_CORE_PATH"),
                   help="Local axe.min.js to inject instead of the CDN (offline/CI safe)")
    p.add_argument("--baseline", help="Previous run directory to pixel-diff against")
    p.add_argument("--diff-threshold", type=float, default=0.5, help="Percent of pixels allowed to change")
    p.add_argument("--storage-state", help="Playwright storage_state.json for authenticated pages")
    p.add_argument("--user-agent", help="Override the user agent")
    p.add_argument("--header", action="append", help="Extra HTTP header 'Name: value' (repeatable)")
    p.add_argument("--ignore-console", action="append", help="Regex of console text to ignore (repeatable)")
    p.add_argument("--ignore-network", action="append", help="Regex of URLs to ignore (repeatable)")
    p.add_argument("--no-default-ignores", action="store_true", help="Do not ignore common dev-tool noise")
    p.add_argument("--fail-on-warning", action="store_true", help="Treat warnings as failures")
    p.add_argument("--dev-build", action="store_true",
                   help="Target is a dev server: report budget misses as warnings, not errors")
    p.add_argument("--skip-budgets", action="store_true", help="Do not enforce performance budgets")
    p.add_argument("--budget-lcp", dest="budget_lcp", type=float, help="LCP budget in ms")
    p.add_argument("--budget-cls", dest="budget_cls", type=float, help="CLS budget")
    p.add_argument("--budget-tbt", dest="budget_tbt", type=float, help="TBT budget in ms")
    p.add_argument("--budget-ttfb", dest="budget_ttfb", type=float, help="TTFB budget in ms")
    p.add_argument("--headed", action="store_true", help="Run with a visible browser window")
    p.add_argument("--executable-path", default=os.environ.get("PLAYWRIGHT_CHROMIUM_PATH"),
                   help="Explicit Chromium binary path")
    p.add_argument("--quiet", action="store_true", help="Only print the one-line verdict")
    args = p.parse_args()

    try:
        report = sweep(args)
    except ModuleNotFoundError:
        print("ERROR: playwright is not installed.\n"
              "  pip install playwright && playwright install chromium", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: verification sweep crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    if not args.quiet:
        print((out / "report.md").read_text())
    verdict = "PASS" if report["passed"] else "FAIL"
    print(f"{verdict}: {report['summary']['errors']} error(s), "
          f"{report['summary']['warnings']} warning(s) — {out / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
