#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BFF_HOST="${BFF_HOST:-127.0.0.1}"
BFF_PORT="${BFF_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

pick_available_port() {
  local host="$1"
  local requested_port="$2"
  python3 - "$host" "$requested_port" <<'PY'
import socket
import sys

host = sys.argv[1]
start_port = int(sys.argv[2])

for port in range(start_port, start_port + 50):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            continue
    print(port)
    break
else:
    raise SystemExit(
        f"No available port found for {host} in range {start_port}-{start_port + 49}."
    )
PY
}

wait_for_http_ready() {
  local url="$1"
  local pid="$2"
  local label="$3"
  local attempt

  for attempt in {1..50}; do
    if python3 - "$url" <<'PY'
from urllib.request import urlopen
import sys

try:
    with urlopen(sys.argv[1], timeout=0.2):
        pass
except Exception:
    raise SystemExit(1)
PY
    then
      return 0
    fi
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      wait "$pid"
      return 1
    fi
    sleep 0.2
  done

  echo "${label} did not become ready at ${url}." >&2
  return 1
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
    wait "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BFF_PID:-}" ]]; then
    kill "${BFF_PID}" >/dev/null 2>&1 || true
    wait "${BFF_PID}" >/dev/null 2>&1 || true
  fi
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

REQUESTED_BFF_PORT="${BFF_PORT}"
REQUESTED_FRONTEND_PORT="${FRONTEND_PORT}"
BFF_PORT="$(pick_available_port "${BFF_HOST}" "${BFF_PORT}")"
FRONTEND_PORT="$(pick_available_port "${FRONTEND_HOST}" "${FRONTEND_PORT}")"
BFF_PROXY_TARGET="http://${BFF_HOST}:${BFF_PORT}"

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "${ROOT_DIR}/frontend" && npm install)
fi

if [[ "${BFF_PORT}" != "${REQUESTED_BFF_PORT}" ]]; then
  echo "Port ${REQUESTED_BFF_PORT} is busy for the BFF; using ${BFF_PORT} instead."
fi

if [[ "${FRONTEND_PORT}" != "${REQUESTED_FRONTEND_PORT}" ]]; then
  echo "Port ${REQUESTED_FRONTEND_PORT} is busy for the frontend; using ${FRONTEND_PORT} instead."
fi

echo "Starting seeded API Gateway / BFF runtime..."
(
  cd "${ROOT_DIR}"
  python3 -m services.api_gateway_bff.server --runtime local-demo --host "${BFF_HOST}" --port "${BFF_PORT}"
) &
BFF_PID=$!

echo "Starting frontend dev server..."
(
  cd "${ROOT_DIR}/frontend"
  BFF_PROXY_TARGET="${BFF_PROXY_TARGET}" npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --strictPort
) &
FRONTEND_PID=$!

wait_for_http_ready "http://${BFF_HOST}:${BFF_PORT}/health" "${BFF_PID}" "BFF"
wait_for_http_ready "http://${FRONTEND_HOST}:${FRONTEND_PORT}" "${FRONTEND_PID}" "Frontend"

echo
echo "Local MVP is starting."
echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "BFF:      http://${BFF_HOST}:${BFF_PORT}"
echo
echo "Reset path:"
echo "- Click the shell Reset button to clear browser-held screen context."
echo "- Stop this script and restart it to reset the seeded in-memory backend state."
echo
wait "${BFF_PID}" "${FRONTEND_PID}"
