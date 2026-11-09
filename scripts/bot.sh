#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir/bot"
if [[ ! -x .venv/bin/python ]]; then
  echo "Установите зависимости из bot/requirements.txt в bot/.venv"
  exit 1
fi
exec .venv/bin/python -m bot.main
