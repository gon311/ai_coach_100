# AI 체력 코치 — Backend API 명세서

> 프론트엔드와 백엔드 통신을 위한 REST API 명세입니다.
> 현재 프론트엔드는 Mock Data로 동작하며, 백엔드 완성 시 아래 API로 교체합니다.

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
