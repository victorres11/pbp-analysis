#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${PBP_OPERATOR_ENV_FILE:-$SCRIPT_DIR/.env}"
HOST="${PBP_OPERATOR_HOST:-127.0.0.1}"
PORT="${PBP_OPERATOR_PORT:-8788}"
DOPPLER_PROJECT="${PBP_OPERATOR_DOPPLER_PROJECT:-pbp}"
DOPPLER_CONFIG="${PBP_OPERATOR_DOPPLER_CONFIG:-prd}"
DOPPLER_ENABLED="${PBP_OPERATOR_USE_DOPPLER:-1}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

SERVER_CMD=(python3 "$SCRIPT_DIR/server.py" --host "$HOST" --port "$PORT")

if [[ -n "${PBP_OPERATOR_GITHUB_TOKEN:-}" ]]; then
  exec "${SERVER_CMD[@]}"
fi

if [[ "$DOPPLER_ENABLED" == "0" || "$DOPPLER_ENABLED" == "false" || "$DOPPLER_ENABLED" == "off" ]]; then
  echo "PBP_OPERATOR_GITHUB_TOKEN is not set and Doppler fallback is disabled." >&2
  exit 1
fi

if ! command -v doppler >/dev/null 2>&1; then
  echo "PBP_OPERATOR_GITHUB_TOKEN is not set and Doppler CLI is not installed." >&2
  exit 1
fi

echo "Starting operator via Doppler project '$DOPPLER_PROJECT' config '$DOPPLER_CONFIG'." >&2
exec doppler run --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG" -- "${SERVER_CMD[@]}"
