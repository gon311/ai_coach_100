# 저장소 구조 안내

팀 작업은 이 저장소의 `main` 브랜치를 기준으로 합니다. 원본 자료는 Git에 넣지 않고, 실행·검토에 필요한 소스와 소형 참조 데이터만 관리합니다.

```text
ai_coach_100/
├── apps/
│   ├── web/                 # 현재 반응형 웹 화면 (frontend_v3 P4)
│   └── api/                 # Python/FastAPI 기반 백엔드
├── data/
│   ├── reference/           # 서비스 참조용 소형 데이터
│   └── scripts/             # RAG 원문 DB 생성 노트북
├── docs/                    # 기획·설계·회의·연구 문서
├── evaluation/              # AI 코칭 평가 계획과 검토 자료
├── .env.example             # 환경변수 예시
├── .gitignore               # Git 제외 규칙
└── README.md                # 프로젝트 개요와 현재 상태
```

## 앱 코드

| 경로 | 내용 | 담당 작업 예시 |
|---|---|---|
| `apps/web/` | 최신 프론트엔드 화면 | 화면·UX·API 호출·스타일 수정 |
| `apps/web/index.html` | 웹 진입 HTML | 전역 화면 구조·스크립트 로드 순서 |
| `apps/web/css/style.css` | 전체 스타일 | 반응형·컴포넌트 스타일 |
| `apps/web/js/app.js` | Vue 화면 상태와 사용자 흐름 | 측정·인증·리포트 화면 로직 |
| `apps/web/js/config/` | 측정·레이더·영상 설정 | 화면에 쓰는 기준값·표시 설정 |
| `apps/web/js/services/` | 백엔드 API 호출 | API 요청·응답 처리 |
| `apps/web/js/utils/` | 화면 보조 함수 | 측정·레이더·YouTube 공통 로직 |
| `apps/api/src/` | FastAPI·코칭·RAG·규준 조회 Python 코드 | 백엔드 기능·테스트 대상 로직 |
| `apps/api/tests/` | Python 테스트 | 기능 변경 시 테스트 추가·수정 |
| `apps/api/scripts/` | 기존 로컬 실행 스크립트 | 백엔드 최신본 기준으로 추후 경로 정비 필요 |
| `apps/api/prompts/` | 챗봇 시스템 프롬프트 | 프롬프트 변경·평가 시 버전 관리 |
| `apps/api/artifacts/fitness_percentile.db` | 공개 체력 규준 DB | 백분위 조회에 필요, Git 포함 |

## 데이터

| 경로 | 포함 내용 | Git 처리 |
|---|---|---|
| `data/reference/normalization/` | 규준·종목·홈 측정 오차 구간 CSV | 포함 |
| `data/reference/fitness-rules/` | 연령대별 체력 기준 CSV | 포함 |
| `data/reference/videos/` | 국민체력100 운동 영상 메타데이터 JSON | 포함 |
| `data/reference/standards/` | BMI 기준·측정 항목 데이터 사전 | 포함 |
| `apps/api/source_data/` | 연령·BMI 추천 규칙 입력 CSV 1개 | 지정 파일만 포함 |
| `data/scripts/build_rag_documents.ipynb` | RAG 원문 DB 생성 절차 | 포함 |
| `data/raw/` | 월별·종합 원본 공공데이터 | 제외 |

원본 공공데이터, 사용자 측정·문진 기록, 모델 파일, Chroma 인덱스, 대용량 RAG DB는 Git에 넣지 않습니다. 팀 노션 또는 공유 드라이브에서 별도로 관리합니다.

## 문서와 평가 자료

| 경로 | 내용 |
|---|---|
| `docs/planning/` | 프로젝트 개요, 회의록, 설계·정규화 기준 |
| `docs/research/` | EDA 보고서와 차트 |
| `docs/frontend/` | frontend_v3의 설계·검증·P4 변경 기록 |
| `docs/specifications/` | 백엔드 API 요청 초안과 실제 구현 라우트 대조 |
| `docs/competition/` | 공모전 관련 자료 |
| `evaluation/` | 평가 계획 v1~v3, 검토자 안내문 |

## 팀 작업 전 확인

1. 작업 전 `git pull`로 최신 `main`을 받습니다.
2. 프론트엔드 변경은 `apps/web/`, 백엔드 변경은 `apps/api/`에 반영합니다.
3. 데이터·모델·로그가 새로 생겼다면 먼저 `.gitignore` 대상인지 확인합니다.
4. 대용량 파일이나 사용자 정보는 커밋하지 않습니다.
5. API를 바꾸면 `docs/specifications/backend-api-spec.md`의 실제 구현 라우트 및 미해결 불일치도 함께 확인합니다.

## 현재 연동 주의사항

- `apps/web`은 frontend_v3 P4 기준입니다.
- 백엔드 최신본을 받기 전까지 `apps/api/scripts/`의 기존 폴더 경로는 수정 보류 상태입니다.
- `/api/report-summary`, `/api/top-videos/{category}`는 현재 프론트엔드와 백엔드의 주소가 일치하지 않습니다. 수정 전 `docs/specifications/backend-api-spec.md`의 “미해결 불일치”를 확인하세요.
