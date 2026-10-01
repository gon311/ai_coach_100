# 데이터·RAG·AI 서버 평가 실행 안내

이 저장소에는 AI 서버 하네스와 평가 코드, 회귀 테스트, 공개 집계 규준 DB(`apps/api/artifacts/fitness_percentile.db`)만 포함합니다. 사용자 측정 DB, 원본 공공데이터, RAG 원문/Chroma 인덱스, 모델 파일, 공식 골드셋, 응답·채점 결과는 포함하지 않습니다. 공식 골드셋은 담당자의 검수를 거쳐 별도로 제공받아야 합니다.

평가 진입점은 `apps/api/src/fitness_evaluation_harness.py`입니다. 서비스 코드와 평가 코드는 동일한 `apps/api/src` 안에 있으며, 평가 결과는 기본적으로 Git에서 제외되는 `apps/api/runtime` 아래의 통합 DB에 기록됩니다. `--export-files`를 지정할 때만 개별 파일을 추가로 내보냅니다.

Windows PowerShell 실행 예시:

```powershell
$env:PYTHONPATH = (Resolve-Path 'apps/api/src').Path
$env:AI_FITNESS_NORM_DB = (Resolve-Path 'apps/api/artifacts/fitness_percentile.db').Path
$env:AI_FITNESS_RAG_DB = 'C:\path\to\rag_documents.sqlite'
$env:AI_FITNESS_USER_DB = 'C:\path\to\user_records.db'

python apps/api/src/fitness_evaluation_harness.py `
  --goldset-jsonl 'C:\path\to\goldset_official_145.jsonl' `
  --preflight-only
```

실제 평가에는 실행 중인 서버 주소를 `--base-url`로, 비교 가능한 기존 응답 또는 서버 주소를 `--baseline-responses` / `--baseline-base-url`로 지정하고 고유한 `--run-id`를 부여합니다. 같은 질문·프로필·설정의 baseline과 improved만 비교해야 합니다. RAGAS가 필요하면 별도 평가 환경에 `apps/api/requirements-eval.txt`를 설치하고 `OPENAI_API_KEY`를 설정한 뒤 `--run-ragas`를 사용합니다. 검색 지표는 검수된 질문별 `gold_document_ids`가 있어야 공식 수치가 됩니다.

회귀 테스트는 `python -m pytest apps/api/tests`로 실행합니다. 일부 테스트는 위의 외부 DB·골드셋이 있을 때만 완전히 검증됩니다. 테스트 통과 자체가 실서버 145건 재수집이나 RAGAS 실행을 뜻하지는 않습니다.
