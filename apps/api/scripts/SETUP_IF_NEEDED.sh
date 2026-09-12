#!/usr/bin/env bash
# 다른 컴퓨터로 옮겼을 때 Python 패키지·llama-server 준비 (macOS) — SETUP_IF_NEEDED.ps1 대응
# 패키지 폴더 안에 .venv 를 만들고, llama.cpp 는 Homebrew 로 설치합니다.
set -euo pipefail
PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT="$PACKAGE_ROOT/AI_체력_코치_Qwen3_4B_Q4_배포"
export AI_FITNESS_RUNTIME_ROOT="${AI_FITNESS_RUNTIME_ROOT:-$PACKAGE_ROOT/.runtime_data}"
export AI_FITNESS_VENV_DIR="$PACKAGE_ROOT/.venv"
bash "$DEPLOYMENT/tools/setup_ai_fitness.sh"
echo "설치 완료. START_AI_FITNESS.sh 를 실행하세요."
