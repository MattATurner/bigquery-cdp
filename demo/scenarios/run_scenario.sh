#!/usr/bin/env bash
# =====================================================================
# Scenario runner
#
#   ./scenarios/run_scenario.sh A
#
# Each scenario is one focused question with one query to answer it.
# They are read-only unless the header of the scenario says otherwise,
# so they are safe to run live, repeatedly, in front of an audience.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${HERE}/../config.env"

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

[[ -f "${CONFIG}" ]] || die "No config.env. Run ./setup.sh first."
# `set -a` matters: envsubst is a separate process and only sees EXPORTED
# variables. Without it every ${CDP_*} token renders as an empty string.
set -a
# shellcheck disable=SC1090
source "${CONFIG}"
CDP_LOCATION_LOWER="$(echo "${CDP_LOCATION:-}" | tr '[:upper:]' '[:lower:]')"
set +a

SCENARIO="${1:-}"
[[ -n "${SCENARIO}" ]] || die "Usage: run_scenario.sh {A|B|C|D|E}"

FILE="${HERE}/scenario_${SCENARIO}.sql"
[[ -f "${FILE}" ]] || die "No such scenario: ${SCENARIO} (expected ${FILE})"

VARS='$CDP_PROJECT $CDP_LOCATION $CDP_LOCATION_LOWER $CDP_DS $CDP_DS_TRUTH $CDP_BUCKET
      $CDP_CONNECTION $CDP_CONNECTION_PATH $CDP_EMBEDDING_ENDPOINT
      $CDP_EXTRACTION_MODEL $CDP_ADJUDICATOR_MODEL $CDP_PROMPT_VERSION
      $CDP_TOPK $CDP_TAU_HI $CDP_TAU_LO
      $CDP_TAU_LOW_IDENTITY $CDP_TAU_SINGLE_SIGNAL $CDP_MIN_NAME_SIMILARITY
      $CDP_ACCEPT_CONFIDENCE $CDP_STEWARD_CONFIDENCE
      $CDP_GREYZONE_CAP $CDP_SEED
      $CDP_MAX_BLOCK_SIZE $CDP_PEOPLE $CDP_RECORDS
      $CDP_TARGET_RECORDS $CDP_TARGET_PEOPLE $CDP_REBUILDS_PER_MONTH
      $CDP_PRICE_EMBED_INPUT $CDP_PRICE_EXTRACT_INPUT $CDP_PRICE_EXTRACT_OUTPUT
      $CDP_PRICE_ADJUDICATE_INPUT $CDP_PRICE_ADJUDICATE_OUTPUT
      $CDP_PRICE_BQ_PER_TIB $CDP_PRICE_BQ_SLOT_HOUR
      $CDP_PRICE_STORAGE_GIB_MONTH'

RENDERED="$(mktemp)"
trap 'rm -f "${RENDERED}"' EXIT
envsubst "${VARS}" < "${FILE}" > "${RENDERED}"

if grep -qE '\$\{?CDP_[A-Z_]+\}?' "${RENDERED}"; then
  die "Unsubstituted tokens in scenario ${SCENARIO}. Check config.env and VARS."
fi

# The narration lives in the SQL header, so the story and the query can
# never drift apart.
bold "Scenario ${SCENARIO}"
sed -n '/^-- ===/,/^-- ===/p' "${FILE}" | sed 's/^-- \{0,1\}//' | sed '/^===/d'

bq query \
  --project_id="${CDP_PROJECT}" \
  --location="${CDP_LOCATION}" \
  --use_legacy_sql=false \
  --format=pretty \
  < "${RENDERED}"
