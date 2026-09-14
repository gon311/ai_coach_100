# Stage P4 — Flow, Auth & Report UX Refinement 최종 실행 지시서

## 0. 역할과 작업 범위

당신은 기존 서비스의 확정 정책, 데이터 구조, API 계약과 P3 반응형 레이아웃을 보존하면서 사용자 흐름과 화면 표현을 안전하게 개선하는 Senior Frontend Engineer다.

작업 대상:

```text
C:\Users\user\Desktop\frontend_v3
```

프로젝트:

```text
체력코치 AI 웹뷰 MVP
```

이번 단계:

```text
P4 — Flow, Auth & Report UX Refinement
```

핵심 목표:

```text
- 로그인/회원가입/비로그인 진입 UI 구성
- PAR-Q 7문항 single-page 전환
- HOME 측정 compact-card single-page 전환
- 센터 안내와 공식 사이트 연결 개선
- Report 정보구조 간소화
- Floating Chat UI 구현
- P3 반응형 구조 유지
```

이번 작업은 측정 정책, 계산식, Radar 의미, Backend percentile, 추천 로직 또는 API 계약을 변경하는 작업이 아니다.

프로젝트가 개발 중이라는 사실 자체는 충돌이나 중단 사유가 아니다. 미구현 기능과 현재 결함을 구분하고, Backend가 필요한 기능을 Frontend에서 임의로 완성하지 않는다.

---

## 1. Source of Truth

작업 전에 현재 프로젝트의 실제 코드와 최신 문서를 모두 확인한다.

우선순위:

```text
1. docs/06_DECISION_LOG.md의 최신 CONFIRMED/BLOCKED 결정
2. 현재 실행 코드와 실제 API 계약
3. P3 설계 및 검증 문서
4. P2 구조 및 검증 문서
5. P1 UX 설계 및 검증 문서
6. 이번 P4 작업 지시서
7. 과거 specs/plans
```

예외:

```text
P4에서 명시적으로 supersede한다고 선언한 UI 표현은
해당 P1 UI보다 우선한다.
```

코드와 CONFIRMED 정책이 충돌하면 어느 한쪽을 임의로 우선하지 않는다. 다음 형식으로 보고하고 영향을 받는 작업만 중단한다.

```text
CONFLICT

- 대상:
- 코드 근거:
- 문서 근거:
- 영향:
- 중단할 작업 범위:
```

과거에 `SUPERSEDED`된 정책이나 구조를 복원하지 않는다.

---

## 2. P4에서 명시적으로 대체하는 P1 UX

P4는 P1의 모든 UX를 그대로 유지하는 단계가 아니다.

다음 두 가지 화면 표현은 P4에서 명시적으로 대체한다.

```text
P1:
PAR-Q one-question-at-a-time

P4:
PAR-Q 7문항 single-page
```

```text
P1:
Measurement Dashboard → Active Measurement
한 종목 집중 입력

P4:
HOME compact measurement cards
전체 항목 single-page 입력
```

이 대체 범위는 화면 표현과 입력 진행 방식에만 적용한다.

변경하지 않는 항목:

```text
- PAR-Q 7문항 원문
- PAR-Q YES/NO 의미와 판정
- Adult/Senior 측정 배터리
- raw measurement data
- measurement validation
- optional grip 정책
- Radar 계산과 의미
- Backend API 계약
- percentile 권한
```

그 밖의 P0/P1/P2/P3 정책과 사용자 흐름은 유지한다.

---

## 3. 현재 기술 구조 유지

현재 P2 이후 구조를 유지한다.

```text
Vue 3 global build
CDN runtime
classic script loading
window.FitnessCoach namespace
no bundler
```

현재 파일 구조:

```text
docs/index.html
css/style.css

js/config/*
js/data/*
js/utils/*
js/services/*
js/app.js
```

금지:

```text
❌ React 전환
❌ TypeScript 도입
❌ Vite/Webpack 도입
❌ native ES module 전환
❌ JavaScript 구조 재분리
❌ 상태관리 라이브러리 추가
❌ 기존 API endpoint/method/payload 변경
❌ 임의 Auth endpoint 생성
❌ Radar 계산 로직 변경
❌ Frontend percentile 계산
```

---

## 4. 보호해야 할 비즈니스 정책

### 4.1 연령

```text
Adult: 만 19~64세
Senior: 만 65세 이상
Under-19: 측정 경로 차단
```

회원가입 가능 연령과 측정 가능 연령을 혼동하지 않는다.

회원가입 연령 제한은 현재 Backend 또는 제품 계약에서 확인되지 않으면 새로 만들지 않는다. 만 19세 미만의 측정 진입은 기존 정책대로 차단한다.

### 4.2 Adult HOME 배터리

필수 4종:

```text
- 앉아윗몸앞으로굽히기
- 교차윗몸일으키기
- 제자리멀리뛰기
- 10m 4회 왕복달리기
```

선택:

```text
- 악력
```

10m 4회 왕복달리기 raw 값은 Adult Radar 민첩성 축에 사용한다.

### 4.3 Senior HOME 배터리

필수 4종:

```text
- 의자에 앉았다 일어서기
- 앉아윗몸앞으로굽히기
- 2분 제자리걷기
- 의자에 앉아 3m 표적 돌아오기
```

선택:

```text
- 악력
```

Senior HOME 순발력은 다른 측정값으로 추정하지 않는다.

3m 표적 돌아오기는 민첩성 참고값이며 Frontend percentile을 만들지 않는다.

### 4.4 Radar

```text
Measurement Raw Value
≠ Radar Display Value
≠ Backend Percentile
```

보존 조건:

```text
- Radar normalization은 SVG geometry에만 사용
- radarDisplayValue를 체력점수로 출력하지 않음
- 75점, 80점 같은 표현 금지
- 미측정은 null 또는 미측정
- 미측정을 0으로 변환하지 않음
- 일부 축만 측정되면 dot과 인접 segment만 표시
- 모든 축이 유효할 때만 closed polygon 표시
- percentile과 peer average는 Backend only
```

### 4.5 Validation

```text
- 유연성은 기존 최소값 범위 안에서 음수 허용
- 나머지 횟수/거리/시간/악력 validation 유지
- raw value는 표시범위를 벗어나도 원본 보존
- Radar SVG 좌표만 기존 범위로 clamp
```

### 4.6 기타

```text
- PAR-Q 7문항과 판정
- Optional grip
- 상대악력 계산
- Mock workout recommendation
- YouTube privacy-enhanced iframe
- CENTER flow
- 기존 API endpoint/method/payload
```

---

## 5. P4-0 — Current-state audit

수정 전에 다음 파일을 확인한다.

```text
docs/index.html
css/style.css
js/app.js
js/config/*
js/data/*
js/utils/*
js/services/*
docs/06_DECISION_LOG.md
P1/P2/P3 설계·계획·검증 문서
```

다음 현재 상태를 보고한다.

```text
1. Login UI와 실제 동작
2. Signup 코드 유무
3. Guest flow 유무
4. Auth API/service/session/token/profile 지원 여부
5. Basic Information 구조
6. HOME/CENTER route
7. PAR-Q UI와 state
8. HOME measurement UI와 state
9. CENTER Input
10. Report와 Radar raw 표시
11. Center Guidance와 현재 공식 URL
12. Chat state/API/UI/ESC/focus 동작
13. 현재 테스트 자산의 실제 위치와 실행 가능 여부
14. 변경할 파일
15. 변경하지 않을 파일
16. 비즈니스 로직 보존 방법
17. 테스트 계획
18. 발견된 CONFLICT/BLOCKED
```

감사 결과를 먼저 보고한 후 구현을 시작한다.

---

## 6. Auth 구현 경계

현재 코드에는 Mock 로그인 UI만 존재할 가능성이 있으며, 실제 Auth Backend 계약이 없을 수 있다.

먼저 다음을 확인한다.

```text
- signup
- login
- logout
- current user
- profile
- session/token
- saved profile
```

### Auth Backend 계약이 존재하는 경우

기존 endpoint, payload, response, session 정책만 사용한다.

로그인 성공 후:

```text
로그인
→ 기존 계약으로 저장 프로필 조회
→ 성별/나이/키/체중 적용
→ 불필요한 기본정보 재입력 최소화
→ 기존 측정 경로
```

가입 후 자동 로그인을 Frontend가 임의로 결정하지 않는다. 기존 Backend 정책을 따른다.

### Auth Backend 계약이 없는 경우

P4에서 구현:

```text
- 로그인/회원가입/비로그인 진입 UI
- 로그인 입력 UI
- 회원가입 입력 UI
- Frontend validation
- Guest → 기존 Basic Information 연결
- Backend 미연결 상태 안내
```

구현하지 않음:

```text
❌ 실제 계정 생성
❌ 실제 로그인 성공 처리
❌ session/token 생성 및 저장
❌ 사용자 프로필 저장·조회
❌ 가입 후 자동 로그인
❌ localStorage 기반 가짜 사용자 DB
❌ Mock Auth 성공 응답
```

다음으로 기록한다.

```text
BLOCKED — BACKEND AUTH CONTRACT REQUIRED
```

Auth Backend 부재는 PAR-Q, 측정, Report 및 Chat UI 작업 전체를 중단하는 사유가 아니다.

---

## 7. 로그인·회원가입·비로그인 3분기

로그인 진입 화면을 다음 세 경로로 구성한다.

```text
1. 로그인
2. 회원가입
3. 비로그인으로 이용하기
```

권장 구조:

```text
체력코치 AI

[ 로그인 ]

계정이 없으신가요?
[ 회원가입 ]

또는

[ 비로그인으로 이용하기 ]
```

비로그인 경로:

```text
비로그인으로 이용하기
→ 기존 Basic Information
→ 성별/나이/키/체중 입력
→ 기존 측정 경로
```

비로그인 데이터를 회원 프로필처럼 저장하지 않는다.

---

## 8. 회원가입 화면

회원가입 UI를 생성한다.

계정 정보:

```text
- 로그인 ID 또는 이메일
- 비밀번호
- 비밀번호 확인
```

기본 프로필:

```text
- 성별
- 나이
- 키
- 체중
```

수집 금지:

```text
❌ 이름
❌ 주소
❌ 전화번호
```

Frontend validation:

```text
- ID/이메일이 비어 있지 않음
- 비밀번호가 비어 있지 않음
- 비밀번호 확인 일치
- 성별 선택
- 나이가 숫자이며 유효한 양수
- 키가 숫자이며 0보다 큼
- 체중이 숫자이며 0보다 큼
```

Backend 계약이 없으면 만들지 않는 정책:

```text
❌ 최소 비밀번호 길이
❌ 특수문자 필수
❌ 이메일 형식 강제
❌ 이메일 인증
❌ 중복 확인
❌ 자동 로그인
```

회원가입 가능 최소 연령은 현재 정책에서 확정되지 않았다. 임의로 만 19세 이상 가입만 허용하지 않는다. 측정 경로의 Under-19 차단은 별도로 유지한다.

---

## 9. PAR-Q single-page

기존 one-question-at-a-time 표현을 제거하고 7개 질문을 한 화면에 표시한다.

```text
운동 전 안전 확인

아래 7개 문항에 모두 답해주세요.

1. 질문
[ 아니오 ] [ 예 ]

...

7. 질문
[ 아니오 ] [ 예 ]

[ 확인하고 다음 ]
```

규칙:

```text
- 기존 parqQuestions와 parqAnswers 재사용
- 질문 순서와 문구 유지
- 각 질문 선택 상태 명확
- 모든 문항에 답한 후 CTA 활성화
- YES/NO 의미 변경 금지
- 기존 submitParq pass/fail 의미 유지
- 문항을 태블릿/데스크톱에서 2열로 나누지 않음
```

기존 `parqQuestionIndex`, `currentParqQuestion`, 진행 이동 methods가 single-page UI에서 불필요해져도 먼저 영향 범위를 확인한다.

사용되지 않는다는 이유만으로 관련 state와 methods를 무조건 삭제하지 않는다. 삭제가 필요하면 테스트로 기존 판정과 navigation 불변을 증명한다.

---

## 10. PAR-Q YES와 Center Guidance

하나 이상의 답변이 YES이면:

```text
PAR-Q ≥ 1 YES
→ HOME 자가측정 차단
→ Center Guidance
```

유지할 허용 범위:

```text
HOME 자가측정 ❌
개인화 자동 처방 ❌
센터 결과 입력 ✅
공식 운동 영상 ✅
센터 공식 사이트 이동 ✅
```

안내 문구:

```text
응답해주신 내용상 혼자 체력측정을 진행하기보다
체력인증센터에서 전문가와 함께 측정하는 것을 권장합니다.

전국 체력인증센터에서 체력측정과 상담을 받을 수 있습니다.
```

CTA:

```text
가까운 체력인증센터 찾기
```

현재 코드에서 확인되는 공식 URL:

```text
https://nfa.kspo.or.kr
```

처리 규칙:

```text
- 기존 공식 URL을 우선 재사용
- 실제 센터 검색 전용 화면으로 직접 연결되는지는 검증
- 전용 URL이 코드나 확정 문서에 없으면 새 URL을 추측하지 않음
- 전용 URL을 확인할 수 없으면 공식 사이트 이동까지만 구현
- 필요하면 DIRECT CENTER SEARCH URL REQUIRED로 기록
```

---

## 11. HOME 측정 single-page

현재 Dashboard → Active Measurement 표현을 compact measurement cards single-page로 대체한다.

Adult HOME 카드 순서:

```text
1. 앉아윗몸앞으로굽히기
2. 교차윗몸일으키기
3. 제자리멀리뛰기
4. 10m 4회 왕복달리기
5. Optional grip
```

Senior HOME 카드 순서:

```text
1. 의자에 앉았다 일어서기
2. 앉아윗몸앞으로굽히기
3. 2분 제자리걷기
4. 의자에 앉아 3m 표적 돌아오기
5. Optional grip
```

각 카드:

```text
측정 종목명

측정값
[ 입력 ] 단위

[ 측정 방법 ]
[ 영상 보기 ]
```

구현 규칙:

```text
- 기존 battery/homeMeasuredItems/homeValues 사용
- 기존 measurementMin 및 validation 사용
- 기존 측정 가이드와 영상 helper 재사용
- 측정값을 카드별 별도 데이터 구조로 복제하지 않음
- required 항목이 모두 valid할 때만 제출 가능
- Desktop/Tablet에서 2열 가능
- DOM과 keyboard 순서는 배터리 순서 유지
- Mobile은 1열
- 카드 높이를 강제로 동일하게 맞추지 않음
```

### Optional grip의 정확한 의미

```text
- 악력 측정 여부는 명시적으로 선택
- 측정함 → 악력값도 valid해야 제출 가능
- 측정하지 않음 → 필수 HOME 4종만으로 제출 가능
- 선택하지 않은 상태에서는 기존 정책에 따라 제출 제한
```

기존 measurement state는 영향이 없다면 유지한다. 삭제가 필요하면 삭제 이유와 영향 범위를 먼저 보고하고, 데이터·validation·Report payload가 변하지 않음을 검증한다.

---

## 12. Report 정보구조

최종 순서:

```text
1. 나의 체력 리포트
2. 결과 요약
3. 체력 프로필 Radar
4. 또래 비교
5. 미측정 항목
6. 운동 추천 CTA
7. 센터 측정 안내
8. Report footer note
9. Floating Chat
```

현재의 다음 시각 섹션을 제거한다.

```text
상세 기록
내가 입력한 측정값
```

측정 데이터, `radarAxes`, raw value 또는 Backend payload를 삭제하는 것이 아니다.

데스크톱의 기존 `.fc-report-raw-section` grid 배치 규칙도 함께 정리하여 빈 column/row 또는 불필요한 공간이 남지 않게 한다.

---

## 13. Radar raw value 표시

Radar 축 주변에서 factor, 측정 원값과 단위를 확인할 수 있게 한다.

일반 축:

```text
유연성
12.5cm
```

```text
근지구력
32회
```

```text
민첩성
11.3초
```

미측정:

```text
악력
미측정
```

악력은 원 측정값과 상대악력을 구분한다.

```text
악력
32kg
상대악력 49.2%
```

규칙:

```text
- 악력의 Radar geometry는 기존 상대악력 %를 사용
- 측정 악력 kg을 Radar 좌표에 직접 사용하지 않음
- 기존 axis.raw/chartRaw 의미를 확인하고 원값 손실 방지
- 새 점수 또는 계산식 생성 금지
```

Senior 3m:

```text
- raw value와 unit 표시
- '참고값 · 백분위 미제공' 의미 유지
- 다른 값으로 순발력을 추정하지 않음
```

표시 금지:

```text
❌ 75점
❌ 80점
❌ radarDisplayValue
❌ Frontend percentile
```

### Radar 접근성

상세 기록 시각 섹션을 제거하더라도 raw value의 접근 가능한 텍스트는 유지한다.

```text
- SVG aria-label 또는 aria-describedby에 factor/raw/unit 포함
- 미측정은 '미측정'으로 읽힘
- Senior 3m 참고값 의미 포함
- Backend percentile은 별도 비교 영역에서 읽힘
```

Radar geometry, `viewBox`, axis order, polygon, segment, dot 조건은 변경하지 않는다.

---

## 14. Peer Comparison

Radar raw 표기와 별도로 유지한다.

```text
또래 비교

유연성
또래 상위 32%
```

규칙:

```text
- Backend 결과만 사용
- Frontend에서 percentile 생성 금지
- Backend 데이터가 없으면 기존 loading/unavailable 정책 유지
- Senior 3m는 참고값 · 백분위 미제공
- 미측정 항목을 0 또는 비교 가능 값으로 변환하지 않음
```

---

## 15. Report 센터 CTA

Report 하단 센터 CTA는 Center Guidance 내부 이동이 아니라 공식 센터 사이트로 직접 연결하는 방향을 우선한다.

버튼 문구:

```text
가까운 체력인증센터 찾기
```

규칙:

```text
- 현재 공식 URL/helper 재사용
- 새 URL 추측 금지
- 확인되지 않은 검색 전용 경로 생성 금지
- 외부 링크임을 접근 가능하게 알림
- 새 창 사용 시 rel=noopener 적용 가능한 구조 사용
```

직접 검색 URL을 확인할 수 없으면 기존 공식 사이트 루트로 연결하고 제한사항을 기록한다.

---

## 16. Report disclaimer

다음 문구의 의미는 유지한다.

```text
본 리포트는 자가측정 기반 참고 정보이며,
국민체력100 공식 인증 결과가 아닙니다.
의학적 진단을 대체하지 않습니다.
```

별도 card/box가 아닌 Report 최하단 footer-note 형태로 표시한다.

```text
────────────────────

본 리포트는 자가측정 기반 참고 정보이며,
국민체력100 공식 인증 결과가 아닙니다.
의학적 진단을 대체하지 않습니다.
```

CENTER Guidance 등 다른 화면의 disclaimer까지 무조건 같은 방식으로 변경하지 않는다.

---

## 17. Floating Chat

Report 내부의 일반 챗봇 섹션과 버튼을 제거한다.

Report 화면에서만 Floating Chat Button을 표시한다.

버튼 요구사항:

```text
- viewport 우측 하단 fixed
- 원형 또는 rounded square
- 44~48px 이상 touch target
- aria-label="체력코치 AI에게 질문하기"
- safe-area 고려
- sticky CTA와 겹치지 않음
- keyboard focus 표시
```

### Chat panel

Desktop:

```text
- 우측 하단 mini chat window
- bounded width/height
- messages 영역만 내부 scroll
```

Mobile:

```text
- bottom sheet 또는 안전 여백을 둔 제한 폭 panel
- 모바일 키보드에서 input 접근 가능
- safe-area 고려
```

구성:

```text
Header
체력코치 AI

Messages

Input
[ 질문 입력 ] [ 전송 ]
```

### 기존 Chat logic 보존

다음은 유지한다.

```text
chatMessages
chatInput
chatLoading
chatInitialized
/api/coach
/api/chat
history 구성
response handling
error handling
ESC 닫기
```

### P4에서 새로 구현할 접근성

현재 ESC 닫기는 존재하지만 완전한 focus 관리는 확인되지 않았다.

다음은 “기존 유지”가 아니라 P4 신규 접근성 요구다.

```text
- 열릴 때 input 또는 dialog heading으로 focus 이동
- 닫힐 때 Floating Chat Button으로 focus 복귀
- dialog 내부 keyboard focus 관리
- role="dialog"
- aria-modal 적용 여부를 실제 backdrop/modal 동작과 일치시킴
- ESC 닫기 유지
- 모바일 키보드에 입력창이 가려지지 않도록 처리
```

Chat API, payload 및 응답 해석은 변경하지 않는다.

---

## 18. P3 반응형 정책 보존

P4는 P3 breakpoint와 shell 구조를 변경하지 않는다.

```text
320–767px:
full-screen mobile shell

768–1023px:
guttered tablet shell

1024px 이상:
full-viewport desktop shell
```

유지:

```text
- .fc-body는 모든 viewport의 단일 page-content scroll owner
- topbar full-width
- Desktop shell border/radius/shadow 없음
- Desktop general content 최대 1180px
- Login/Basic 최대 720px
- Measurement Dashboard 기준 최대 920px
- PAR-Q/안전 안내/집중 입력 최대 680~720px
```

P4는 새 breakpoint 체계를 만들지 않는다. 기존 breakpoint 안에 필요한 component rule만 추가한다.

### PAR-Q

```text
Mobile:
- 1열
- 7문항 세로 scroll

Tablet/Desktop:
- 680~720px reading width
- 질문 목록 1열
- 각 질문 내부 YES/NO 버튼만 나란히 배치 가능
```

### HOME Measurement

```text
Mobile:
- compact card 1열

Tablet/Desktop:
- compact card 2열 가능
- DOM/keyboard 순서 유지
```

### Report

```text
Mobile:
Summary
→ Radar
→ Peer Comparison
→ Unmeasured
→ Actions
→ Footer note

Desktop:
Radar와 Peer Comparison의 제한적 2열 허용
상세 기록 삭제 후 기존 raw-section grid rule 제거
빈 grid 영역 금지
```

### Floating Chat

```text
Mobile:
bottom sheet 또는 제한 폭 panel

Tablet/Desktop:
viewport 우측 하단 mini window
```

확인 사항:

```text
- horizontal overflow 없음
- sticky CTA가 마지막 입력을 가리지 않음
- Radar label clipping 없음
- Chat이 CTA/topbar와 겹치지 않음
- 모바일 키보드에서 Chat input 접근 가능
- 200% zoom 사용 가능
```

---

## 19. 변경 파일 원칙

예상 주요 수정:

```text
js/app.js
css/style.css
P4 설계/검증 문서
필요한 테스트 파일
```

원칙적으로 보호:

```text
js/config/*
js/data/*
js/utils/*
js/services/*
docs/index.html
```

Auth service 등 새 파일이 필요해 보이면 먼저 실제 Backend 계약을 확인한다. 계약이 없으면 service나 endpoint를 만들지 않는다.

`app.js`에서 다음은 필요 이상 수정하지 않는다.

```text
- Radar 계산
- percentile 처리
- relative grip 계산
- video parser/lifecycle
- recommendation logic
- 기존 API payload
```

---

## 20. 구현 순서

대규모 일괄 수정은 금지한다.

### P4-0 — Current-state audit

현재 구조, 충돌, Backend 지원과 테스트 자산을 보고한다.

### P4-1 — Auth Entry UI

```text
Login
Signup
Guest
Frontend validation
Backend 부재 상태 처리
```

실제 Auth는 기존 계약이 있을 때만 연결한다.

### P4-2 — PAR-Q와 Center Guidance

```text
PAR-Q 7문항 single-page
all answered CTA
YES → Center Guidance
공식 센터 사이트 CTA
```

### P4-3 — HOME Measurement

```text
Adult single-page
Senior single-page
Optional grip
Negative flexibility
기존 validation
Guide/Video
```

### P4-4 — Report

```text
상세 기록 시각 섹션 제거
Radar raw value
악력 kg/상대악력 구분
Senior 3m 참고값
Peer Comparison 유지
센터 CTA
Footer disclaimer
desktop grid 정리
Radar 접근성
```

### P4-5 — Floating Chat

```text
Floating button
Responsive mini panel/bottom sheet
기존 Chat API/logic
ESC
focus 이동·복귀
mobile keyboard
```

### P4-6 — Full Regression

전체 flow, 정책, API와 반응형 화면을 검증한다.

각 단계가 검증된 후 다음 단계로 이동한다.

---

## 21. 테스트 및 검증

먼저 현재 프로젝트와 작업 환경에서 실제 실행 가능한 테스트 자산을 확인한다.

과거 문서에 기록된 테스트 숫자를 새로 실행한 결과로 보고하지 않는다.

### 자동 검사

```text
- 현재 JavaScript 전체 syntax
- 신규 P4 테스트가 실제 생성됐다면 해당 테스트
- protected module hash
- docs/index.html dependency load order
- API endpoint/method/payload contract
- app.js exact diff
```

### Flow 검증

```text
Auth UI:
- Login
- Signup
- Guest
- validation error
- Backend unavailable

Basic:
- manual Basic Information
- Under-19 measurement block

PAR-Q:
- 7문항 표시
- 일부 미응답 시 CTA disabled
- all NO
- one YES
- Center Guidance
- Center official link

HOME:
- Adult 4종
- Senior 4종
- optional grip 측정함
- optional grip 측정하지 않음
- negative flexibility
- invalid required measurement
- guide/video

Report:
- Radar raw values
- grip kg + relative grip %
- missing null
- partial/full Radar
- Backend percentile
- Backend unavailable
- Senior 3m reference
- detailed raw section absent
- no empty desktop grid
- footer note
- center CTA

Other:
- Recommendation
- YouTube
- CENTER input

Chat:
- floating button
- init
- send
- error
- ESC close
- focus open/return
- mobile keyboard layout
```

### 반응형 검증

최소:

```text
Mobile:
320×568
390×844
430×932

Tablet:
768×1024
820×1180

Desktop:
1024×768
1440×900
1920×1080
```

확인:

```text
- horizontal overflow
- clipping
- mobile DOM/keyboard order
- sticky overlap
- Radar labels
- Chat placement
- safe-area
- 200% zoom
```

### Auth 테스트 판정

Backend Auth 계약이 없으면 다음은 실패가 아니라 `BLOCKED/SKIP`으로 기록한다.

```text
- 실제 signup 성공
- 실제 login 성공
- logout
- session/token 유지
- saved profile 조회
- 가입 후 로그인
```

실행하지 않은 항목을 PASS로 보고하지 않는다.

---

## 22. 완료 조건

### 현재 Frontend만으로 완료 가능한 범위

```text
[ ] 로그인/회원가입/비로그인 3분기 UI
[ ] 회원가입 페이지
[ ] 이름/주소/전화번호 미수집
[ ] 회원가입 Frontend validation
[ ] Guest → Basic Information
[ ] Auth 계약 부재 시 가짜 endpoint/session 미생성

[ ] PAR-Q 7문항 single-page
[ ] 기존 판정 유지
[ ] YES → Center Guidance
[ ] 공식 센터 사이트 CTA

[ ] Adult HOME single-page
[ ] Senior HOME single-page
[ ] Optional grip 정책 유지
[ ] Negative flexibility 유지
[ ] 기존 validation 유지

[ ] 상세 기록 시각 섹션 제거
[ ] Radar raw value + unit
[ ] 악력 kg와 상대악력 % 구분
[ ] Senior 3m 참고값 유지
[ ] Backend percentile 별도 유지
[ ] missing을 0으로 처리하지 않음
[ ] Radar 접근성 유지

[ ] Report footer-note
[ ] Floating Chat Button
[ ] Responsive Chat panel
[ ] 기존 Chat API/logic 유지
[ ] ESC 및 focus 접근성

[ ] P3 반응형 shell과 breakpoint 유지
[ ] mobile/tablet/desktop 회귀 없음
[ ] 보호 정책과 API 계약 회귀 없음
```

### Backend 계약이 있을 때만 완료 가능한 범위

```text
[ ] 실제 회원가입
[ ] 실제 로그인
[ ] 로그아웃
[ ] session/token
[ ] 저장 프로필
[ ] 로그인 사용자 프로필 자동 적용
```

Backend 계약이 없으면 위 항목은 완료 조건에서 제외하고 다음으로 보고한다.

```text
BLOCKED — BACKEND AUTH CONTRACT REQUIRED
```

---

## 23. 최종 보고 형식

```text
1. P4-0 Current-state audit
2. 발견된 CONFLICT
3. Backend Auth 지원 여부
4. BLOCKED/OUT OF SCOPE
5. 단계별 구현 내용
6. 변경 파일
7. 보호 파일 hash 비교
8. app.js 및 API diff 판정
9. 실제 실행한 테스트
10. PASS/FAIL/SKIP/BLOCKED
11. viewport별 검증
12. 남은 위험과 다음 단계
```

---

## 24. 최종 핵심 명령

이번 P4는 기존 측정 정책과 계산을 변경하는 작업이 아니라 사용자 진입 흐름과 화면 표현을 개선하는 작업이다.

다음을 구현한다.

```text
- 로그인/회원가입/비로그인 진입 UI
- PAR-Q 7문항 single-page
- HOME compact measurement cards single-page
- Center Guidance와 공식 센터 사이트 연결
- Report 정보구조 재배치
- Radar raw value 표시
- Report footer disclaimer
- Floating Chat
```

다음을 변경하지 않는다.

```text
- 측정 배터리
- PAR-Q 판정
- raw measurement data
- validation
- Radar normalization/geometry
- missing/null
- Backend percentile
- API 계약
- recommendation logic
- YouTube lifecycle
- P2 module structure
- P3 responsive shell과 breakpoint
```

실제 Backend Auth 계약이 없으면 임의 endpoint, 가짜 session 또는 localStorage 계정을 만들지 않는다. Auth UI와 Frontend validation까지만 구현하고 `BLOCKED — BACKEND AUTH CONTRACT REQUIRED`로 기록한다.

---

## 25. P4-0 확정 감사 결과 — 2026-09-11

### 충돌과 UX supersession

- 현재 P0–P3 구현과 `docs/06_DECISION_LOG.md`의 CONFIRMED 정책 사이의 충돌은 발견되지 않았다.
- P4의 PAR-Q 7문항 single-page는 P1의 one-question-at-a-time UI 표현을 의도적으로 supersede한다.
- P4의 HOME compact measurement cards single-page는 P1의 Measurement Dashboard → Active Measurement UI 표현을 의도적으로 supersede한다.
- 두 변경은 화면 표현과 입력 진행 방식만 대체하며 PAR-Q 판정, 측정 배터리, 원값, validation, optional grip, Radar, percentile 및 API 계약은 변경하지 않는다.

### Auth 경계

- 현재 로그인은 읽기 전용 Mock 시연 UI이며 실제 Auth endpoint, service, session, token 또는 saved profile 계약이 없다.
- P4는 Login/Signup/Guest UI와 Frontend validation까지만 구현한다.
- 실제 signup, login, logout, session/token 및 저장 프로필은 `BLOCKED — BACKEND AUTH CONTRACT REQUIRED`로 기록한다.
- Auth Backend 부재는 PAR-Q, HOME measurement, Report 및 Floating Chat UI 구현을 중단시키지 않는다.

### 공식 센터 검색 URL

- 기존 코드: `https://nfa.kspo.or.kr`
- P4에서 검증 후 적용: `https://nfa.kspo.or.kr/intro/centerList.kspo`
- 위 주소는 국민체력100 공식 체력인증센터 찾기 페이지로 검증됐으며 임의 URL 생성이 아니다.

### 외부 테스트 자산과 P4 baseline

외부 테스트 절대 경로:

```text
C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests
```

확인 결과 해당 테스트는 현재 `C:\Users\user\Desktop\frontend_v3`를 대상으로 한다.

2026-09-11 P4-0에서 실제 실행한 결과:

- Node test files: 13
- Node tests: 49/49 PASS
- PowerShell contract files: 4/4 PASS
- Current JavaScript syntax: 11/11 PASS
- P2 protected-module hashes: 10/10 MATCH

이 결과는 과거 P3 결과와 구분되는 P4 시작 baseline이다.

### 문서 및 구현 산출물

- `docs/12_P4_FLOW_AUTH_REPORT_DESIGN.md`
- `docs/superpowers/plans/2026-09-11-p4-flow-auth-report-refinement.md`
- `docs/13_P4_VERIFICATION.md`
- `docs/06_DECISION_LOG.md`
- `js/app.js`
- `css/style.css`
- 필요한 외부 P4 테스트 파일

P4 구현 계획 문서는 본 설계서 사용자 검토 승인 후 작성한다.

