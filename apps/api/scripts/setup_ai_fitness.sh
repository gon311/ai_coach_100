#!/usr/bin/env bash
# AI 체력 코치 — macOS 최초 설치 (Windows용 tools/setup_ai_fitness.ps1 대응)
#   1) Python 3.10+ 확인 → 전용 venv 생성 → requirements.txt 설치
#   2) llama-server 확인 (없으면 Homebrew로 llama.cpp 설치)
#   3) 배포 필수 파일 확인
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="${AI_FITNESS_RUNTIME_ROOT:-$HOME/ai_fitness_qwen3_runtime}"
VENV_DIR="${AI_FITNESS_VENV_DIR:-$RUNTIME_ROOT/venv}"
VENV_PYTHON="$VENV_DIR/bin/python"

find_base_python() {
  if [[ -n "${AI_FITNESS_BASE_PYTHON:-}" && -x "$AI_FITNESS_BASE_PYTHON" ]]; then
    echo "$AI_FITNESS_BASE_PYTHON"; return
  fi
  local candidate
  for candidate in python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local path; path="$(command -v "$candidate")"
      if "$path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$path"; return
      fi
    fi
  done
  cat >&2 <<'EOF'
Python 3.10 이상을 찾을 수 없습니다. 다음 중 하나로 설치한 뒤 다시 실행하세요.
  brew install python@3.12
또는 https://www.python.org/downloads/macos/ 에서 설치
EOF
  exit 1
}

echo "== [1/3] Python 환경"
BASE_PYTHON="$(find_base_python)"
echo "기본 Python: $BASE_PYTHON ($("$BASE_PYTHON" --version 2>&1))"
mkdir -p "$RUNTIME_ROOT"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "AI 체력 코치 전용 Python 환경을 만듭니다: $VENV_DIR"
  "$BASE_PYTHON" -m venv "$VENV_DIR"
fi
echo "필수 Python 패키지를 설치합니다. 처음 한 번은 인터넷 연결이 필요합니다."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -c "import fastapi,uvicorn,chromadb,sentence_transformers,pydantic; print('Python package check: OK')"
"$VENV_PYTHON" - <<'EOF'
try:
    import torch
    print("PyTorch", torch.__version__, "| MPS(Apple GPU) 사용 가능:", torch.backends.mps.is_available())
except Exception as exc:  # noqa: BLE001
    print("PyTorch 확인 생략:", exc)
EOF

echo
echo "== [2/3] llama-server (Qwen3 모델 서버)"
LLAMA_FOUND=""
for candidate in "${AI_FITNESS_LLAMA_SERVER:-}" "$PROJECT_ROOT/runtime/llama/llama-server" /opt/homebrew/bin/llama-server /usr/local/bin/llama-server; do
  [[ -n "$candidate" && -x "$candidate" ]] && { LLAMA_FOUND="$candidate"; break; }
done
if [[ -z "$LLAMA_FOUND" ]] && command -v llama-server >/dev/null 2>&1; then
  LLAMA_FOUND="$(command -v llama-server)"
fi
if [[ -z "$LLAMA_FOUND" ]]; then
  if command -v brew >/dev/null 2>&1; then
    echo "llama-server가 없어 Homebrew로 llama.cpp를 설치합니다 (Metal 가속 포함)."
    brew install llama.cpp
    LLAMA_FOUND="$(command -v llama-server || true)"
  fi
fi
if [[ -z "$LLAMA_FOUND" ]]; then
  cat >&2 <<'EOF'
llama-server를 설치하지 못했습니다. Homebrew 설치 후 `brew install llama.cpp` 를 실행하거나,
https://github.com/ggml-org/llama.cpp/releases 의 macOS 바이너리에서 llama-server 를
runtime/llama/llama-server 로 복사하세요 (복사 후 chmod +x 필요).
EOF
  exit 1
fi
echo "llama-server: $LLAMA_FOUND"

echo
echo "== [3/3] 배포 필수 파일 확인"
required=(
  "models/Qwen3-4B-Q4_K_M.gguf"
  "models/ko-sroberta-multitask/model.safetensors"
  "artifacts/rag_documents.sqlite"
  "artifacts/chroma/BUILD_COMPLETE.json"
  "artifacts/center_percentile_norms.sqlite"
  "artifacts/age_bmi_recommendation_rules.sqlite"
  "artifacts/korean_adult_bmi_standards.json"
)
for rel in "${required[@]}"; do
  if [[ ! -f "$PROJECT_ROOT/$rel" ]]; then
    echo "배포 필수 파일이 없습니다: $PROJECT_ROOT/$rel" >&2; exit 1
  fi
done
# source_data 는 재구축용이라 실행에는 필수가 아니므로 경고만 출력
for rel in "source_data/KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv"; do
  [[ -f "$PROJECT_ROOT/$rel" ]] || echo "(참고) 재구축용 파일 없음: $rel"
done

echo
echo "설치 및 배포 파일 확인 완료"
echo "venv: $VENV_PYTHON"
echo "이제 START_AI_FITNESS_SERVER.command 를 더블클릭하거나 tools/server.sh start 를 실행하세요."
