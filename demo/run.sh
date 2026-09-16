#!/usr/bin/env bash
# =====================================================================
# Composable CDP demo — end-to-end runner
#
#   ./run.sh              full build
#   ./run.sh --from 50    resume from stage 50
#   ./run.sh --only 95    run one stage
#   ./run.sh --dry-run    render SQL, submit nothing
#
# Idempotent: every stage uses CREATE OR REPLACE. Safe to re-run.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${HERE}/config.env"
RENDER_DIR="${HERE}/.rendered"
STATE_DIR="${HERE}/.state"

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
info() { printf '  \033[36m→\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

FROM=0; ONLY=""; DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)    [[ $# -ge 2 ]] || die "Option --from requires a stage number"; FROM="$2"; shift 2 ;;
    --only)    [[ $# -ge 2 ]] || die "Option --only requires a stage number"; ONLY="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -f "${CONFIG}" ]] || die "No config.env. Run ./setup.sh first."
# `set -a` matters: envsubst is a separate process and only sees EXPORTED
# variables. A plain `source` makes these shell variables only, so every
# ${CDP_*} token renders as an empty string — and the failure is baffling,
# because run.sh's own banner prints the values correctly while the SQL that
# reaches BigQuery reads `CREATE SCHEMA \`.\`` with location ''.
set -a
# shellcheck disable=SC1090
source "${CONFIG}"
CDP_LOCATION_LOWER="$(echo "${CDP_LOCATION:-}" | tr '[:upper:]' '[:lower:]')"
set +a
[[ -n "${CDP_PROJECT:-}" ]] || die "CDP_PROJECT is empty. Re-run ./setup.sh."

mkdir -p "${RENDER_DIR}" "${STATE_DIR}"

# Every token a SQL file may reference. envsubst only substitutes these,
# so stray shell-looking text in SQL is left alone.
VARS='$CDP_PROJECT $CDP_LOCATION $CDP_LOCATION_LOWER $CDP_DS $CDP_DS_TRUTH $CDP_BUCKET
      $CDP_CONNECTION $CDP_CONNECTION_PATH $CDP_EMBEDDING_ENDPOINT
      $CDP_EXTRACTION_MODEL $CDP_ADJUDICATOR_MODEL $CDP_PROMPT_VERSION
      $CDP_TOPK $CDP_TAU_HI
      $CDP_TAU_LO $CDP_TAU_LOW_IDENTITY $CDP_TAU_SINGLE_SIGNAL
      $CDP_MIN_NAME_SIMILARITY
      $CDP_ACCEPT_CONFIDENCE $CDP_STEWARD_CONFIDENCE
      $CDP_GREYZONE_CAP $CDP_SEED $CDP_MAX_BLOCK_SIZE
      $CDP_PEOPLE $CDP_RECORDS
      $CDP_TARGET_RECORDS $CDP_TARGET_PEOPLE $CDP_REBUILDS_PER_MONTH
      $CDP_PRICE_EMBED_INPUT $CDP_PRICE_EXTRACT_INPUT $CDP_PRICE_EXTRACT_OUTPUT
      $CDP_PRICE_ADJUDICATE_INPUT $CDP_PRICE_ADJUDICATE_OUTPUT
      $CDP_PRICE_BQ_PER_TIB $CDP_PRICE_BQ_SLOT_HOUR
      $CDP_PRICE_STORAGE_GIB_MONTH'

run_sql() {
  local f="$1"
  local base; base="$(basename "${f}" .sql)"
  local rendered="${RENDER_DIR}/${base}.sql"

  envsubst "${VARS}" < "${f}" > "${rendered}"

  # Fail loudly rather than letting an unrendered token reach BigQuery,
  # where it produces a baffling syntax error hundreds of lines in.
  if grep -qE '\$\{?CDP_[A-Z_]+\}?' "${rendered}"; then
    warn "Unsubstituted tokens in ${base}:"
    grep -noE '\$\{?CDP_[A-Z_]+\}?' "${rendered}" | sort -u -t: -k2 | head
    die "Add the missing variable to config.env and VARS in run.sh."
  fi

  if [[ "${DRY}" == "1" ]]; then
    ok "rendered ${base}.sql (dry run, not submitted)"
    return
  fi

  local start; start=$(date +%s)
  info "${base} ..."

  if ! bq query \
        --project_id="${CDP_PROJECT}" \
        --location="${CDP_LOCATION}" \
        --use_legacy_sql=false \
        --format=none \
        --quiet \
        < "${rendered}"; then
    die "${base} failed. Rendered SQL: ${rendered}"
  fi

  local elapsed=$(( $(date +%s) - start ))
  ok "${base} (${elapsed}s)"
  echo "${base}" >> "${STATE_DIR}/completed"
}

stage_num() { basename "$1" | grep -oE '^[0-9]+' ; }

should_run() {
  local n; n="$(stage_num "$1")"
  [[ -n "${ONLY}" ]] && { (( 10#${n} == 10#${ONLY} )) && return 0 || return 1; }
  (( 10#${n} >= 10#${FROM} ))
}

# ---------------------------------------------------------------------
# Verify what BigQuery actually loaded against what the generator says it
# wrote. A silently short CSV load is the single most demoralising way to
# lose an afternoon: everything downstream succeeds, the numbers are just
# quietly wrong.
# ---------------------------------------------------------------------
validate_landing() {
  [[ -f "${HERE}/data/manifest.json" ]] || { warn "No manifest.json — skipping row count check"; return 0; }

  info "verifying loaded row counts against manifest"

  local actual
  actual="$(bq query \
      --project_id="${CDP_PROJECT}" \
      --location="${CDP_LOCATION}" \
      --use_legacy_sql=false \
      --format=csv \
      --quiet \
      "SELECT 'crm_customers.csv'              AS f, COUNT(*) AS n FROM \`${CDP_PROJECT}.${CDP_DS}.src_crm_customers\`
       UNION ALL SELECT 'ecom_accounts.csv',              COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.src_ecom_accounts\`
       UNION ALL SELECT 'loyalty_members.csv',            COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.src_loyalty_members\`
       UNION ALL SELECT 'consent_events.csv',             COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.src_consent_events\`
       UNION ALL SELECT 'pos_transactions.csv',           COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.ext_pos_transactions\`
       UNION ALL SELECT 'support_tickets.parquet',        COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.ext_support_tickets\`
       UNION ALL SELECT 'third_party_enrich.jsonl',       COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.ext_third_party_enrich\`
       UNION ALL SELECT 'call_transcripts_manifest.csv',  COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.ext_call_manifest\`
       UNION ALL SELECT 'call_transcripts/*.txt',         COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS}.obj_call_transcripts\`
       UNION ALL SELECT 'truth/person_truth.csv',         COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth\`
       UNION ALL SELECT 'truth/case_catalogue.csv',       COUNT(*) FROM \`${CDP_PROJECT}.${CDP_DS_TRUTH}.case_catalogue\`")" \
    || die "Row count query failed. Did stage 10 succeed?"

  MANIFEST="${HERE}/data/manifest.json" ACTUAL="${actual}" python3 - <<'PY' || die "Row counts do not match the manifest. The load is incomplete or the contract has drifted."
import json, os, sys, csv, io

expected = json.load(open(os.environ['MANIFEST']))['row_counts']
rows = list(csv.reader(io.StringIO(os.environ['ACTUAL'])))[1:]

bad = []
for name, n in rows:
    want = expected.get(name)
    if want is None:
        continue
    if int(n) != int(want):
        bad.append(f'  {name}: manifest {want}, BigQuery {n}')

if bad:
    print('  Row count mismatch:')
    print('\n'.join(bad))
    sys.exit(1)
print(f'  all {len(rows)} sources match the manifest')
PY

  ok "row counts verified"
}

# ---------------------------------------------------------------------
# BigQuery requires a generated embedding column to be asynchronous, so
# the vectors in party_search are still being written by a background job
# when stage 30 returns.
#
# Stage 35 builds party_vectors with WHERE match_embedding.result IS NOT
# NULL. Start it early and you get an EMPTY table and no error at all —
# every later stage then succeeds with the wrong numbers. SQL has no
# SLEEP, so the wait lives here.
# ---------------------------------------------------------------------
wait_for_embeddings() {
  local deadline=$(( $(date +%s) + 1800 ))   # 30 minutes
  local last=""

  info "waiting for background embedding generation"

  while :; do
    local row
    row="$(bq query \
        --project_id="${CDP_PROJECT}" \
        --location="${CDP_LOCATION}" \
        --use_legacy_sql=false \
        --format=csv \
        --quiet \
        "SELECT IFNULL(SUM(missing),0), IFNULL(SUM(embedded),0), IFNULL(SUM(errored),0)
         FROM \`${CDP_PROJECT}.${CDP_DS}.v_embedding_health\`" 2>/dev/null | tail -1)" \
      || die "Could not read v_embedding_health. Did stage 30 succeed?"

    local missing embedded errored
    IFS=, read -r missing embedded errored <<< "${row}"

    # Partial failure is the dangerous case: quota pressure embeds most
    # rows and drops the rest, and a silently unembedded record is a
    # silently unmatched customer.
    if [[ "${errored:-0}" -gt 0 ]]; then
      die "${errored} row(s) carry an embedding error. Read v_embedding_health.sample_error — usually quota pressure."
    fi

    if [[ "${missing:-1}" -eq 0 && "${embedded:-0}" -gt 0 ]]; then
      ok "all ${embedded} rows embedded"
      return 0
    fi

    if [[ "$(date +%s)" -ge "${deadline}" ]]; then
      die "Embeddings still incomplete after 30 minutes (${missing} missing). Check v_embedding_health."
    fi

    if [[ "${missing}" != "${last}" ]]; then
      info "  ${embedded} embedded, ${missing} remaining"
      last="${missing}"
    fi
    sleep 20
  done
}

# ---------------------------------------------------------------------
bold "Composable CDP demo"
echo "  project   ${CDP_PROJECT}"
echo "  location  ${CDP_LOCATION}"
echo "  datasets  ${CDP_DS} (working) · ${CDP_DS_TRUTH} (ground truth, never read by pipeline)"
echo "  bucket    gs://${CDP_BUCKET}"
echo "  corpus    ${CDP_PEOPLE} people / ${CDP_RECORDS} records · seed ${CDP_SEED}"
[[ "${DRY}" == "1" ]] && warn "DRY RUN — rendering only"

[[ -z "${ONLY}" && "${FROM}" -eq 0 ]] && : > "${STATE_DIR}/completed"
RUN_START=$(date +%s)

# ---------------------------------------------------------------------
bold "1. Generate synthetic data"
# ---------------------------------------------------------------------
if [[ -z "${ONLY}" && "${FROM}" -le 10 ]]; then
  if [[ -f "${HERE}/data/manifest.json" ]]; then
    ok "data present — delete demo/data to regenerate"
  else
    # The generator writes support_tickets.parquet, so it needs pyarrow.
    # Prefer the project venv. Fall back to python3 only if that interpreter
    # can actually import pyarrow — otherwise fail here with an actionable
    # message rather than part-way through a 200k write.
    GEN_PY="${HERE}/generate/.venv/bin/python"
    if [[ ! -x "${GEN_PY}" ]]; then
      GEN_PY="python3"
      "${GEN_PY}" -c 'import pyarrow' 2>/dev/null || die \
        "No generate/.venv, and python3 cannot import pyarrow. Create it with: uv venv ${HERE}/generate/.venv && uv pip install --python ${HERE}/generate/.venv/bin/python -r ${HERE}/generate/requirements.txt"
    fi
    "${GEN_PY}" "${HERE}/generate/generate.py" \
      --seed "${CDP_SEED}" \
      --people "${CDP_PEOPLE}" \
      --records "${CDP_RECORDS}" \
      --out "${HERE}/data"
    ok "generated"
  fi

  if [[ "${DRY}" != "1" ]]; then
    bold "2. Upload sources to GCS"
    # `gcloud storage`, not `gsutil`: gsutil writes a lock file into
    # ~/.gsutil and dies with "Read-only file system" wherever HOME is not
    # writable, which kills the run before a single stage executes. gcloud
    # storage honours CLOUDSDK_CONFIG, is parallel by default (so -m is
    # unnecessary), and is the supported successor.
    # Everything goes to GCS, including the files destined for managed
    # tables: 10_land_sources.sql uses LOAD DATA ... FROM FILES so that the
    # whole landing step is expressible in SQL rather than split between
    # bash and SQL. The layout below is load-bearing — the URIs are
    # hardcoded in 10_land_sources.sql.
    gcloud storage cp \
      "${HERE}/data/crm_customers.csv" \
      "${HERE}/data/ecom_accounts.csv" \
      "${HERE}/data/loyalty_members.csv" \
      "${HERE}/data/consent_events.csv" \
      "${HERE}/data/call_transcripts_manifest.csv" \
      "gs://${CDP_BUCKET}/raw/"
    gcloud storage cp "${HERE}/data/pos_transactions.csv"     "gs://${CDP_BUCKET}/pos/"
    gcloud storage cp "${HERE}/data/support_tickets.parquet"  "gs://${CDP_BUCKET}/support/"
    gcloud storage cp "${HERE}/data/third_party_enrich.jsonl" "gs://${CDP_BUCKET}/enrich/"
    # Clear the prefix first. Transcript filenames are content-hashed, so a
    # regenerated corpus writes NEW names rather than overwriting the old
    # ones -- the object table then counts both and every downstream number
    # is quietly computed over two corpora at once. Observed: 442 local
    # files, 875 in the bucket. The row-count check below does catch it, but
    # only after stage 10 has already run.
    gcloud storage rm --recursive "gs://${CDP_BUCKET}/call_transcripts" \
      >/dev/null 2>&1 || true
    gcloud storage cp -r "${HERE}/data/call_transcripts"      "gs://${CDP_BUCKET}/"
    gcloud storage cp \
      "${HERE}/data/truth/person_truth.csv" \
      "${HERE}/data/truth/case_catalogue.csv" \
      "gs://${CDP_BUCKET}/truth/"
    ok "uploaded"
  fi
fi

# ---------------------------------------------------------------------
bold "3. Pipeline"
# ---------------------------------------------------------------------
shopt -s nullglob
for f in "${HERE}"/sql/[0-9]*.sql; do
  should_run "${f}" || continue
  run_sql "${f}"
  # Checked here rather than at the end: everything downstream succeeds on
  # a short load, it just succeeds with the wrong numbers.
  [[ "$(stage_num "${f}")" == "10" && "${DRY}" != "1" ]] && validate_landing
  # Same reasoning as the row-count check above: stage 35 would otherwise
  # succeed against a half-written embedding column and be quietly wrong.
  [[ "$(stage_num "${f}")" == "30" && "${DRY}" != "1" ]] && wait_for_embeddings
done

# ---------------------------------------------------------------------
bold "Done"
# ---------------------------------------------------------------------
echo "  wall clock  $(( $(date +%s) - RUN_START ))s"
echo
echo "  The scorecard is the point. Read it:"
echo "    bq query --project_id=${CDP_PROJECT} --location=${CDP_LOCATION} --use_legacy_sql=false \\"
echo "      'SELECT * FROM \`${CDP_PROJECT}.${CDP_DS}.v_scorecard\`'"
echo
echo "  Then the honest one — which hard cases failed:"
echo "    bq query --project_id=${CDP_PROJECT} --location=${CDP_LOCATION} --use_legacy_sql=false \\"
echo "      'SELECT * FROM \`${CDP_PROJECT}.${CDP_DS}.v_case_results\` ORDER BY passed, case_type'"
echo
echo "  What it cost, measured — and what it would cost at ${CDP_TARGET_RECORDS} records:"
echo "    bq query --project_id=${CDP_PROJECT} --location=${CDP_LOCATION} --use_legacy_sql=false \\"
echo "      'SELECT * FROM \`${CDP_PROJECT}.${CDP_DS}.v_cost_model\`'"
echo "    (add BigQuery compute from v_cost_compute — the model cost excludes it)"
echo
echo "  Scenarios: ./scenarios/run_scenario.sh {A|B|C|D|E}"
echo "    A stability · B retrieval legs · C consent · D contradiction · E real-time"
echo
