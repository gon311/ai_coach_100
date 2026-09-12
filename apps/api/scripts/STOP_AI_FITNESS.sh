#!/usr/bin/env bash
# AI Fitness 종료 (macOS) — Windows용 STOP_AI_FITNESS.ps1 대응
set -euo pipefail
PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$(find "$PACKAGE_ROOT" -type f -path '*/tools/server.sh' -not -name '._*' 2>/dev/null \
  | while IFS= read -r f; do [[ -f "$(dirname "$f")/fitness_web_server.py" ]] && echo "$f"; done | head -n 1)"
[[ -n "$SERVER_SCRIPT" ]] || { echo "AI Fitness server.sh 를 찾을 수 없습니다." >&2; exit 1; }
export AI_FITNESS_RUNTIME_ROOT="${AI_FITNESS_RUNTIME_ROOT:-$PACKAGE_ROOT/.runtime_data}"
bash "$SERVER_SCRIPT" stop --web-port 8501 --model-port 8089
