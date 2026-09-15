#!/usr/bin/env bash
# =====================================================================
# Composable CDP demo — interactive setup
#
# Prompts for every environment value, validates the target project,
# and writes config.env (git-ignored). Safe to re-run: existing values
# become the offered defaults.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${HERE}/config.env"

bold()  { printf '\033[1m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
die()   { fail "$1"; exit 1; }

# Load existing config so re-runs offer current values as defaults.
if [[ -f "${CONFIG}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG}"
  bold "Existing config found — press enter to keep each current value."
  echo
fi

ask() {
  # ask VAR "Prompt text" "fallback default"
  local var="$1" prompt="$2" fallback="${3:-}"
  local current="${!var:-}"
  local default="${current:-$fallback}"
  local reply
  if [[ -n "${default}" ]]; then
    read -r -p "  ${prompt} [${default}]: " reply
    reply="${reply:-$default}"
  else
    read -r -p "  ${prompt}: " reply
  fi
  printf -v "${var}" '%s' "${reply}"
}

# ---------------------------------------------------------------------
bold "1. Target environment"
# ---------------------------------------------------------------------
while :; do
  ask CDP_PROJECT "GCP project ID"
  [[ -n "${CDP_PROJECT}" ]] && break
  warn "Project ID is required."
done

ask CDP_LOCATION       "BigQuery location"          "EU"
ask CDP_DATASET_PREFIX "Dataset prefix"             "cdp"
ask CDP_BUCKET         "GCS bucket (no gs:// prefix)" "${CDP_PROJECT}-cdp-demo"
ask CDP_CONNECTION     "Vertex AI connection name"  "cdp-conn"

echo
# ---------------------------------------------------------------------
bold "2. Models"
# ---------------------------------------------------------------------
echo "  Model IDs move fast. The Gemini 2.5 family is scheduled for deprecation"
echo "  from 16 Oct 2026. Stage 05 preflights these before any data is touched,"
echo "  so a wrong ID fails in seconds rather than mid-pipeline."
echo
ask CDP_EMBEDDING_ENDPOINT  "Embedding endpoint"                 "gemini-embedding-001"
ask CDP_EXTRACTION_MODEL    "Entity-extraction model (high volume, cheap)" "gemini-3.5-flash-lite"
ask CDP_ADJUDICATOR_MODEL   "Adjudicator model (low volume, capable; pin it)" "gemini-3.5-flash"
ask CDP_PROMPT_VERSION      "Prompt version tag"                 "adjudicator-v2"

echo
# ---------------------------------------------------------------------
bold "3. Corpus and cost guardrails"
# ---------------------------------------------------------------------
echo "  200000 / 80000 is the presentation scale. Use 20000 / 8000 while"
echo "  debugging — same seed, same hard cases, roughly a tenth of the cost."
echo
ask CDP_PEOPLE         "Distinct people to generate"       "80000"
ask CDP_RECORDS        "Total source records"              "200000"
ask CDP_SEED           "Generator seed (reproducibility)"  "42"
ask CDP_GREYZONE_CAP   "Max pairs sent to the adjudicator" "50000"
ask CDP_TOPK           "Candidates retrieved per record"   "25"
ask CDP_MAX_BLOCK_SIZE "Discard blocking keys larger than" "2000"

echo
# ---------------------------------------------------------------------
bold "4. Matching thresholds"
# ---------------------------------------------------------------------
echo "  Precision is prioritised over recall: over-merging two real people is a"
echo "  privacy incident, under-merging is a data-quality ticket."
echo
ask CDP_TAU_HI             "Auto-match at or above"      "0.92"
ask CDP_TAU_LO             "Auto-reject at or below"     "0.72"
ask CDP_ACCEPT_CONFIDENCE  "Accept adjudicator verdict above" "0.85"
ask CDP_STEWARD_CONFIDENCE "Send to steward above"       "0.60"
ask CDP_TAU_LOW_IDENTITY   "Low-identity rail floor"     "0.15"
ask CDP_TAU_SINGLE_SIGNAL  "Single-signal rail floor"    "0.40"
ask CDP_MIN_NAME_SIMILARITY "Min name similarity (no-name-match pairs)" "0.70"

echo
# ---------------------------------------------------------------------
bold "5. Cost model"
# ---------------------------------------------------------------------
echo "  Stage 96 measures what the run actually consumed — real token counts"
echo "  from the models, real bytes billed by BigQuery — then extrapolates."
echo
echo "  The extrapolation target should be the CUSTOMER'S volume, not the"
echo "  demo's. That is what makes the output answer the question they ask."
echo
ask CDP_TARGET_RECORDS     "Extrapolate to how many source records" "15000000"
ask CDP_TARGET_PEOPLE      "...representing how many people"        "3000000"
ask CDP_REBUILDS_PER_MONTH "Full rebuilds per month in production"  "4"

echo
echo "  Unit prices are list prices captured 14 Sep 2026 and WILL go stale."
echo "  Press enter to accept, or override. Verify before quoting a customer."
echo
ask CDP_PRICE_EMBED_INPUT       "Embedding, USD / 1M input tokens"   "0.15"
ask CDP_PRICE_EXTRACT_INPUT     "Extraction, USD / 1M input tokens"  "0.30"
ask CDP_PRICE_EXTRACT_OUTPUT    "Extraction, USD / 1M output tokens" "2.50"
ask CDP_PRICE_ADJUDICATE_INPUT  "Adjudicator, USD / 1M input tokens" "1.50"
ask CDP_PRICE_ADJUDICATE_OUTPUT "Adjudicator, USD / 1M output tokens" "9.00"
ask CDP_PRICE_BQ_PER_TIB        "BigQuery on-demand, USD / TiB"      "6.25"
ask CDP_PRICE_BQ_SLOT_HOUR      "BigQuery Enterprise, USD / slot-hour" "0.06"
ask CDP_PRICE_STORAGE_GIB_MONTH "Storage, USD / GiB-month"           "0.02"

echo
# ---------------------------------------------------------------------
bold "6. Validating"
# ---------------------------------------------------------------------

command -v bq      >/dev/null 2>&1 || die "bq not found. Install the Google Cloud SDK."
command -v gcloud  >/dev/null 2>&1 || die "gcloud not found. Install the Google Cloud SDK."
command -v python3 >/dev/null 2>&1 || die "python3 not found."
ok "CLI tools present"

if gcloud projects describe "${CDP_PROJECT}" >/dev/null 2>&1; then
  ok "Project ${CDP_PROJECT} reachable"
else
  die "Cannot reach project ${CDP_PROJECT}. Check the ID and run: gcloud auth login"
fi

if gcloud services list --enabled --project "${CDP_PROJECT}" 2>/dev/null \
     | grep -q bigquery.googleapis.com; then
  ok "BigQuery API enabled"
else
  warn "BigQuery API may not be enabled. Enable with:"
  echo "      gcloud services enable bigquery.googleapis.com --project ${CDP_PROJECT}"
fi

# --- Bucket -----------------------------------------------------------
# `gcloud storage`, not `gsutil`: gsutil writes a lock file under ~/.gsutil and
# dies with "Read-only file system" wherever HOME is not writable, which kills
# setup before it reaches the connection step. gcloud storage honours
# CLOUDSDK_CONFIG and is the supported successor.
if gcloud storage buckets describe "gs://${CDP_BUCKET}" >/dev/null 2>&1; then
  BUCKET_LOC="$(gcloud storage buckets describe "gs://${CDP_BUCKET}" \
    --format='value(location)' 2>/dev/null \
    | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  if [[ -n "${BUCKET_LOC}" && "${BUCKET_LOC}" != "$(echo "${CDP_LOCATION}" | tr '[:lower:]' '[:upper:]')" ]]; then
    fail "Bucket is in ${BUCKET_LOC} but BigQuery location is ${CDP_LOCATION}."
    die  "External tables require both in the same location. Use a different bucket or location."
  fi
  ok "Bucket gs://${CDP_BUCKET} reachable and co-located"
else
  warn "Bucket gs://${CDP_BUCKET} does not exist."
  read -r -p "  Create it in ${CDP_LOCATION}? [Y/n]: " mk
  if [[ ! "${mk}" =~ ^[Nn]$ ]]; then
    gcloud storage buckets create "gs://${CDP_BUCKET}" \
      --project="${CDP_PROJECT}" --location="${CDP_LOCATION}" \
      && ok "Created gs://${CDP_BUCKET}"
  else
    die "A bucket is required for the external and object tables."
  fi
fi

# --- Vertex AI connection --------------------------------------------
CONN_PATH="${CDP_PROJECT}.${CDP_LOCATION}.${CDP_CONNECTION}"
if bq --project_id="${CDP_PROJECT}" show --connection --location="${CDP_LOCATION}" \
      "${CDP_CONNECTION}" >/dev/null 2>&1; then
  ok "Connection ${CONN_PATH} exists"
else
  warn "Connection ${CONN_PATH} not found."
  read -r -p "  Create it? [Y/n]: " mk
  if [[ ! "${mk}" =~ ^[Nn]$ ]]; then
    bq mk --connection --location="${CDP_LOCATION}" --project_id="${CDP_PROJECT}" \
          --connection_type=CLOUD_RESOURCE "${CDP_CONNECTION}" \
      && ok "Created ${CONN_PATH}"
  else
    die "The AI functions cannot run without a Vertex AI connection."
  fi
fi

# The connection's service account needs Vertex AI User. This is the single
# most common cause of a mid-run failure, so surface it explicitly.
CONN_SA="$(bq --project_id="${CDP_PROJECT}" show --format=prettyjson --connection \
             --location="${CDP_LOCATION}" "${CDP_CONNECTION}" 2>/dev/null \
           | python3 -c 'import sys,json;print(json.load(sys.stdin).get("cloudResource",{}).get("serviceAccountId",""))' 2>/dev/null || true)"

if [[ -n "${CONN_SA}" ]]; then
  ok "Connection service account: ${CONN_SA}"
  echo
  warn "That service account needs the Vertex AI User role. If you haven't granted it:"
  echo "      gcloud projects add-iam-policy-binding ${CDP_PROJECT} \\"
  echo "        --member=serviceAccount:${CONN_SA} \\"
  echo "        --role=roles/aiplatform.user"
  echo
  read -r -p "  Attempt to grant it now? [y/N]: " grant
  if [[ "${grant}" =~ ^[Yy]$ ]]; then
    gcloud projects add-iam-policy-binding "${CDP_PROJECT}" \
      --member="serviceAccount:${CONN_SA}" \
      --role="roles/aiplatform.user" >/dev/null 2>&1 \
      && ok "Granted" \
      || warn "Grant failed — you may lack permission. Ask an admin to run the command above."
  fi
else
  warn "Could not determine the connection's service account. Verify its IAM manually."
fi

# ---------------------------------------------------------------------
bold "7. Writing config.env"
# ---------------------------------------------------------------------
cat > "${CONFIG}" <<EOF
# Generated by setup.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Git-ignored. Re-run ./setup.sh to change any value.

CDP_PROJECT="${CDP_PROJECT}"
CDP_LOCATION="${CDP_LOCATION}"
CDP_DATASET_PREFIX="${CDP_DATASET_PREFIX}"
CDP_BUCKET="${CDP_BUCKET}"
CDP_CONNECTION="${CDP_CONNECTION}"

CDP_EMBEDDING_ENDPOINT="${CDP_EMBEDDING_ENDPOINT}"
CDP_EXTRACTION_MODEL="${CDP_EXTRACTION_MODEL}"
CDP_ADJUDICATOR_MODEL="${CDP_ADJUDICATOR_MODEL}"
CDP_PROMPT_VERSION="${CDP_PROMPT_VERSION}"

CDP_PEOPLE="${CDP_PEOPLE}"
CDP_RECORDS="${CDP_RECORDS}"
CDP_SEED="${CDP_SEED}"
CDP_GREYZONE_CAP="${CDP_GREYZONE_CAP}"
CDP_TOPK="${CDP_TOPK}"
CDP_MAX_BLOCK_SIZE="${CDP_MAX_BLOCK_SIZE}"

CDP_TAU_HI="${CDP_TAU_HI}"
CDP_TAU_LO="${CDP_TAU_LO}"
CDP_ACCEPT_CONFIDENCE="${CDP_ACCEPT_CONFIDENCE}"
CDP_STEWARD_CONFIDENCE="${CDP_STEWARD_CONFIDENCE}"
CDP_TAU_LOW_IDENTITY="${CDP_TAU_LOW_IDENTITY}"
CDP_TAU_SINGLE_SIGNAL="${CDP_TAU_SINGLE_SIGNAL}"
CDP_MIN_NAME_SIMILARITY="${CDP_MIN_NAME_SIMILARITY}"

# Cost model. Unit prices are list prices captured 14 Sep 2026 — re-verify
# before quoting. Targets are the customer's volume, not the demo's.
CDP_TARGET_RECORDS="${CDP_TARGET_RECORDS}"
CDP_TARGET_PEOPLE="${CDP_TARGET_PEOPLE}"
CDP_REBUILDS_PER_MONTH="${CDP_REBUILDS_PER_MONTH}"
CDP_PRICE_EMBED_INPUT="${CDP_PRICE_EMBED_INPUT}"
CDP_PRICE_EXTRACT_INPUT="${CDP_PRICE_EXTRACT_INPUT}"
CDP_PRICE_EXTRACT_OUTPUT="${CDP_PRICE_EXTRACT_OUTPUT}"
CDP_PRICE_ADJUDICATE_INPUT="${CDP_PRICE_ADJUDICATE_INPUT}"
CDP_PRICE_ADJUDICATE_OUTPUT="${CDP_PRICE_ADJUDICATE_OUTPUT}"
CDP_PRICE_BQ_PER_TIB="${CDP_PRICE_BQ_PER_TIB}"
CDP_PRICE_BQ_SLOT_HOUR="${CDP_PRICE_BQ_SLOT_HOUR}"
CDP_PRICE_STORAGE_GIB_MONTH="${CDP_PRICE_STORAGE_GIB_MONTH}"

# Derived — do not edit
CDP_DS="${CDP_DATASET_PREFIX}"
CDP_DS_TRUTH="${CDP_DATASET_PREFIX}_truth"
CDP_CONNECTION_PATH="${CDP_PROJECT}.${CDP_LOCATION}.${CDP_CONNECTION}"
EOF

chmod 600 "${CONFIG}"
ok "Wrote ${CONFIG}"

echo
bold "Ready."
echo "  Next:  ./run.sh"
echo
echo "  Cost:  this build has not been benchmarked, so no estimate is offered"
echo "         up front. Stage 96 measures what the run actually consumed and"
echo "         extrapolates to ${CDP_TARGET_RECORDS} records. Query"
echo "         v_cost_model afterwards for the real number."
echo "         If you want a cheap first pass, re-run setup.sh with"
echo "         20000 records / 8000 people."
echo
