#!/usr/bin/env bash
# Runs Agora locally: the tile server (Martin), the API and the web, with their output together.
# Ctrl-C stops all three.
#
#   ./dev.sh
#
# Tiles on http://localhost:3000, the API on http://localhost:8000 (MCP on /mcp), the web on the
# port Vite prints (5173, or the next free one).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# A port already taken (a server left running) would make its server fail: say which.
for port in 3000 8000; do
  pid=$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null | head -1)
  if [ -n "$pid" ]; then
    echo "Port $port is in use by: $(ps -o command= -p "$pid")" >&2
    echo "Stop it first (kill $pid)." >&2
    exit 1
  fi
done

# The servers (and what they start, like Vite under npm) are in this script's process group:
# stopping the script stops them all.
trap 'trap - INT TERM EXIT; echo; echo "Stopping…"; kill 0' INT TERM EXIT

# Each server's lines prefixed with its name.
run() {
  local name=$1 dir=$2
  shift 2
  (cd "$ROOT/$dir" && exec "$@") 2>&1 | sed -l "s/^/[$name] /" &
}

run tiles tileserver martin --config martin.yaml
run api api .venv/bin/uvicorn agora_api.main:app --port 8000
run web platform npm run dev

wait
