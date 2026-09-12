#!/usr/bin/env bash
# AI Fitness 즉시 실행 (macOS) — Windows용 START_AI_FITNESS.ps1 대응
set -euo pipefail
PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# tools/server.sh 가 fitness_web_server.py 와 같은 폴더에 정확히 하나 있어야 함
mapfile_compat() { SERVER_CANDIDATES=(); while IFS= read -r line; do SERVER_CANDIDATES+=("$line"); done; }
mapfile_compat < <(find "$PACKAGE_ROOT" -type f -path '*/tools/server.sh' -not -name '._*' 2>/dev/null \
  | while IFS= read -r f; do [[ -f "$(dirname "$f")/fitness_web_server.py" ]] && echo "$f"; done)
if (( ${#SERVER_CANDIDATES[@]} != 1 )); then
  echo "AI Fitness server.sh 가 패키지 안에 정확히 하나 있어야 합니다. (발견: ${#SERVER_CANDIDATES[@]})" >&2; exit 1
fi
SERVER_SCRIPT="${SERVER_CANDIDATES[0]}"
DEPLOYMENT="$(cd "$(dirname "$SERVER_SCRIPT")/.." && pwd)"
FRONTEND_FILE="$PACKAGE_ROOT/frontend1/fit-coach-webview.html"
RUNTIME_ROOT="${AI_FITNESS_RUNTIME_ROOT:-$PACKAGE_ROOT/.runtime_data}"

# Python: 패키지 내 .venv → 설치 스크립트가 만든 venv → PATH 순
PYTHON_EXE=""
for c in "$PACKAGE_ROOT/.venv/bin/python" "$RUNTIME_ROOT/venv/bin/python" "$HOME/ai_fitness_qwen3_runtime/venv/bin/python"; do
  [[ -x "$c" ]] && { PYTHON_EXE="$c"; break; }
done
if [[ -z "$PYTHON_EXE" ]]; then
  for c in python3.12 python3.11 python3.10 python3; do
    command -v "$c" >/dev/null 2>&1 && { PYTHON_EXE="$(command -v "$c")"; break; }
  done
fi
[[ -n "$PYTHON_EXE" ]] || { echo "Python을 찾을 수 없습니다. 먼저 SETUP_IF_NEEDED.sh 를 실행하세요." >&2; exit 1; }

for required in "$SERVER_SCRIPT" "$FRONTEND_FILE" "$DEPLOYMENT/models/Qwen3-4B-Q4_K_M.gguf" "$DEPLOYMENT/artifacts/rag_documents.sqlite"; do
  [[ -f "$required" ]] || { echo "필수 파일이 없습니다: $required" >&2; exit 1; }
done

export AI_FITNESS_FRONTEND_FILE="$FRONTEND_FILE"
export AI_FITNESS_CONTEXT_SIZE=32768
export AI_FITNESS_MAX_TOKENS=8192
export AI_FITNESS_PYTHON="$PYTHON_EXE"
export AI_FITNESS_RUNTIME_ROOT="$RUNTIME_ROOT"

bash "$SERVER_SCRIPT" start --web-port 8501 --model-port 8089 --ctx 32768 "$@"
echo "Open: http://127.0.0.1:8501"
