#!/usr/bin/env bash
# Run the generator verification checks in order. Exits non-zero on the first
# failure. No GCP: nothing here calls bq, gcloud or gsutil, and no SQL runs.
#
#   bash demo/generate/checks/run_all.sh          # static checks only
#   bash demo/generate/checks/run_all.sh --full   # + corpus-dependent checks
#
# The default set needs only demo/generate/ to be importable. --full also
# needs a generated corpus in demo/data/ and pyarrow installed.
#
# compare_runs.py is deliberately NOT in either set: it needs two output
# directories to compare. Run it explicitly:
#
#   python3 demo/generate/checks/compare_runs.py RUN_A RUN_B
#
# Read README.md before trusting a green run. Several of these checks report
# how many items they examined, and a zero over a small sample is not a pass.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --full re-runs the generator, which writes Parquet and so needs pyarrow.
# Prefer the project venv over a bare python3, which usually does not have it:
# the failure otherwise surfaces deep inside a check as a ModuleNotFoundError
# and reads like a broken check rather than a missing dependency.
# Override with PYTHON=... if you keep your interpreter elsewhere.
PY="${PYTHON:-}"
if [[ -z "${PY}" ]]; then
  if [[ -x "${HERE}/../.venv/bin/python" ]]; then
    PY="${HERE}/../.venv/bin/python"
  else
    PY="python3"
  fi
fi

FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

run() {
  local label="$1"; shift
  echo
  echo "=============================================================="
  echo "== ${label}"
  echo "=============================================================="
  if ! "$@"; then
    echo
    echo "FAILED: ${label}" >&2
    echo "Command: $*" >&2
    exit 1
  fi
}

# --- static: no corpus required -------------------------------------------
run "parse check (all scripts)" \
    "$PY" -c '
import ast, pathlib, sys
here = pathlib.Path(sys.argv[1])
bad = 0
for f in sorted(here.glob("*.py")):
    try:
        ast.parse(f.read_text(encoding="utf-8"))
        print(f"  ok    {f.name}")
    except SyntaxError as exc:
        print(f"  PARSE {f.name}: {exc}")
        bad += 1
sys.exit(1 if bad else 0)
' "$HERE"

run "preflight SQL structure" \
    "$PY" "$HERE/check_preflight.py"

run "CONFUSABLE_FORENAMES vs group pools" \
    "$PY" "$HERE/check_confusables.py"

run "risk-bank tags vs prose (+ negative control)" \
    "$PY" "$HERE/check_body_tags.py"

run "NOTABLE_FULL_NAMES roster audit (reachability)" \
    "$PY" "$HERE/notable_full_names.py"

run "emission-time name guard (deterministic unit tests)" \
    "$PY" "$HERE/check_emitted_sweep.py" --skip-end-to-end

if [ "$FULL" -eq 0 ]; then
  echo
  echo "=============================================================="
  echo "STATIC CHECKS PASSED."
  echo
  echo "NOT RUN (need a generated corpus in demo/data):"
  echo "  check_corpus.py"
  echo "  check_holder_gender.py  (and its --negative-control run)"
  echo "  verify_corpus_fixes.py"
  echo "  check_emitted_sweep.py  end-to-end section"
  echo "Re-run with --full once the corpus exists."
  echo "NOT RUN (needs two output dirs): compare_runs.py"
  echo "=============================================================="
  exit 0
fi

# --- full: corpus required -------------------------------------------------
run "emission-time name guard (end-to-end)" \
    "$PY" "$HERE/check_emitted_sweep.py"

run "corpus sweep" \
    "$PY" "$HERE/check_corpus.py"

run "ticket prose regressions (+ detector self-test)" \
    "$PY" "$HERE/verify_corpus_fixes.py"

run "holder gender end-to-end" \
    "$PY" "$HERE/check_holder_gender.py"

run "holder gender NEGATIVE CONTROL (must detect N/N)" \
    "$PY" "$HERE/check_holder_gender.py" --negative-control

echo
echo "=============================================================="
echo "ALL CHECKS PASSED."
echo
echo "Still not proven by any of the above:"
echo "  * no SQL has ever executed against BigQuery"
echo "  * determinism -- run compare_runs.py over two SERIAL generations"
echo "=============================================================="
