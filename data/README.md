# 데이터 운영 원칙

## Git에 포함하는 데이터

- `reference/normalization`: 서비스 조회에 필요한 규준·종목·자가측정 오차 구간 CSV
- `reference/fitness-rules`: 체력 수준·연령대별 기준 CSV
- `reference/videos`: 국민체력100 운동 영상 메타데이터 JSON
- `reference/standards`: BMI 기준과 측정항목 데이터 사전 JSON

## Git에서 제외하는 데이터

- 월별·종합 원본 공공데이터 CSV
- 압축 배포본, DuckDB/SQLite DB, Chroma 벡터 인덱스
- Qwen GGUF·임베딩 모델 등 다운로드 가능한 모델 파일
- 사용자 측정·문진·대화 기록

## 재현 절차

1. 공공데이터 원본은 별도 팀 공유 드라이브 또는 공식 제공처에서 내려받아 `data/raw/`에 둡니다.
2. RAG 원문 DB 생성 절차는 `data/scripts/build_rag_documents.ipynb`에 있으며, 백엔드 데이터 생성 코드는 `apps/api/src/build_*.py`에 있습니다. 이 파일들은 `apps/api/`를 런타임 루트로 가정하므로 위치를 옮기지 않습니다.
3. `apps/api/artifacts/fitness_percentile.db`는 백분위 조회에 필요한 공개 규준 DB로 Git에 포함합니다. 사용자 기록 DB·대용량 RAG 인덱스·모델은 Git이 아닌 팀 저장소 또는 릴리스 자산으로 배포합니다.

원본 데이터의 출처, 취득일, 라이선스와 파일 검증값은 새 데이터 추가 시 이 문서에 함께 기록합니다.
