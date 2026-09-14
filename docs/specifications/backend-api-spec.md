# AI 체력 코치 — Backend API 명세서

> **문서 성격 — 먼저 읽을 것.** 본 문서는 2차 회의 시점에 프론트엔드 담당자가 백엔드에 요청한 **설계 초안**이며, 현재 구현과 다릅니다.
> §1~§3에 명세된 엔드포인트 3개(`POST /api/fitness/analyze`, `POST /api/coaching`, `GET /api/videos`)는 **아직 구현되지 않았습니다.**
> 아래 Base URL(8000)과 §7 기술 스택도 현재 구현과 다릅니다 — 실제 서버는 8501 포트, llama.cpp Qwen3 로컬 모델과 chromadb 직접 호출을 씁니다.
>
> **실제로 제공되는 라우트는 §8, 프론트엔드와의 불일치는 §9를 보십시오.** §1~§7은 요청 사항의 이력으로 보존합니다.

---

## Base URL

```
http://localhost:8000
```

---

## 1. 체력 분석 요청

### `POST /api/fitness/analyze`

사용자의 기본 정보와 체력 측정값을 전달하면, 또래 비교 기반 분석 결과를 반환합니다.

#### Request Body

```json
{
  "age": 25,
  "gender": "female",
  "measurement_type": "home",
  "strength": 25,
  "endurance": 30,
  "cardio": 48,
  "flexibility": 12,
  "agility": 14
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| age | int | ✅ | 나이 (10~80) |
| gender | string | ✅ | "male" 또는 "female" |
| measurement_type | string | ✅ | "center" (센터) 또는 "home" (홈) |
| strength | number | ✅ | 근력 (팔굽혀펴기 횟수) |
| endurance | number | ✅ | 근지구력 (윗몸일으키기 횟수) |
| cardio | number | ✅ | 심폐지구력 (왕복달리기 횟수) |
| flexibility | number | ✅ | 유연성 (앉아 윗몸 굽히기 cm) |
| agility | number | ✅ | 민첩성 (반복횡뛰기 횟수 또는 초) |

#### Response Body

```json
{
  "overall_score": 72,
  "peer_group": "20대 여성",
  "factors": [
    {
      "key": "strength",
      "label": "근력",
      "value": 25,
      "status": "good",
      "status_label": "좋음",
      "score": 85,
      "peer_avg": 18,
      "peer_p25": 10,
      "peer_p75": 25
    },
    {
      "key": "cardio",
      "label": "심폐지구력",
      "value": 48,
      "status": "normal",
      "status_label": "보통",
      "score": 70,
      "peer_avg": 45,
      "peer_p25": 35,
      "peer_p75": 55
    }
  ],
  "weak_factors": [
    {
      "key": "flexibility",
      "label": "유연성",
      "score": 45
    }
  ]
}
```

---

## 2. AI 코칭 요청

### `POST /api/coaching`

체력 분석 결과를 기반으로 RAG 검색 + LLM 코칭을 반환합니다.

#### Request Body

```json
{
  "age": 25,
  "gender": "female",
  "weak_factors": ["flexibility", "cardio"],
  "analysis_summary": {
    "strength": "good",
    "endurance": "normal",
    "cardio": "bad",
    "flexibility": "bad",
    "agility": "normal"
  }
}
```

#### Response Body

```json
{
  "summary": "분석 결과 유연성과 심폐지구력 개선이 필요합니다.",
  "priority_factor": "flexibility",
  "recommendations": [
    {
      "exercise_name": "앉아 윗몸 앞으로 굽히기",
      "reason": "허리와 햄스트링 유연성 향상에 효과적입니다.",
      "method": "다리를 앞으로 펴고 앉아 천천히 앞으로 숙입니다.",
      "caution": "반동을 주지 않고 천천히 진행하세요.",
      "tags": ["유연성", "스트레칭"],
      "video_url": "http://openapi.kspo.or.kr/web/video/0AUDLJ08S_00351.mp4"
    }
  ]
}
```

---

## 3. 운동 영상 검색

### `GET /api/videos?query={검색어}`

운동 관련 영상 메타데이터를 반환합니다.

#### Query Parameters

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| query | string | ✅ | 검색어 (예: "스쿼트", "유연성") |

#### Response Body

```json
{
  "total": 1,
  "videos": [
    {
      "video_id": "0AUDLJ08S_00351",
      "title": "국민체력100 운동 가이드",
      "description": "공식 운동 가이드 영상",
      "streaming_url": "http://openapi.kspo.or.kr/web/video/0AUDLJ08S_00351.mp4",
      "tags": ["공식 가이드", "국민체력100"],
      "source": "국민체육진흥공단"
    }
  ]
}
```

---

## 4. 에러 응답 형식

모든 API는 에러 시 다음 형식으로 응답합니다.

```json
{
  "detail": "에러 메시지",
  "error_code": "VALIDATION_ERROR"
}
```

| HTTP 코드 | 설명 |
|---|---|
| 400 | 요청 데이터 유효성 검사 실패 |
| 422 | Pydantic 스키마 검증 실패 |
| 500 | 서버 내부 에러 |

---

## 5. CORS 설정

프론트엔드 개발 환경에서의 접근을 위해 백엔드에 다음 CORS를 설정합니다.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 개발 시에만 *
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 6. 프론트엔드 연동 방법

`mock-data.js`의 함수를 `fetch()` 호출로 교체합니다.

### 변경 전 (Mock)

```javascript
var result = analyzePhysicalFitness(userInput);
renderResult(result);
```

### 변경 후 (실제 API)

```javascript
fetch('/api/fitness/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(userInput)
})
.then(res => res.json())
.then(result => renderResult(result));
```

---

## 7. 필요 기술 스택

| 구분 | 기술 | 용도 |
|---|---|---|
| 서버 프레임워크 | FastAPI | REST API 서버 |
| 데이터 검증 | Pydantic | Request/Response 스키마 |
| AI/RAG | LangChain + ChromaDB | 운동 콘텐츠 검색 |
| LLM | OpenAI GPT 또는 Google Gemini | AI 코칭 응답 생성 |
| 영상 API | 공공데이터포털 동영상 API | 운동 영상 메타데이터 |
| 데이터 분석 | Pandas + NumPy | 체력 통계 분석 |
| CORS | FastAPI CORSMiddleware | 프론트엔드 접근 허용 |

> §7의 스택은 요청 초안 기준이다. 현재 구현은 LangChain·OpenAI·Gemini를 쓰지 않고 llama.cpp(Qwen3-4B-Q4_K_M) 로컬 서버와 chromadb를 직접 호출하며, 동일 출처로 서빙하므로 CORSMiddleware도 적용하지 않는다.

---

## 8. 실제 구현 라우트 (2026-09-13 기준)

`apps/api/src/fitness_web_server.py`와 `apps/api/src/fitness_mvp.py`에서 추출한 현행 라우트다. **동작 기준은 §1~§3이 아니라 이 표다.**

### 8-1. fitness_web_server.py — `@app`

| 메서드 | 경로 | 핸들러 |
|---|---|---|
| GET | `/` | `index` — `AI_FITNESS_FRONTEND_FILE`이 가리키는 HTML 반환 |
| GET | `/video-player` | `video_player` |
| GET | `/api/health` | `health` |
| GET | `/api/center-percentile-status` | `center_percentile_status` |
| GET | `/api/age-bmi-recommendation-status` | `age_bmi_recommendation_status` |
| GET | `/api/center-percentile-inputs` | `center_percentile_inputs` |
| POST | `/api/center-percentiles` | `center_percentiles` |
| GET | `/api/options` | `options` |
| POST | `/api/options` | `filtered_options` |
| GET | `/api/video-link-audit` | `video_link_audit` |
| POST | `/api/chat` | `chat` |
| POST | `/api/coach` | `coach` |

### 8-2. fitness_mvp.py — `@router` (prefix `/api/mvp`)

| 메서드 | 경로 | 핸들러 |
|---|---|---|
| POST | `/api/mvp/login` | `login` |
| POST | `/api/mvp/signup` | `signup` |
| GET | `/api/mvp/profile` | `profile` 조회 |
| PUT | `/api/mvp/profile` | `profile` 수정 |
| GET | `/api/mvp/catalog` | `catalog` |
| POST | `/api/mvp/evaluate` | `evaluate` |
| GET | `/api/mvp/history` | `history` |
| POST | `/api/mvp/chat` | `chat` |
| POST | `/api/mvp/report-summary` | `report_summary` |
| GET | `/api/mvp/recommendation-videos/{item_code}` | `recommendation_videos` |

`prefix="/api/mvp"`는 `fitness_mvp.py`의 `APIRouter` 선언에 있다. 이 접두사 때문에 프론트엔드가 `/api/report-summary`로 호출하면 404가 난다(§9 참조).

### 8-3. 정적 자원 마운트

| 마운트 | 대상 디렉터리 | 조건 |
|---|---|---|
| `/css` | `apps/web/css` | 디렉터리 존재 시에만 마운트 |
| `/js` | `apps/web/js` | 디렉터리 존재 시에만 마운트 |

기본 위치는 저장소 루트의 `apps/web`이며 `AI_FITNESS_WEB_DIR`로 변경한다. 디렉터리가 없으면 마운트를 조용히 건너뛰므로, 정적 자원이 404라면 이 환경변수부터 확인한다.

---

## 9. 미해결 불일치

프론트엔드(`apps/web`, frontend_v3)가 실제로 호출하는 6개와 서버 라우트를 대조한 결과다.

| 프론트엔드 호출 | 호출부 | 서버 실제 상태 | 판정 |
|---|---|---|---|
| `/api/health` | `js/app.js` | `GET /api/health` | 일치 |
| `/api/coach` | `js/app.js` | `POST /api/coach` | 일치 |
| `/api/chat` | `js/app.js` | `POST /api/chat` | 일치 |
| `/api/center-percentiles` | `js/services/percentile-service.js` | `POST /api/center-percentiles` | 일치 |
| `/api/report-summary` | `js/services/report-service.js` | **`/api/mvp/report-summary`만 존재** | **404** |
| `/api/top-videos/{category}` | `js/services/video-service.js` | **라우트 없음** | **404** |

두 서비스 모두 실패 시 `'*-api-unavailable'` 예외를 던지고 호출부에서 잡으므로 화면이 죽지는 않는다. 대신 **리포트 요약과 영상 추천이 조용히 빈 상태**가 된다.

**해결 방향 미결정.** 프론트엔드 URL을 고칠지, 백엔드에 alias 라우트를 추가할지 백엔드 최신본을 받은 뒤 정한다. 결정 시 이 절을 갱신한다.
