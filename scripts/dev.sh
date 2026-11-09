#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$project_dir/backend/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "Создайте backend/.venv и установите backend/requirements-dev.txt"
  exit 1
fi
if ! command -v npm >/dev/null; then
  for node_dir in "$project_dir/web/.tools/node/bin" /home/rakh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin /home/rakh/Documents/ChatGPT/fibo.games/frontend/.tools/node-v22.23.4-linux-x64/bin; do
    if [[ -x "$node_dir/npm" ]]; then export PATH="$node_dir:$PATH"; break; fi
  done
fi
cd "$project_dir/backend"
"$python_bin" -m alembic upgrade head
# Local fallback avoids downloading embedding weights on startup. .env can opt into e5.
export FIBO_EMBEDDING_BACKEND="${FIBO_EMBEDDING_BACKEND:-hash}"
"$python_bin" -m uvicorn app.main:app --host 127.0.0.1 --port "${FIBO_API_PORT:-8000}" &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
cd "$project_dir/web"
npm run dev -- --host 127.0.0.1 --strictPort --port "${FIBO_WEB_PORT:-5174}"
