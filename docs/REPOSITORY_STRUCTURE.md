# 저장소 구조 안내

이 저장소는 AI 체력 코치의 프론트엔드, FastAPI 백엔드, 데이터 가공 코드, 평가 자료와 공모전·포트폴리오 문서를 관리합니다. 대용량 모델과 검색 인덱스, 원본 공공데이터, 사용자 데이터와 원본 운영 로그는 공개 저장소에 포함하지 않습니다.

## 전체 구조

```text
ai_coach_100/
├── apps/
│   ├── web/                         # Vue 3 반응형 프론트엔드
│   └── api/                         # FastAPI·RAG·로컬 LLM 백엔드
│       ├── src/                     # 서비스·데이터 생성·평가 Python 코드
│       ├── tests/                   # 단위·계약 테스트
│       ├── scripts/                 # Windows/macOS/Linux 실행 스크립트
│       ├── prompts/                 # 챗봇 시스템 프롬프트
│       ├── artifacts/               # Git 공개가 가능한 규준 DB
│       ├── source_data/             # 공개 가능한 추천 규칙 입력 데이터
│       └── KIMMIN_BACKEND_WORKLOG.md # 김민의 1~5주차 백엔드 작업 기록
├── data/
│   ├── reference/                   # 서비스 참조용 규칙·정규화·영상 데이터
│   ├── scripts/                     # RAG 원문 DB 생성 노트북
│   └── README.md                    # 데이터 포함·제외 및 재현 원칙
├── docs/
│   ├── planning/                    # 기획·회의·정규화·HOME 측정 기준
│   ├── research/                    # 공공데이터 EDA 보고서와 차트
│   ├── frontend/                    # P1~P4 설계·검증 기록과 배포 화면
│   ├── competition/                 # 공모전 자료와 README 서비스 화면
│   ├── deployment/                  # GCP 구축·배포·서빙 증빙 요약
│   ├── specifications/              # 백엔드 API 설계 이력과 구현 대조
│   ├── PORTFOLIO.md                 # 프로젝트 판단·검증·회고
│   ├── TEAM_ROLES.md                # 팀원별 역할과 관련 산출물
│   └── REPOSITORY_STRUCTURE.md      # 현재 문서
├── evaluation/                      # 평가 계획 v1~v3와 검토자 안내
├── .env.example                     # 로컬 실행 환경변수 예시
├── .gitignore                       # 비공개·대용량·생성 파일 제외 규칙
└── README.md                        # 프로젝트 소개와 주요 결과
```

## 프론트엔드

| 경로 | 내용 |
|---|---|
| `apps/web/index.html` | Vue 3 및 프론트 자산을 불러오는 진입 HTML |
| `apps/web/css/style.css` | 모바일·데스크톱 반응형 UI와 컴포넌트 스타일 |
| `apps/web/js/app.js` | PAR-Q, 측정, 리포트, 추천, 인증·기록과 챗봇 화면 흐름 |
| `apps/web/js/config/` | 측정항목, 레이더 차트, 공식 영상 설정 |
| `apps/web/js/services/` | 백분위, 리포트, 영상 관련 API 요청 |
| `apps/web/js/utils/` | 측정값·레이더·YouTube 공통 처리 함수 |
| `apps/web/js/data/mock-data.js` | 화면 개발·검증용 예시 데이터 |

현재 화면은 P4의 인증·PAR-Q·측정·리포트 흐름까지 반영된 반응형 프론트엔드입니다. 프론트에서 API 경로를 변경할 때는 `apps/api/src/fitness_web_server.py`, `apps/api/src/fitness_mvp.py`의 실제 라우트와 함께 확인합니다.

## 백엔드와 실행 스크립트

| 경로 | 내용 |
|---|---|
| `apps/api/KIMMIN_BACKEND_WORKLOG.md` | 김민의 1~5주차 백엔드 작업 과정과 검증 기록 |
| `apps/api/src/fitness_web_server.py` | FastAPI 앱 진입점, 정적 화면 서빙, 코칭·백분위 API |
| `apps/api/src/fitness_mvp.py` | `/api/mvp` 인증, 프로필, 기록, 추천, 대화 API |
| `apps/api/src/center_percentile.py` | CENTER·HOME 백분위 조회와 표시 기준 |
| `apps/api/src/age_bmi_recommendations.py` | 연령·성별·BMI 기반 구조화 추천 |
| `apps/api/src/qwen3_grounded_harness.py` | 로컬 Qwen3 답변 생성과 근거 제한 |
| `apps/api/src/rag_data_roles.py` | RAG 데이터 역할과 검색 대상 구분 |
| `apps/api/src/rag_index_contract.py` | Chroma 인덱스 계약과 검증 |
| `apps/api/src/evaluate_rag.py` | 자동평가 실행 로직 |
| `apps/api/src/build_*.py` | 규준·추천 규칙·DuckDB·Chroma 생성 코드 |
| `apps/api/tests/` | 백분위·추천·코칭·RAG·웹 서버 단위 및 계약 테스트 |
| `apps/api/prompts/chatbot_system_prompt.md` | 챗봇의 근거·안전·응답 정책 |
| `apps/api/requirements.txt` | FastAPI, Chroma, Sentence Transformers 등 실행 의존성 |
| `apps/api/requirements-dev.txt` | 테스트·개발 의존성 |

### 실행 스크립트

| 구분 | Windows | macOS·Linux |
|---|---|---|
| 배포 패키지 준비 | `SETUP_IF_NEEDED.ps1` | `SETUP_IF_NEEDED.sh` |
| 배포 패키지 원클릭 시작 | `START_AI_FITNESS.ps1` | `START_AI_FITNESS.sh` |
| 배포 패키지 종료 | `STOP_AI_FITNESS.ps1` | `STOP_AI_FITNESS.sh` |
| 통합 서버 직접 관리 | `server.ps1 start/stop/status` | `server.sh start/stop/status` |

`START_AI_FITNESS.*`는 최종 배포 패키지의 `tools/`, `frontend1/`, 모델·아티팩트 구조를 전제로 보존한 래퍼이며 웹 서버 `8501`, 모델 서버 `8089`를 사용합니다. `server.ps1`과 `server.sh`를 직접 실행할 때의 모델 서버 기본값은 `8080`입니다.

공개 저장소에서 직접 실행하려면 `.env.example`의 환경변수로 모델, 프론트엔드, Chroma와 런타임 경로를 현재 체크아웃에 맞게 지정해야 합니다. 대용량 자산이 포함되지 않으므로 스크립트만 실행해서는 전체 서비스가 시작되지 않습니다.

## 공개 데이터와 제외 자산

### Git에 포함하는 데이터

| 경로 | 포함 내용 |
|---|---|
| `apps/api/artifacts/fitness_percentile.db` | 공개 가능한 백분위 규준 DB |
| `apps/api/source_data/KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv` | 연령·BMI 추천 규칙 입력 데이터 |
| `data/reference/normalization/` | 측정항목, 규준과 HOME 백분위 오차 구간 |
| `data/reference/fitness-rules/` | 생애주기·체력 수준별 판정 기준 |
| `data/reference/videos/` | 국민체력100 측정방법·표준운동·영상 메타데이터 |
| `data/reference/standards/` | 국내 성인 BMI 기준과 측정 데이터 사전 |
| `data/scripts/build_rag_documents.ipynb` | RAG 원문 DB 생성·분석 절차 |

### Git에서 제외하는 자산

| 자산 | 기본 위치 또는 설정 |
|---|---|
| Qwen3 GGUF 모델 | `apps/api/models/` 또는 `AI_FITNESS_MODEL_PATH` |
| 임베딩 모델 | `apps/api/models/ko-sroberta-multitask/` 등 별도 배치 |
| Chroma 인덱스 | `apps/api/artifacts/chroma/` 또는 `AI_FITNESS_CHROMA_DIR` |
| RAG 원문 DB와 생성 DB | `apps/api/artifacts/` 아래 별도 배치 |
| 사용자·세션 DB | `AI_FITNESS_RUNTIME_ROOT` 등 로컬 런타임 영역 |
| 월별·종합 원본 공공데이터 | `data/raw/` |
| DuckDB, 압축 배포본, 로그와 PID | `.gitignore`에 따라 제외 |
| GCP 원본 감사·접속 로그 | 개인 이메일과 외부 IP가 있어 비공개 보관 |

세부 데이터 운영 원칙과 재현 절차는 [`data/README.md`](../data/README.md)를 참고합니다.

## 문서와 이미지 자산

| 경로 | 내용 |
|---|---|
| `docs/planning/` | 프로젝트 개요, 회의 기록, 측정 정규화와 HOME 측정 기준 |
| `docs/research/` | 데이터 EDA 보고서와 시각화 결과 |
| `docs/frontend/` | P1~P4 설계, 의사결정, 계약·브라우저 검증 기록 |
| `docs/frontend/assets/service-*-live.png` | 기존 GCP 배포 화면 원본 |
| `docs/frontend/assets/cards/` | README 표에 사용하는 `1200×900` 배포 화면 사본 |
| `docs/competition/assets/` | 공모전 증빙자료에서 선별한 서비스 화면 원본 |
| `docs/competition/assets/cards/` | README 표에 사용하는 `1200×900` 동일 규격 사본 |
| `docs/deployment/GCP_SERVING_EVIDENCE.md` | VM 생성, systemd 기동과 HTTP 응답 근거를 개인정보 없이 요약한 문서 |
| `docs/specifications/backend-api-spec.md` | 초기 API 요청안과 현재 구현 라우트·불일치 대조 |
| `docs/TEAM_ROLES.md` | 팀원별 담당 업무, 관련 코드·문서와 근거 |
| `docs/PORTFOLIO.md` | 데이터·추천·통합·평가 과정과 남은 한계 |
| `evaluation/` | 평가 계획 변경 이력과 블라인드 검토자 안내 |

서비스 화면의 원본은 보존합니다. `cards/` 이미지는 표에서 화면 크기를 통일하기 위한 표시용 사본이며, 원본 비율을 유지한 채 흰색 여백을 더한 `1200×900` 규격입니다.

## 작업별 수정 위치

| 작업 | 우선 확인할 경로 |
|---|---|
| 화면·반응형 UI 수정 | `apps/web/`, `docs/frontend/` |
| API·인증·기록 수정 | `apps/api/src/fitness_web_server.py`, `fitness_mvp.py`, `apps/api/tests/` |
| 백분위·추천 규칙 수정 | `apps/api/src/center_percentile.py`, `age_bmi_recommendations.py`, `data/reference/` |
| RAG·LLM 수정 | `qwen3_grounded_harness.py`, `rag_data_roles.py`, `rag_index_contract.py`, `apps/api/prompts/` |
| 데이터 재생성 | `apps/api/src/build_*.py`, `data/scripts/`, `data/README.md` |
| 평가 기준·결과 수정 | `evaluation/`, `apps/api/src/evaluate_rag.py`, `docs/PORTFOLIO.md` |
| 팀 역할·기여 수정 | `docs/TEAM_ROLES.md`, `README.md` |
| 배포 증빙 수정 | `docs/deployment/`, `README.md` |
| README 서비스 화면 수정 | `docs/frontend/assets/cards/`, `docs/competition/assets/cards/`, `README.md` |

## 변경 시 확인사항

1. 작업 전 현재 브랜치와 원격 변경사항을 확인합니다.
2. 기능을 변경하면 관련 `apps/api/tests/`와 프론트 계약 검증도 함께 확인합니다.
3. API 경로 또는 응답을 변경하면 `docs/specifications/backend-api-spec.md`의 구현 대조표를 갱신합니다.
4. 데이터·모델·로그를 추가하기 전에 `.gitignore` 대상과 공개 가능 여부를 확인합니다.
5. 대용량 원본, 모델, 사용자 정보, 비밀값과 개인 식별 로그는 커밋하지 않습니다.
6. 역할이나 성과를 수정하면 `README.md`, `docs/TEAM_ROLES.md`와 근거 문서를 함께 맞춥니다.
7. 서비스 화면을 교체하면 원본과 `cards/` 사본을 구분하고 README 링크를 확인합니다.

## 현재 알려진 연동 주의사항

- `docs/specifications/backend-api-spec.md`의 §1~§7은 초기 요청안이며, 현재 구현은 같은 문서의 §8 이후를 기준으로 확인합니다.
- 프론트의 `/api/report-summary` 요청과 백엔드의 `/api/mvp/report-summary` 라우트는 아직 일치하지 않습니다.
- 프론트의 `/api/top-videos/{category}`에 대응하는 백엔드 라우트는 현재 없습니다.
- 실행 스크립트는 공개 저장소에 없는 모델·Chroma·RAG DB를 별도로 배치해야 정상 동작합니다.
- 환경별 자산 위치가 다르면 `.env.example`의 `AI_FITNESS_*` 경로를 명시적으로 설정합니다.
