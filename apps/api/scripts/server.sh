#!/usr/bin/env bash
# AI 체력 코치 — 모델(llama-server) + 웹(uvicorn) 통합 관리 스크립트 (macOS / Linux)
# Windows용 tools/server.ps1 을 그대로 옮긴 것입니다.
#
# 사용법:
#   tools/server.sh start  [--web-port 8501] [--model-port 8080] [--ctx 8192] [--no-browser]
#   tools/server.sh stop   [--web-port ...] [--model-port ...]
#   tools/server.sh status [--web-port ...] [--model-port ...]
#
# 환경 변수 (모두 선택):
#   AI_FITNESS_RUNTIME_ROOT   실행 캐시·로그·PID 위치 (기본: ~/ai_fitness_qwen3_runtime)
#   AI_FITNESS_PYTHON         사용할 python 실행 파일
#   AI_FITNESS_LLAMA_SERVER   사용할 llama-server 실행 파일
#   AI_FITNESS_MODEL_PATH     GGUF 모델 경로
#   AI_FITNESS_GPU_LAYERS     Metal에 올릴 레이어 수 (기본 99, 메모리 부족 시 0)
#   AI_FITNESS_FRONTEND_FILE  프론트엔드 HTML (기본: 배포 폴더의 frontend1/…)
set -euo pipefail

ACTION="status"
WEB_PORT=8501
MODEL_PORT=8080
CONTEXT_SIZE=8192
NO_BROWSER=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    start|stop|status) ACTION="$1" ;;
    --web-port)   WEB_PORT="$2"; shift ;;
    --model-port) MODEL_PORT="$2"; shift ;;
    --ctx|--context-size) CONTEXT_SIZE="$2"; shift ;;
    --no-browser) NO_BROWSER=1 ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
  shift
done

if (( CONTEXT_SIZE < 4096 || CONTEXT_SIZE > 32768 )); then
  echo "컨텍스트 길이는 4096~32768 사이여야 합니다: $CONTEXT_SIZE" >&2; exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="${AI_FITNESS_RUNTIME_ROOT:-$HOME/ai_fitness_qwen3_runtime}"
LOG_DIR="$RUNTIME_ROOT/logs"
OUTPUT_DIR="$RUNTIME_ROOT/outputs"
WEB_PID_PATH="$RUNTIME_ROOT/web.pid"
MODEL_PID_PATH="$RUNTIME_ROOT/model.pid"
WEB_URL="http://127.0.0.1:$WEB_PORT"
MODEL_URL="http://127.0.0.1:$MODEL_PORT"
MODEL_FILE_NAME="Qwen3-4B-Q4_K_M.gguf"

# ---------------------------------------------------------------- helpers
listening_pid() {  # $1 = port
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

web_ready() {
  curl -fsS --max-time 3 "$WEB_URL/api/health" 2>/dev/null | grep -q '"status": *"ok"'
}

model_ready() {
  curl -fsS --max-time 3 "$MODEL_URL/v1/models" 2>/dev/null | grep -q "$MODEL_FILE_NAME"
}

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

stop_owned_process() {  # $1 pid file, $2 expected name pattern (grep -E), $3 label
  local pid_path="$1" expected="$2" label="$3"
  if [[ ! -f "$pid_path" ]]; then
    echo "$label PID 기록이 없습니다."; return
  fi
  local saved_pid; saved_pid="$(tr -d '[:space:]' < "$pid_path")"
  local comm=""
  if [[ -n "$saved_pid" ]] && kill -0 "$saved_pid" 2>/dev/null; then
    comm="$(ps -p "$saved_pid" -o command= 2>/dev/null || true)"
  fi
  if [[ -n "$comm" ]] && grep -qiE "$expected" <<<"$comm"; then
    # 자식 프로세스까지 정리 (uvicorn 워커 등)
    pkill -TERM -P "$saved_pid" 2>/dev/null || true
    kill -TERM "$saved_pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$saved_pid" 2>/dev/null || break
      sleep 0.5
    done
    kill -0 "$saved_pid" 2>/dev/null && kill -KILL "$saved_pid" 2>/dev/null || true
    echo "$label 종료 완료 (PID $saved_pid)"
  else
    echo "$label 프로세스가 이미 종료되어 있습니다."
  fi
  rm -f "$pid_path"
}

sync_chroma_index() {
  local bundle="$PROJECT_ROOT/artifacts/chroma"
  local runtime="$RUNTIME_ROOT/chroma"
  local bundle_marker="$bundle/BUILD_COMPLETE.json"
  local runtime_marker="$runtime/BUILD_COMPLETE.json"
  if [[ ! -f "$bundle_marker" ]]; then
    echo "배포용 Chroma 인덱스를 찾을 수 없습니다: $bundle" >&2; exit 1
  fi
  if [[ -f "$runtime_marker" ]]; then
    if [[ "$(sha256_of "$bundle_marker")" == "$(sha256_of "$runtime_marker")" ]]; then
      echo "검색 인덱스 준비 완료"; return
    fi
    echo "실행 캐시에 다른 버전의 검색 인덱스가 있습니다: $runtime" >&2; exit 1
  fi
  if [[ -e "$runtime" ]]; then
    echo "완성되지 않은 검색 인덱스 캐시가 있습니다: $runtime" >&2
    echo "  → 삭제 후 다시 시도하세요: rm -rf \"$runtime\"" >&2; exit 1
  fi
  echo "첫 실행용 검색 인덱스를 준비합니다. 한 번만 복사되며 잠시 걸릴 수 있습니다."
  mkdir -p "$RUNTIME_ROOT"
  # rsync가 있으면 AppleDouble(._*) 파일을 제외하고 복사
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude='._*' --exclude='.DS_Store' "$bundle/" "$runtime/"
  else
    cp -R "$bundle" "$runtime"
  fi
  if [[ ! -f "$runtime_marker" ]]; then
    echo "검색 인덱스 복사가 완료되지 않았습니다." >&2; exit 1
  fi
  echo "검색 인덱스 준비 완료"
}

find_python() {
  if [[ -n "${AI_FITNESS_PYTHON:-}" && -x "$AI_FITNESS_PYTHON" ]]; then
    echo "$AI_FITNESS_PYTHON"; return
  fi
  local candidate
  for candidate in \
    "$RUNTIME_ROOT/venv/bin/python" \
    "$PROJECT_ROOT/../.venv/bin/python" \
    "$PROJECT_ROOT/.venv/bin/python"; do
    [[ -x "$candidate" ]] && { echo "$candidate"; return; }
  done
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then command -v "$candidate"; return; fi
  done
  echo "Python을 찾을 수 없습니다. 먼저 setup_ai_fitness.sh 를 실행해 주세요." >&2; exit 1
}

find_llama_server() {
  if [[ -n "${AI_FITNESS_LLAMA_SERVER:-}" && -x "$AI_FITNESS_LLAMA_SERVER" ]]; then
    echo "$AI_FITNESS_LLAMA_SERVER"; return
  fi
  local candidate
  for candidate in \
    "$PROJECT_ROOT/runtime/llama/llama-server" \
    "$RUNTIME_ROOT/llama/llama-server" \
    /opt/homebrew/bin/llama-server \
    /usr/local/bin/llama-server; do
    [[ -x "$candidate" ]] && { echo "$candidate"; return; }
  done
  if command -v llama-server >/dev/null 2>&1; then command -v llama-server; return; fi
  cat >&2 <<'EOF'
llama-server를 찾을 수 없습니다. 배포 폴더의 runtime/llama/llama-server.exe는 Windows 전용입니다.
macOS에서는 다음 중 하나로 설치하세요.
  brew install llama.cpp          (권장, Apple Silicon Metal 가속 포함)
또는 https://github.com/ggml-org/llama.cpp/releases 에서 macOS 바이너리를 받아
  runtime/llama/llama-server 로 넣거나 AI_FITNESS_LLAMA_SERVER 환경 변수로 지정하세요.
EOF
  exit 1
}

# ---------------------------------------------------------------- actions
start_model() {
  if model_ready; then
    local running; running="$(listening_pid "$MODEL_PORT")"
    [[ -n "$running" ]] && echo "$running" > "$MODEL_PID_PATH"
    echo "Qwen3 모델 서버가 이미 준비되어 있습니다."; return
  fi
  local model_path="${AI_FITNESS_MODEL_PATH:-$PROJECT_ROOT/models/$MODEL_FILE_NAME}"
  if [[ ! -f "$model_path" ]]; then
    echo "Qwen3 모델을 찾을 수 없습니다. models/$MODEL_FILE_NAME 를 확인해 주세요." >&2; exit 1
  fi
  local llama; llama="$(find_llama_server)"
  local gpu_layers="${AI_FITNESS_GPU_LAYERS:-99}"

  (
    cd "$PROJECT_ROOT"
    nohup "$llama" \
      --model "$model_path" --host 127.0.0.1 --port "$MODEL_PORT" \
      --ctx-size "$CONTEXT_SIZE" --parallel 1 --jinja --reasoning off \
      --n-gpu-layers "$gpu_layers" \
      > "$LOG_DIR/model.out.log" 2> "$LOG_DIR/model.err.log" &
    echo $! > "$MODEL_PID_PATH"
  )
  echo "Qwen3 모델을 준비하고 있습니다 (PID $(cat "$MODEL_PID_PATH"))."
  local attempt
  for attempt in $(seq 1 60); do
    if model_ready; then echo "Qwen3 모델 준비 완료"; return; fi
    if ! kill -0 "$(cat "$MODEL_PID_PATH")" 2>/dev/null; then
      echo "Qwen3 모델 서버가 바로 종료되었습니다. $LOG_DIR/model.err.log 를 확인해 주세요." >&2; exit 1
    fi
    sleep 2
  done
  echo "Qwen3 모델 서버가 준비되지 않았습니다. $LOG_DIR/model.err.log 를 확인해 주세요." >&2; exit 1
}

start_web() {
  if web_ready; then
    local running; running="$(listening_pid "$WEB_PORT")"
    [[ -n "$running" ]] && echo "$running" > "$WEB_PID_PATH"
    echo "웹 서버가 이미 준비되어 있습니다: $WEB_URL"; return
  fi
  local python; python="$(find_python)"
  if ! "$python" -c "import fastapi,uvicorn,chromadb,sentence_transformers,pydantic" 2>/dev/null; then
    echo "Python 필수 패키지가 없습니다 ($python). 먼저 setup_ai_fitness.sh 를 실행해 주세요." >&2; exit 1
  fi

  export AI_FITNESS_RUNTIME_ROOT="$RUNTIME_ROOT"
  export AI_FITNESS_ARTIFACTS_DIR="$PROJECT_ROOT/artifacts"
  export AI_FITNESS_CHROMA_DIR="$RUNTIME_ROOT/chroma"
  export AI_FITNESS_OUTPUT_DIR="$OUTPUT_DIR"
  export QWEN3_BASE_URL="$MODEL_URL"
  # macOS에서 tokenizers 포크 경고 억제
  export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

  (
    cd "$PROJECT_ROOT"
    nohup "$python" -m uvicorn fitness_web_server:app \
      --app-dir "$SCRIPT_DIR" --host 127.0.0.1 --port "$WEB_PORT" \
      > "$LOG_DIR/web.out.log" 2> "$LOG_DIR/web.err.log" &
    echo $! > "$WEB_PID_PATH"
  )
  echo "웹 화면을 준비하고 있습니다 (PID $(cat "$WEB_PID_PATH"))."
  local attempt
  for attempt in $(seq 1 90); do
    if web_ready; then echo "AI 체력 코치 준비 완료: $WEB_URL"; return; fi
    if ! kill -0 "$(cat "$WEB_PID_PATH")" 2>/dev/null; then
      echo "웹 서버가 바로 종료되었습니다. $LOG_DIR/web.err.log 를 확인해 주세요." >&2; exit 1
    fi
    sleep 2
  done
  echo "웹 서버가 준비되지 않았습니다. $LOG_DIR/web.err.log 를 확인해 주세요." >&2; exit 1
}

open_browser() {
  if command -v open >/dev/null 2>&1; then open "$WEB_URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$WEB_URL" >/dev/null 2>&1 || true
  fi
}

mkdir -p "$RUNTIME_ROOT" "$LOG_DIR" "$OUTPUT_DIR"

case "$ACTION" in
  start)
    sync_chroma_index
    start_model
    start_web
    (( NO_BROWSER )) || open_browser
    ;;
  stop)
    stop_owned_process "$WEB_PID_PATH" "python|uvicorn" "웹 서버"
    stop_owned_process "$MODEL_PID_PATH" "llama-server" "Qwen3 모델 서버"
    ;;
  status)
    if web_ready;   then echo "웹 서버: 정상 ($WEB_URL)";   else echo "웹 서버: 중지"; fi
    if model_ready; then echo "Qwen3: 정상 ($MODEL_URL)";   else echo "Qwen3: 중지"; fi
    echo "실행 기록: $RUNTIME_ROOT"
    ;;
esac
