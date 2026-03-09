#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ANALYSIS_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
WORKSPACE_ROOT=$(cd "${ANALYSIS_ROOT}/.." && pwd)

PARSER_ROOT=${PBP_PARSER_ROOT:-"${WORKSPACE_ROOT}/pbp-parser"}
YR_DATA_API_ROOT=${YR_DATA_API_ROOT:-"${WORKSPACE_ROOT}/yr-data-api"}

MODE="live-refresh"
SEASON=2025
LAST_N=3
BRIEF_FORMAT="markdown"
RUN_TESTS=0
STRICT_VERIFICATION=1
NO_ENRICHMENT=0
REUSE_BUNDLE=0

OUTPUT_DIR="${ANALYSIS_ROOT}/outputs/game_prep_brief"
SUMMARY_JSON=""
SCAN_DIR="${PARSER_ROOT}/data/statbroadcast_game_briefs"
BUNDLE_PATH=""
SNAPSHOT_PATH=""
VERIFICATION_REPORT_PATH=""
ENRICHMENT_FILE=""

TEAM1=""
TEAM2=""

usage() {
  cat <<'EOF'
Usage:
  ./scripts/refresh-game-prep-pipeline.sh <team1> <team2> [options]

Modes:
  --mode live-refresh        Regenerate bundle, CFBStats artifacts, enrichment, and smoke brief.
  --mode offline-validate    Rebuild the bundle locally, reuse pinned snapshot/report artifacts, and smoke brief offline.

Options:
  --season <year>                        Season year (default: 2025)
  --last-n <count>                       Last-N trend window for the brief (default: 3)
  --brief-format <markdown|html|both>    Smoke brief format (default: markdown)
  --output-dir <path>                    Brief output directory
  --summary-json <path>                  Write machine-readable pipeline summary JSON
  --scan-dir <path>                      StatBroadcast game brief scan directory
  --bundle-path <path>                   Output bundle path
  --reuse-bundle                        Reuse an existing bundle at --bundle-path instead of regenerating it
  --cfbstats-snapshot <path>             Snapshot artifact path (generated or reused)
  --cfbstats-verification-report <path>  Verification report path (generated or reused)
  --enrichment-file <path>               Enrichment artifact path
  --run-tests                            Run parser and analysis pytest suites
  --skip-tests                           Skip parser and analysis pytest suites
  --strict-verification                  Fail if verification report has fail metrics (default)
  --no-strict-verification               Allow verification fail metrics without failing the pipeline
  --no-enrichment                        Skip enrichment refresh/use during smoke rendering
  --help                                 Show this help

Environment overrides:
  PBP_PIPELINE_PYTHON   Python interpreter to use
  PBP_PARSER_ROOT       Sibling pbp-parser checkout path
  YR_DATA_API_ROOT      Sibling yr-data-api checkout path
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE=${2:-}
      shift 2
      ;;
    --season)
      SEASON=${2:-}
      shift 2
      ;;
    --last-n)
      LAST_N=${2:-}
      shift 2
      ;;
    --brief-format)
      BRIEF_FORMAT=${2:-}
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR=${2:-}
      shift 2
      ;;
    --summary-json)
      SUMMARY_JSON=${2:-}
      shift 2
      ;;
    --scan-dir)
      SCAN_DIR=${2:-}
      shift 2
      ;;
    --bundle-path)
      BUNDLE_PATH=${2:-}
      shift 2
      ;;
    --reuse-bundle)
      REUSE_BUNDLE=1
      shift
      ;;
    --cfbstats-snapshot)
      SNAPSHOT_PATH=${2:-}
      shift 2
      ;;
    --cfbstats-verification-report)
      VERIFICATION_REPORT_PATH=${2:-}
      shift 2
      ;;
    --enrichment-file)
      ENRICHMENT_FILE=${2:-}
      shift 2
      ;;
    --run-tests)
      RUN_TESTS=1
      shift
      ;;
    --skip-tests)
      RUN_TESTS=0
      shift
      ;;
    --strict-verification)
      STRICT_VERIFICATION=1
      shift
      ;;
    --no-strict-verification)
      STRICT_VERIFICATION=0
      shift
      ;;
    --no-enrichment)
      NO_ENRICHMENT=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -z "${TEAM1}" ]]; then
        TEAM1=$1
      elif [[ -z "${TEAM2}" ]]; then
        TEAM2=$1
      else
        echo "Unexpected positional argument: $1" >&2
        usage >&2
        exit 2
      fi
      shift
      ;;
  esac
done

if [[ -z "${TEAM1}" || -z "${TEAM2}" ]]; then
  usage >&2
  exit 2
fi

case "${MODE}" in
  live-refresh|offline-validate) ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    exit 2
    ;;
esac

case "${BRIEF_FORMAT}" in
  markdown|html|both) ;;
  *)
    echo "Unsupported --brief-format value: ${BRIEF_FORMAT}" >&2
    exit 2
    ;;
esac

PYTHON_BIN=${PBP_PIPELINE_PYTHON:-}
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${WORKSPACE_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${WORKSPACE_ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
  else
    echo "Unable to find python3 or \$PBP_PIPELINE_PYTHON." >&2
    exit 2
  fi
fi

abs_path() {
  "${PYTHON_BIN}" - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

brief_slugify() {
  PYTHONPATH="${ANALYSIS_ROOT}" "${PYTHON_BIN}" - "$1" <<'PY'
import sys
from scripts.game_prep_brief.loaders import slugify

print(slugify(sys.argv[1]))
PY
}

ensure_parent_dir() {
  local target=$1
  mkdir -p "$(dirname "${target}")"
}

TEAM1_SLUG=$(brief_slugify "${TEAM1}")
TEAM2_SLUG=$(brief_slugify "${TEAM2}")
BRIEF_BASE="${TEAM1_SLUG}_vs_${TEAM2_SLUG}_${SEASON}_v2"

OUTPUT_DIR=$(abs_path "${OUTPUT_DIR}")

if [[ -z "${BUNDLE_PATH}" ]]; then
  if [[ "${MODE}" == "live-refresh" && -d "${YR_DATA_API_ROOT}" ]]; then
    BUNDLE_PATH="${YR_DATA_API_ROOT}/data/pbp_stats_bundle.json"
  else
    BUNDLE_PATH="${OUTPUT_DIR}/pbp_stats_bundle.json"
  fi
fi
if [[ -z "${SNAPSHOT_PATH}" ]]; then
  SNAPSHOT_PATH="${PARSER_ROOT}/data/cfbstats_snapshots/cfbstats_${SEASON}.json"
fi
if [[ -z "${VERIFICATION_REPORT_PATH}" ]]; then
  VERIFICATION_REPORT_PATH="${PARSER_ROOT}/data/cfbstats_reports/cfbstats_verification_${SEASON}.json"
fi
if [[ -z "${ENRICHMENT_FILE}" ]]; then
  ENRICHMENT_FILE="${OUTPUT_DIR}/${TEAM1_SLUG}_vs_${TEAM2_SLUG}_${SEASON}_enrichment.json"
fi

BUNDLE_PATH=$(abs_path "${BUNDLE_PATH}")
SNAPSHOT_PATH=$(abs_path "${SNAPSHOT_PATH}")
VERIFICATION_REPORT_PATH=$(abs_path "${VERIFICATION_REPORT_PATH}")
ENRICHMENT_FILE=$(abs_path "${ENRICHMENT_FILE}")
SCAN_DIR=$(abs_path "${SCAN_DIR}")

mkdir -p "${OUTPUT_DIR}"
ensure_parent_dir "${BUNDLE_PATH}"
ensure_parent_dir "${SNAPSHOT_PATH}"
ensure_parent_dir "${VERIFICATION_REPORT_PATH}"
ensure_parent_dir "${ENRICHMENT_FILE}"
if [[ -n "${SUMMARY_JSON}" ]]; then
  SUMMARY_JSON=$(abs_path "${SUMMARY_JSON}")
  ensure_parent_dir "${SUMMARY_JSON}"
fi

if [[ ! -d "${ANALYSIS_ROOT}" ]]; then
  echo "Missing pbp-analysis root at ${ANALYSIS_ROOT}" >&2
  exit 2
fi
if [[ "${MODE}" == "live-refresh" || "${REUSE_BUNDLE}" == "0" ]]; then
  if [[ ! -d "${PARSER_ROOT}" ]]; then
    echo "Missing pbp-parser root at ${PARSER_ROOT}" >&2
    exit 2
  fi
fi
if [[ "${REUSE_BUNDLE}" == "0" ]]; then
  if [[ ! -d "${SCAN_DIR}" ]]; then
    echo "Missing StatBroadcast scan directory at ${SCAN_DIR}" >&2
    exit 2
  fi
fi
if [[ "${REUSE_BUNDLE}" == "1" && ! -f "${BUNDLE_PATH}" ]]; then
  echo "Missing reusable bundle at ${BUNDLE_PATH}" >&2
  exit 2
fi

TMP_DIR=$(mktemp -d)
STAGE_FILE="${TMP_DIR}/stages.tsv"
WARNINGS_FILE="${TMP_DIR}/warnings.log"
VERIFICATION_COUNTS_FILE="${TMP_DIR}/verification_counts.json"
CURRENT_STAGE_FILE="${TMP_DIR}/current_stage.tsv"
touch "${STAGE_FILE}" "${WARNINGS_FILE}"

STAGE_HEARTBEAT_SECONDS=${PBP_PIPELINE_STAGE_HEARTBEAT_SECONDS:-60}
STAGE_BUDGET_OVERRIDES=${PBP_PIPELINE_STAGE_BUDGET_OVERRIDES:-}
PIPELINE_SIGNAL=""

if ! [[ "${STAGE_HEARTBEAT_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "PBP_PIPELINE_STAGE_HEARTBEAT_SECONDS must be an integer (got '${STAGE_HEARTBEAT_SECONDS}')." >&2
  exit 2
fi

BRIEF_MARKDOWN_PATH=""
BRIEF_HTML_PATH=""
if [[ "${BRIEF_FORMAT}" == "markdown" || "${BRIEF_FORMAT}" == "both" ]]; then
  BRIEF_MARKDOWN_PATH="${OUTPUT_DIR}/${BRIEF_BASE}.md"
fi
if [[ "${BRIEF_FORMAT}" == "html" || "${BRIEF_FORMAT}" == "both" ]]; then
  BRIEF_HTML_PATH="${OUTPUT_DIR}/${BRIEF_BASE}.html"
fi

contains_exit_code() {
  local needle=$1
  local allowed_csv=$2
  local IFS=,
  read -r -a allowed_codes <<< "${allowed_csv}"
  for code in "${allowed_codes[@]}"; do
    if [[ "${needle}" == "${code}" ]]; then
      return 0
    fi
  done
  return 1
}

record_stage() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$1" "${2}" "${3}" "${4:-}" "${5:-}" "${6:-}" "${7:-0}" "${8:-}" "${9:-0}" >> "${STAGE_FILE}"
  rm -f "${CURRENT_STAGE_FILE}"
}

record_skipped() {
  local stage_name=$1
  local detail=${2:-}
  echo "[skip] ${stage_name}${detail:+ (${detail})}"
  record_stage "${stage_name}" "skipped" "0" "${detail}"
}

stage_expected_duration_seconds() {
  local stage_name=$1
  local expected=""
  case "${stage_name}" in
    parser_tests) expected=1200 ;;
    analysis_tests) expected=900 ;;
    bundle_generation) expected=900 ;;
    bundle_validation|offline_artifact_validation|verification_gate) expected=60 ;;
    cfbstats_snapshot) expected=1200 ;;
    cfbstats_verification_report) expected=900 ;;
    enrichment_refresh) expected=600 ;;
    smoke_brief) expected=300 ;;
  esac

  if [[ -n "${STAGE_BUDGET_OVERRIDES}" ]]; then
    local IFS=,
    read -r -a override_pairs <<< "${STAGE_BUDGET_OVERRIDES}"
    for pair in "${override_pairs[@]}"; do
      local override_stage=${pair%%=*}
      local override_value=${pair#*=}
      if [[ "${override_stage}" == "${stage_name}" && "${override_value}" =~ ^[0-9]+$ ]]; then
        expected=${override_value}
      fi
    done
  fi

  echo "${expected}"
}

write_current_stage() {
  local stage_name=$1
  local start_epoch=$2
  local start_iso=$3
  local expected_duration=$4
  local heartbeat_count=$5
  local exceeded_budget=$6
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${stage_name}" "${start_epoch}" "${start_iso}" "${expected_duration}" "${heartbeat_count}" "${exceeded_budget}" \
    > "${CURRENT_STAGE_FILE}"
}

record_interrupted_stage_if_needed() {
  local exit_code=$1
  if [[ ! -f "${CURRENT_STAGE_FILE}" ]]; then
    return 0
  fi

  local stage_name=""
  local start_epoch=""
  local start_iso=""
  local expected_duration=""
  local heartbeat_count=""
  local exceeded_budget=""
  IFS=$'\t' read -r stage_name start_epoch start_iso expected_duration heartbeat_count exceeded_budget < "${CURRENT_STAGE_FILE}"
  [[ -n "${stage_name}" ]] || return 0

  local finish_epoch
  finish_epoch=$(date +%s)
  local finish_iso
  finish_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local duration=0
  if [[ "${start_epoch}" =~ ^[0-9]+$ ]]; then
    duration=$((finish_epoch - start_epoch))
  fi
  if [[ -n "${expected_duration}" && "${expected_duration}" =~ ^[0-9]+$ && "${expected_duration}" -gt 0 && "${duration}" -ge "${expected_duration}" ]]; then
    exceeded_budget=1
  fi

  local detail="interrupted_exit_code=${exit_code}"
  if [[ -n "${PIPELINE_SIGNAL}" ]]; then
    detail="${detail};signal=${PIPELINE_SIGNAL}"
  fi
  record_stage \
    "${stage_name}" \
    "interrupted" \
    "${duration}" \
    "${detail}" \
    "${start_iso}" \
    "${finish_iso}" \
    "${heartbeat_count:-0}" \
    "${expected_duration}" \
    "${exceeded_budget:-0}"
}

append_warnings_from_log() {
  local log_file=$1
  if [[ -f "${log_file}" ]]; then
    awk '/\[warn\]/ { print }' "${log_file}" >> "${WARNINGS_FILE}"
  fi
}

run_stage_impl() {
  local stage_name=$1
  local allowed_codes=$2
  shift 2

  local stage_log="${TMP_DIR}/${stage_name}.log"
  local start_seconds=${SECONDS}
  local start_epoch
  start_epoch=$(date +%s)
  local start_iso
  start_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local expected_duration
  expected_duration=$(stage_expected_duration_seconds "${stage_name}")
  local heartbeat_count=0
  local exceeded_budget=0

  if [[ -n "${expected_duration}" ]]; then
    echo "[stage] ${stage_name} (expected<=${expected_duration}s, heartbeat=${STAGE_HEARTBEAT_SECONDS}s)"
  else
    echo "[stage] ${stage_name} (heartbeat=${STAGE_HEARTBEAT_SECONDS}s)"
  fi
  write_current_stage "${stage_name}" "${start_epoch}" "${start_iso}" "${expected_duration}" "${heartbeat_count}" "${exceeded_budget}"
  set +e
  (
    set -o pipefail
    "$@" 2>&1 | tee "${stage_log}"
  ) &
  local stage_pid=$!
  if [[ "${STAGE_HEARTBEAT_SECONDS}" -gt 0 ]]; then
    local next_heartbeat=${STAGE_HEARTBEAT_SECONDS}
    while kill -0 "${stage_pid}" 2>/dev/null; do
      sleep 1
      if ! kill -0 "${stage_pid}" 2>/dev/null; then
        break
      fi

      local elapsed=$((SECONDS - start_seconds))
      if [[ "${elapsed}" -lt "${next_heartbeat}" ]]; then
        continue
      fi

      heartbeat_count=$((heartbeat_count + 1))
      next_heartbeat=$((next_heartbeat + STAGE_HEARTBEAT_SECONDS))
      local heartbeat_msg="[heartbeat] ${stage_name} still running (elapsed=${elapsed}s"
      if [[ -n "${expected_duration}" ]]; then
        heartbeat_msg="${heartbeat_msg}, expected<=${expected_duration}s"
      fi
      heartbeat_msg="${heartbeat_msg})"
      echo "${heartbeat_msg}" | tee -a "${stage_log}"

      if [[ -n "${expected_duration}" && "${expected_duration}" -gt 0 && "${elapsed}" -ge "${expected_duration}" && "${exceeded_budget}" -eq 0 ]]; then
        exceeded_budget=1
        echo "[warn] ${stage_name} exceeded expected duration budget (${expected_duration}s); waiting for completion" \
          | tee -a "${stage_log}"
      fi

      write_current_stage \
        "${stage_name}" \
        "${start_epoch}" \
        "${start_iso}" \
        "${expected_duration}" \
        "${heartbeat_count}" \
        "${exceeded_budget}"
    done
  fi
  wait "${stage_pid}"
  local stage_exit=$?
  set -e

  local duration=$((SECONDS - start_seconds))
  local finish_iso
  finish_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  append_warnings_from_log "${stage_log}"

  if contains_exit_code "${stage_exit}" "${allowed_codes}"; then
    local detail=""
    if [[ "${stage_exit}" != "0" ]]; then
      detail="allowed_exit_code=${stage_exit}"
    fi
    if [[ "${exceeded_budget}" -eq 1 ]]; then
      detail="${detail:+${detail};}expected_duration_exceeded"
    fi
    record_stage \
      "${stage_name}" \
      "passed" \
      "${duration}" \
      "${detail}" \
      "${start_iso}" \
      "${finish_iso}" \
      "${heartbeat_count}" \
      "${expected_duration}" \
      "${exceeded_budget}"
    return 0
  fi

  local detail="exit_code=${stage_exit}"
  if [[ "${exceeded_budget}" -eq 1 ]]; then
    detail="${detail};expected_duration_exceeded"
  fi
  record_stage \
    "${stage_name}" \
    "failed" \
    "${duration}" \
    "${detail}" \
    "${start_iso}" \
    "${finish_iso}" \
    "${heartbeat_count}" \
    "${expected_duration}" \
    "${exceeded_budget}"
  return "${stage_exit}"
}

run_stage() {
  local stage_name=$1
  shift
  run_stage_impl "${stage_name}" "0" "$@"
}

run_stage_allow() {
  local stage_name=$1
  local allowed_codes=$2
  shift 2
  run_stage_impl "${stage_name}" "${allowed_codes}" "$@"
}

refresh_enrichment() {
  PYTHONPATH="${ANALYSIS_ROOT}" "${PYTHON_BIN}" - "${ENRICHMENT_FILE}" "${TEAM1}" "${TEAM2}" <<'PY'
from pathlib import Path
import sys

from scripts.game_prep_brief.loaders import (
    build_enrichment_payload,
    load_enrichment_file,
    merge_enrichment_payload,
    slugify,
    write_enrichment_file,
)

enrichment_path = Path(sys.argv[1]).expanduser()
team_names = sys.argv[2:]
team_specs = [{"slug": slugify(name), "display_name": name} for name in team_names]
refreshed = build_enrichment_payload(team_specs)
if not refreshed:
    raise SystemExit(f"Enrichment refresh returned no data for {enrichment_path}")
merged = merge_enrichment_payload(load_enrichment_file(enrichment_path), refreshed)
write_enrichment_file(enrichment_path, merged)
print(f"[ok] Enrichment -> {enrichment_path}")
PY
}

write_disabled_enrichment_fixture() {
  PYTHONPATH="${ANALYSIS_ROOT}" "${PYTHON_BIN}" - "${ENRICHMENT_FILE}" "${TEAM1}" "${TEAM2}" <<'PY'
from pathlib import Path
import json
import sys

from scripts.game_prep_brief.loaders import slugify

enrichment_path = Path(sys.argv[1]).expanduser()
team_names = sys.argv[2:]
payload = {
    slugify(name): {
        "_status": "disabled",
        "_source": "pipeline",
    }
    for name in team_names
}
enrichment_path.parent.mkdir(parents=True, exist_ok=True)
enrichment_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"[ok] Enrichment placeholder -> {enrichment_path}")
PY
}

validate_offline_artifacts() {
  "${PYTHON_BIN}" - "${SNAPSHOT_PATH}" "${VERIFICATION_REPORT_PATH}" <<'PY'
from pathlib import Path
import json
import sys

checks = [
    (Path(sys.argv[1]).expanduser(), "cfbstats_snapshot"),
    (Path(sys.argv[2]).expanduser(), "cfbstats_bundle_verification_report"),
]

for path, expected_artifact in checks:
    if not path.exists():
        raise SystemExit(f"Missing {expected_artifact} artifact at {path}")
    with open(path) as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid {expected_artifact} artifact at {path}: expected object")
    actual = ((payload.get("meta") or {}).get("artifact") or "").strip()
    if actual != expected_artifact:
        raise SystemExit(
            f"Invalid {expected_artifact} artifact at {path}: found '{actual or 'unknown'}'"
        )
    print(f"[ok] {expected_artifact} -> {path}")
PY
}

validate_bundle_artifact() {
  "${PYTHON_BIN}" - "${BUNDLE_PATH}" <<'PY'
from pathlib import Path
import json
import sys

bundle_path = Path(sys.argv[1]).expanduser()
if not bundle_path.exists():
    raise SystemExit(f"Missing bundle artifact at {bundle_path}")

with open(bundle_path) as handle:
    payload = json.load(handle)

if not isinstance(payload, dict):
    raise SystemExit(f"Invalid bundle artifact at {bundle_path}: expected object")

teams = payload.get("teams", payload)
if not isinstance(teams, dict) or not teams:
    raise SystemExit(f"Invalid bundle artifact at {bundle_path}: missing teams")

print(f"[ok] bundle -> {bundle_path}")
PY
}

check_verification_report() {
  "${PYTHON_BIN}" - "${VERIFICATION_REPORT_PATH}" "${VERIFICATION_COUNTS_FILE}" "${STRICT_VERIFICATION}" <<'PY'
from pathlib import Path
import json
import sys

report_path = Path(sys.argv[1]).expanduser()
counts_path = Path(sys.argv[2]).expanduser()
strict = sys.argv[3] == "1"

if not report_path.exists():
    raise SystemExit(f"Missing verification report at {report_path}")

with open(report_path) as handle:
    report = json.load(handle)

summary = report.get("summary") if isinstance(report, dict) else None
if not isinstance(summary, dict):
    raise SystemExit(f"Invalid verification report at {report_path}: missing summary")

metric_results = summary.get("metric_results") if isinstance(summary.get("metric_results"), dict) else {}
counts = {
    "pass": int(metric_results.get("pass") or 0),
    "warning": int(metric_results.get("warning") or 0),
    "fail": int(metric_results.get("fail") or 0),
}
counts_path.write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")

print(
    f"[ok] Verification summary -> pass={counts['pass']} warning={counts['warning']} fail={counts['fail']}"
)
if strict and counts["fail"] > 0:
    raise SystemExit(2)
PY
}

run_parser_tests_cmd() {
  (
    cd "${PARSER_ROOT}"
    env PYTHONPATH=src "${PYTHON_BIN}" -m pytest -q
  )
}

run_analysis_tests_cmd() {
  (
    cd "${ANALYSIS_ROOT}"
    env PYTHONPATH=. "${PYTHON_BIN}" -m pytest -q
  )
}

generate_bundle_cmd() {
  (
    cd "${PARSER_ROOT}"
    env PYTHONPATH=src "${PYTHON_BIN}" scripts/generate_statbroadcast_bundle.py \
      --scan-dir "${SCAN_DIR}" \
      --last-n "${LAST_N}" \
      --metrics-profile statbroadcast_source_of_truth \
      --out "${BUNDLE_PATH}"
  )
}

generate_snapshot_cmd() {
  (
    cd "${PARSER_ROOT}"
    env PYTHONPATH=src "${PYTHON_BIN}" scripts/snapshot_cfbstats.py \
      --year "${SEASON}" \
      --output "${SNAPSHOT_PATH}"
  )
}

generate_verification_report_cmd() {
  (
    cd "${PARSER_ROOT}"
    env PYTHONPATH=src "${PYTHON_BIN}" scripts/verify_bundle_cfbstats.py \
      --bundle "${BUNDLE_PATH}" \
      --year "${SEASON}" \
      --json-out "${VERIFICATION_REPORT_PATH}"
  )
}

smoke_brief_cmd() {
  local -a cmd=(
    env
    GAME_PREP_XML_BUNDLE_PATH="${BUNDLE_PATH}"
    PYTHONPATH=.
    "${PYTHON_BIN}"
    -m
    scripts.game_prep_brief
    "${TEAM1}"
    "${TEAM2}"
    --season
    "${SEASON}"
    --format
    "${BRIEF_FORMAT}"
    --last-n
    "${LAST_N}"
    --output-dir
    "${OUTPUT_DIR}"
    --cfbstats-snapshot
    "${SNAPSHOT_PATH}"
    --cfbstats-verification-report
    "${VERIFICATION_REPORT_PATH}"
  )

  if [[ "${NO_ENRICHMENT}" == "1" ]]; then
    write_disabled_enrichment_fixture
  fi
  cmd+=(--enrichment-file "${ENRICHMENT_FILE}")

  (
    cd "${ANALYSIS_ROOT}"
    "${cmd[@]}"
  )
}

write_summary_json() {
  local exit_code=$1
  [[ -n "${SUMMARY_JSON}" ]] || return 0

  local analysis_ref=""
  local parser_ref=""
  if git -C "${ANALYSIS_ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    analysis_ref=$(git -C "${ANALYSIS_ROOT}" rev-parse HEAD)
  fi
  if git -C "${PARSER_ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    parser_ref=$(git -C "${PARSER_ROOT}" rev-parse HEAD)
  fi

  SUMMARY_JSON="${SUMMARY_JSON}" \
  STAGE_FILE="${STAGE_FILE}" \
  WARNINGS_FILE="${WARNINGS_FILE}" \
  VERIFICATION_COUNTS_FILE="${VERIFICATION_COUNTS_FILE}" \
  STAGE_HEARTBEAT_SECONDS="${STAGE_HEARTBEAT_SECONDS}" \
  MODE="${MODE}" \
  SEASON="${SEASON}" \
  TEAM1="${TEAM1}" \
  TEAM2="${TEAM2}" \
  TEAM1_SLUG="${TEAM1_SLUG}" \
  TEAM2_SLUG="${TEAM2_SLUG}" \
  BUNDLE_PATH="${BUNDLE_PATH}" \
  SNAPSHOT_PATH="${SNAPSHOT_PATH}" \
  VERIFICATION_REPORT_PATH="${VERIFICATION_REPORT_PATH}" \
  ENRICHMENT_FILE="${ENRICHMENT_FILE}" \
  OUTPUT_DIR="${OUTPUT_DIR}" \
  STRICT_VERIFICATION="${STRICT_VERIFICATION}" \
  BRIEF_FORMAT="${BRIEF_FORMAT}" \
  BRIEF_MARKDOWN_PATH="${BRIEF_MARKDOWN_PATH}" \
  BRIEF_HTML_PATH="${BRIEF_HTML_PATH}" \
  ANALYSIS_REF="${analysis_ref}" \
  PARSER_REF="${parser_ref}" \
  FINAL_EXIT_CODE="${exit_code}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path


def _read_stage_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        (
            stage,
            status,
            duration,
            detail,
            started_at,
            finished_at,
            heartbeat_count,
            expected_duration,
            exceeded_expected,
        ) = (raw.split("\t") + [""] * 9)[:9]
        rows.append(
            {
                "name": stage,
                "status": status,
                "duration_seconds": int(duration),
                "detail": detail or None,
                "started_at": started_at or None,
                "finished_at": finished_at or None,
                "heartbeat_count": int(heartbeat_count or 0),
                "expected_duration_seconds": int(expected_duration) if expected_duration else None,
                "exceeded_expected_duration": exceeded_expected == "1",
            }
        )
    return rows


def _read_warning_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    seen: set[str] = set()
    warnings: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        warnings.append(clean)
    return warnings


def _read_counts(path: Path) -> dict:
    if not path.exists():
        return {"pass": 0, "warning": 0, "fail": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"pass": 0, "warning": 0, "fail": 0}
    if not isinstance(payload, dict):
        return {"pass": 0, "warning": 0, "fail": 0}
    return {
        "pass": int(payload.get("pass") or 0),
        "warning": int(payload.get("warning") or 0),
        "fail": int(payload.get("fail") or 0),
    }


def _path_or_none(value: str | None) -> str | None:
    if not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def _path_exists(value: str | None, *, assume_exists: bool = False) -> bool:
    if assume_exists:
        return True
    if not value:
        return False
    return Path(value).exists()


def _artifact_entry(
    *,
    logical_name: str,
    path_value: str | None,
    tier: str,
    required: bool,
    relative_path: str | None,
    scope: str,
    assume_exists: bool = False,
) -> dict:
    path = _path_or_none(path_value)
    return {
        "logical_name": logical_name,
        "path": path,
        "exists": _path_exists(path, assume_exists=assume_exists),
        "tier": tier,
        "scope": scope,
        "required": required,
        "relative_path": relative_path,
    }


def _stage_status(rows: list[dict], name: str) -> str | None:
    for row in rows:
        if row["name"] == name:
            return str(row["status"])
    return None


stages = _read_stage_rows(Path(os.environ["STAGE_FILE"]))
warnings = _read_warning_lines(Path(os.environ["WARNINGS_FILE"]))
verification_counts = _read_counts(Path(os.environ["VERIFICATION_COUNTS_FILE"]))
season = int(os.environ["SEASON"])
team1 = os.environ["TEAM1"]
team2 = os.environ["TEAM2"]
team1_slug = os.environ["TEAM1_SLUG"]
team2_slug = os.environ["TEAM2_SLUG"]
analysis_ref = os.environ.get("ANALYSIS_REF") or None
parser_ref = os.environ.get("PARSER_REF") or None
summary_path = _path_or_none(os.environ.get("SUMMARY_JSON"))
generated_timestamp = datetime.now(timezone.utc)
generated_at = generated_timestamp.isoformat()
generated_tag = generated_timestamp.strftime("%Y%m%dT%H%M%SZ")
brief_markdown_relative = (
    f"scratch/brief/{team1_slug}_vs_{team2_slug}_{season}_v2.md"
    if os.environ.get("BRIEF_MARKDOWN_PATH")
    else None
)
brief_html_relative = (
    f"scratch/brief/{team1_slug}_vs_{team2_slug}_{season}_v2.html"
    if os.environ.get("BRIEF_HTML_PATH")
    else None
)

published_artifacts = {
    "bundle": _artifact_entry(
        logical_name="bundle",
        path_value=os.environ.get("BUNDLE_PATH"),
        tier="published",
        scope="season",
        required=True,
        relative_path=f"published/{season}/pbp_stats_bundle_{season}.json",
    ),
    "cfbstats_snapshot": _artifact_entry(
        logical_name="cfbstats_snapshot",
        path_value=os.environ.get("SNAPSHOT_PATH"),
        tier="published",
        scope="season",
        required=True,
        relative_path=f"published/{season}/cfbstats_{season}.json",
    ),
    "cfbstats_verification_report": _artifact_entry(
        logical_name="cfbstats_verification_report",
        path_value=os.environ.get("VERIFICATION_REPORT_PATH"),
        tier="published",
        scope="season",
        required=True,
        relative_path=f"published/{season}/cfbstats_verification_{season}.json",
    ),
    "pipeline_summary": _artifact_entry(
        logical_name="pipeline_summary",
        path_value=os.environ.get("SUMMARY_JSON"),
        tier="published",
        scope="run",
        required=True,
        relative_path=f"published/{season}/game_prep_pipeline_summary_{season}.json",
        assume_exists=True,
    ),
}

scratch_artifacts = {
    "enrichment": _artifact_entry(
        logical_name="enrichment",
        path_value=os.environ.get("ENRICHMENT_FILE"),
        tier="scratch",
        scope="run",
        required=False,
        relative_path=f"scratch/game_prep_enrichment_{season}.json",
    ),
    "smoke_brief_output_dir": _artifact_entry(
        logical_name="smoke_brief_output_dir",
        path_value=os.environ.get("OUTPUT_DIR"),
        tier="scratch",
        scope="run",
        required=False,
        relative_path="scratch/brief/",
    ),
    "smoke_brief_markdown": _artifact_entry(
        logical_name="smoke_brief_markdown",
        path_value=os.environ.get("BRIEF_MARKDOWN_PATH"),
        tier="scratch",
        scope="run",
        required=False,
        relative_path=brief_markdown_relative,
    ),
    "smoke_brief_html": _artifact_entry(
        logical_name="smoke_brief_html",
        path_value=os.environ.get("BRIEF_HTML_PATH"),
        tier="scratch",
        scope="run",
        required=False,
        relative_path=brief_html_relative,
    ),
}

published_set_complete = all(entry["exists"] for entry in published_artifacts.values())
non_publishable_reasons: list[str] = []
if os.environ["MODE"] != "live-refresh":
    non_publishable_reasons.append("mode_must_be_live_refresh")
if int(os.environ["FINAL_EXIT_CODE"]) != 0:
    non_publishable_reasons.append("pipeline_exit_nonzero")
if verification_counts["fail"] > 0:
    non_publishable_reasons.append("verification_fail_metrics_present")
if _stage_status(stages, "smoke_brief") != "passed":
    non_publishable_reasons.append("smoke_brief_failed")
if not published_set_complete:
    non_publishable_reasons.append("published_artifact_set_incomplete")
publishable = not non_publishable_reasons
artifact_set_id = f"{season}-{generated_tag}-{(analysis_ref or 'unknown')[:12]}"
interrupted_stages = [row["name"] for row in stages if row["status"] == "interrupted"]
slow_stages = [row["name"] for row in stages if row.get("exceeded_expected_duration")]

summary = {
    "season": season,
    "teams": [team1, team2],
    "mode": os.environ["MODE"],
    "generated_at": generated_at,
    "artifacts": {
        "bundle": _path_or_none(os.environ.get("BUNDLE_PATH")),
        "snapshot": _path_or_none(os.environ.get("SNAPSHOT_PATH")),
        "verification_report": _path_or_none(os.environ.get("VERIFICATION_REPORT_PATH")),
        "enrichment": _path_or_none(os.environ.get("ENRICHMENT_FILE")),
        "brief_output_dir": _path_or_none(os.environ.get("OUTPUT_DIR")),
        "brief_markdown": _path_or_none(os.environ.get("BRIEF_MARKDOWN_PATH")),
        "brief_html": _path_or_none(os.environ.get("BRIEF_HTML_PATH")),
        "summary_json": summary_path,
    },
    "git": {
        "pbp_analysis_ref": analysis_ref,
        "pbp_parser_ref": parser_ref,
    },
    "validation": {
        "parser_tests_passed": _stage_status(stages, "parser_tests") == "passed"
        if _stage_status(stages, "parser_tests") != "skipped"
        else None,
        "analysis_tests_passed": _stage_status(stages, "analysis_tests") == "passed"
        if _stage_status(stages, "analysis_tests") != "skipped"
        else None,
        "smoke_brief_passed": _stage_status(stages, "smoke_brief") == "passed",
        "verification_fail_count": verification_counts["fail"],
        "verification_warning_count": verification_counts["warning"],
    },
    "run_state": {
        "completed": not interrupted_stages,
        "interrupted": bool(interrupted_stages),
        "interrupted_stages": interrupted_stages,
    },
    "observability": {
        "heartbeat_interval_seconds": int(os.environ.get("STAGE_HEARTBEAT_SECONDS") or 0),
        "slow_stages": slow_stages,
    },
    "stages": stages,
    "warnings": warnings,
    "strict_verification": os.environ.get("STRICT_VERIFICATION", "1") == "1",
    "brief_format": os.environ.get("BRIEF_FORMAT"),
    "exit_code": int(os.environ["FINAL_EXIT_CODE"]),
    "artifact_contract": {
        "version": 1,
        "artifact_set_id": artifact_set_id,
        "published_root_relative_path": f"published/{season}/",
        "scratch_root_relative_path": "scratch/",
        "published_set_complete": published_set_complete,
        "publishable": publishable,
        "non_publishable_reasons": non_publishable_reasons,
        "published_artifacts": published_artifacts,
        "scratch_artifacts": scratch_artifacts,
    },
}

Path(os.environ["SUMMARY_JSON"]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY
  echo "[ok] Summary -> ${SUMMARY_JSON}"
}

cleanup() {
  local exit_code=$1
  record_interrupted_stage_if_needed "${exit_code}" || true
  write_summary_json "${exit_code}" || true
  rm -rf "${TMP_DIR}"
}

handle_interrupt() {
  local signal_name=$1
  local exit_code=$2
  PIPELINE_SIGNAL="${signal_name}"
  exit "${exit_code}"
}

trap 'cleanup $?' EXIT
trap 'handle_interrupt INT 130' INT
trap 'handle_interrupt TERM 143' TERM

if [[ "${RUN_TESTS}" == "1" ]]; then
  if [[ -d "${PARSER_ROOT}" ]]; then
    run_stage parser_tests run_parser_tests_cmd
  else
    record_skipped "parser_tests" "parser_root_unavailable"
  fi
else
  record_skipped "parser_tests" "disabled"
fi

if [[ "${RUN_TESTS}" == "1" ]]; then
  run_stage analysis_tests run_analysis_tests_cmd
else
  record_skipped "analysis_tests" "disabled"
fi

if [[ "${REUSE_BUNDLE}" == "1" ]]; then
  record_skipped "bundle_generation" "reused_existing_bundle"
  run_stage bundle_validation validate_bundle_artifact
else
  run_stage bundle_generation generate_bundle_cmd
fi

if [[ "${MODE}" == "live-refresh" ]]; then
  run_stage cfbstats_snapshot generate_snapshot_cmd

  run_stage_allow cfbstats_verification_report "0,2" generate_verification_report_cmd
else
  record_skipped "cfbstats_snapshot" "offline_mode_uses_existing_artifact"
  record_skipped "cfbstats_verification_report" "offline_mode_uses_existing_artifact"
  run_stage offline_artifact_validation validate_offline_artifacts
fi

run_stage verification_gate check_verification_report

if [[ "${NO_ENRICHMENT}" == "1" ]]; then
  record_skipped "enrichment_refresh" "disabled"
else
  if [[ "${MODE}" == "live-refresh" ]]; then
    run_stage enrichment_refresh refresh_enrichment
  else
    record_skipped "enrichment_refresh" "offline_mode_uses_existing_or_required_artifact"
  fi
fi

run_stage smoke_brief smoke_brief_cmd
