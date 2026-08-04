#!/usr/bin/env bash
# Smoke test: the gate must PASS a clean page and FAIL a broken one.
# A verifier that never fails is worse than no verifier at all, so both
# directions are asserted.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SMOKE_PORT:-8912}"
OUT="$(mktemp -d)"
AXE="$ROOT/node_modules/axe-core/axe.min.js"
A11Y_ARGS=(--a11y)
[ -f "$AXE" ] && A11Y_ARGS+=(--axe-path "$AXE")

python3 -m http.server "$PORT" --directory "$ROOT/tests/fixtures" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null; rm -rf "$OUT"' EXIT

for _ in $(seq 1 30); do
  curl -sf -m 1 "http://localhost:$PORT/clean.html" >/dev/null && break
  sleep 0.5
done

fail=0

echo "==> clean.html should PASS"
python3 "$ROOT/scripts/verify_ui.py" \
  --url "http://localhost:$PORT/clean.html" \
  --flow "$ROOT/tests/flows/clean.json" \
  --out "$OUT/clean" --dev-build --quiet "${A11Y_ARGS[@]}"
if [ $? -eq 0 ]; then echo "    PASS (exit 0 as expected)"; else echo "    FAIL: clean fixture did not pass"; fail=1; fi

echo "==> broken.html should FAIL"
python3 "$ROOT/scripts/verify_ui.py" \
  --url "http://localhost:$PORT/broken.html" \
  --out "$OUT/broken" --dev-build --quiet "${A11Y_ARGS[@]}"
if [ $? -ne 0 ]; then echo "    PASS (non-zero exit as expected)"; else echo "    FAIL: broken fixture was not caught"; fail=1; fi

echo "==> broken.html findings must name the real defects"
python3 - "$OUT/broken/report.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
blob = json.dumps(report["findings"]).lower()
expected = {
    "404 on a missing asset": "404",
    "uncaught exception": "deliberate test failure",
}
missing = [label for label, needle in expected.items() if needle not in blob]
if missing:
    print("    FAIL: not detected -> " + ", ".join(missing))
    sys.exit(1)
print(f"    PASS ({report['summary']['errors']} errors, {report['summary']['warnings']} warnings detected)")
PY
[ $? -ne 0 ] && fail=1

echo
if [ "$fail" -eq 0 ]; then echo "smoke test: OK"; else echo "smoke test: FAILED"; fi
exit "$fail"
