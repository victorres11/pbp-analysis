#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Prefer shared repo venvs that have Python 3.10+ and pbp_parser compatibility.
PY_CANDIDATES=(
  "${REPO_ROOT}/../.venv/bin/python"
  "${REPO_ROOT}/.venv/bin/python"
  "$(command -v python3 || true)"
)

pick_python() {
  local py
  for py in "${PY_CANDIDATES[@]}"; do
    [[ -n "${py}" ]] || continue
    [[ -x "${py}" ]] || continue
    if "${py}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      echo "${py}"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(pick_python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "error: Python 3.10+ is required for game brief generation." >&2
  echo "hint: use /Users/victorres/projects2/pbp/.venv/bin/python" >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m scripts.game_prep_brief "$@"
