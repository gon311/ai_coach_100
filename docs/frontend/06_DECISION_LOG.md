# 06. Frontend Decision Log

## Stage P0 — Policy & Radar Alignment

적용 범위: 기존 Vue 화면 구조와 순백색·파란색 디자인을 유지하면서 측정 정책, Radar 데이터 모델, Backend percentile 경계, 미측정 처리, 영상 재생, 입력 검증 및 Mock 처방 데이터 계층을 정렬한다. JavaScript 파일 분리와 대규모 리팩터링은 P1 Stage로 연기한다.

### [CONFIRMED] Radar의 의미

Radar chart는 체력점수나 백분위를 표현하는 그래프가 아니다.

사용자의 측정 원값을 종목별 predefined display range 안에서 0~100 SVG 좌표로 정규화하여 시각화한다. 이 정규화 결과는 `radarDisplayValue`이며 화면에 `75점`, `82점`과 같은 체력점수로 출력하지 않는다.

Radar normalized value MUST NOT be exposed as fitness score.

Percentile is supplied separately by Backend.

Unmeasured values MUST NOT be converted to zero.

### [CONFIRMED] Adult Radar display ranges — 만 19~64세

| Radar 축 | 측정항목 | 원값 표시 범위 |
| --- | --- | --- |
| 유연성 | 앉아윗몸앞으로굽히기 | -30 ~ +40 cm |
| 순발력 | 제자리멀리뛰기 | 0 ~ 300 cm |
| 근지구력 | 교차윗몸일으키기 | 0 ~ 100회 |
| 민첩성 | CENTER에서 제공되는 해당 측정값 | 0 ~ 40초, 짧을수록 바깥쪽 |
| 악력 | 상대악력 | 0 ~ 100% |
| 심폐지구력 | CENTER에서 제공되는 해당 측정값 | 0 ~ 150 |

Adult HOME 배터리는 BMI 산출을 위한 신장·체중 정보와 다음 4개 현장 측정으로 고정한다.

- 교차윗몸일으키기
- 앉아윗몸앞으로굽히기
- 제자리멀리뛰기
- 10m 4회 왕복달리기

10m 4회 왕복달리기는 Adult HOME과 CENTER에서 모두 사용할 수 있다. 악력은 선택 모듈이다.

### [CONFIRMED] Senior Radar display ranges — 만 65세 이상

| Radar 축 | 기준 측정항목 | 원값 표시 범위 |
| --- | --- | --- |
| 유연성 | 앉아윗몸앞으로굽히기 | -30 ~ +40 cm |
| 순발력 | CENTER 측정값이 있을 경우 | 0 ~ 300 cm |
| 근지구력 | 의자에 앉았다 일어서기 | 0 ~ 60회 |
| 민첩성 | 의자에 앉아 3m 표적 돌아오기 | 0 ~ 20초, 짧을수록 바깥쪽 |
| 악력 | 상대악력 | 0 ~ 100% |
| 심폐지구력 | 2분 제자리걷기 | 0 ~ 150회 |

Senior HOME mappings:

- Chair stand → muscular endurance / 근지구력
- Sit and reach → flexibility / 유연성
- 2-min step → cardio endurance / 심폐지구력
- 3m chair target return → agility / 민첩성, 참고값

Senior HOME에는 순발력 측정 종목이 없다. 순발력 축은 유지하되 `미측정`으로 표시하고 다른 원값으로 추정하지 않는다. CENTER에서 대응 데이터가 제공될 때만 순발력 원값과 Radar 위치를 표시한다.

### [CONFIRMED] 미측정 데이터

미측정 축의 내부값은 `null`이다. Radar 중심의 0으로 변환하지 않는다.

- 축 라벨에는 `미측정`을 표시한다.
- 사용자 점을 그리지 않는다.
- 미측정 축을 중심점에 연결하지 않는다.
- 모든 축이 측정된 경우에만 닫힌 사용자 면을 그린다.
- 일부 축만 측정된 경우에는 서로 인접한 측정 축의 선분과 점만 그린다.

Senior HOME의 미측정 안내는 순발력, 선택 악력(상지 근기능), 협응력을 구분한다.

### [CONFIRMED] Percentile과 신뢰 범위

Percentile은 측정 원값, 성별, 5세 `age_band` 및 공단 규준 데이터를 이용해 Backend에서 계산한다. Frontend는 percentile을 계산하거나 Radar 위치값으로 대체하지 않는다.

- Backend 비교 결과가 있을 때만 `상위 N%`를 표시한다.
- Backend 연결 전에는 percentile과 평균을 표시하지 않는다.
- `agility_shuttle`에 적용하던 임의 ±5%p 범위는 제거한다.
- `chair_stand`는 Backend percentile이 존재할 때만 ±5%p 표시 범위를 적용한다.
- Senior 3m 표적 돌아오기는 계속 참고값이며 Frontend percentile을 만들지 않는다.

### [CONFIRMED] 악력

사용자 입력은 악력계 원값 kg이다. Radar와 Backend 비교에는 `악력 kg / 체중 kg × 100`으로 산출한 상대악력 %를 사용한다. 악력계를 선택하지 않았거나 유효한 원값이 없으면 `null`과 미측정 상태를 유지하며 0%를 전송하지 않는다.

### [CONFIRMED] 입력 검증

모든 측정항목에 `>= 0`을 적용하는 공통 검증은 사용하지 않는다.

- 유연성 입력은 -30 cm 이상을 허용한다.
- 그 밖의 횟수·거리·시간·악력 입력은 항목별 최소값 0을 적용한다.
- Radar 범위를 벗어난 유효 원값은 원본을 변경하지 않고 SVG 좌표만 0~100 사이로 제한한다.

### [BLOCKED] 만 19세 미만 배터리

teen/youth 측정 배터리는 확정되지 않았다. Frontend가 임의 항목을 제공하지 않으며 만 19세 미만 사용자는 기본정보 화면에서 측정 경로 진입을 차단한다. 최종 배터리는 기획·Data·Backend 합의 후 별도 Stage에서 확정한다.

### [CONFIRMED] 영상 재생

측정 가이드와 국민체력100 운동 영상은 웹뷰 안의 privacy-enhanced YouTube iframe Player로 재생한다. 직접 `<video src>` 재생과 새 YouTube 사이트 페이지 이동은 사용하지 않는다. YouTube ID로 해석할 수 없는 레코드는 재생 불가 상태로 표시한다.

### [CONFIRMED] Mock 운동 처방

Frontend 하드코딩 운동은 `MOCK_WORKOUT_RECOMMENDATIONS` 데이터 계층으로 분리하고 화면에 Mock임을 표시한다. 약점 항목은 Backend percentile이 있을 때만 해당 결과를 사용하며, 없으면 기본 전신 체력 구성을 사용한다. 실제 자동 처방 Backend 결합 전까지 Mock 데이터는 공식 처방으로 표현하지 않는다.

### [BLOCKED / TERMINOLOGY] Senior chair stand factor

만 65세 이상 `의자에 앉았다 일어서기`에 대해 문서 간 다음 표현이 혼재한다.

- 근력
- 근지구력
- 하지 근기능

현재 Frontend Radar 표시명은 `근지구력`으로 유지한다. 최종 `factor_code` 및 명칭은 Data/Backend 협의 후 확정한다.

### [CONFIRMED] 임시 식별자

`RADAR_CONFIG.code`는 Backend의 최종 `factor_code` 또는 `item_code`가 확정되기 전까지 사용하는 Frontend 내부 식별자다. Frontend 식별자를 공식 Backend 계약으로 간주하지 않는다.

## [CONFIRMED / STAGE SCOPE UPDATE] P1 and P2

Previous P1: JavaScript file split and structural refactoring.

Superseded by: P1 = Mobile UX & Report Redesign.

P1 constraints:

- Keep Vue runtime.
- Keep single `app.js`.
- Preserve P0 policy, calculations, contracts, and behavior.
- Redesign information architecture, interaction, accessibility, and visual presentation only.

JavaScript file splitting into `config / data / services / app` is deferred to P2.

## [CONFIRMED / P1 FINAL REFINEMENT] Header and Radar colors

- The `체력코치 AI` header brand returns to Landing through the existing Vue navigation method.
- `나의 측정값` uses a light-blue filled polygon with a blue outline.
- `또래 평균` uses a light-orange filled polygon with an orange outline.
- Filled polygons are rendered only for complete series. Partial series retain dots and adjacent segments.
- Peer averages remain Backend-only and are never synthesized by Frontend.

## [CONFIRMED / P2 COMPLETE] JavaScript structure

P2 modifies the existing frontend in place and does not regenerate or rewrite it. Vue CDN and the existing templates remain.

- `js/config`: measurement, Radar, and video configuration
- `js/data`: explicitly labeled Mock workout data
- `js/utils`: pure measurement, Radar, and YouTube helpers
- `js/services`: existing percentile, report-summary, and video API access
- `js/app.js`: Vue state, computed UI models, navigation, event orchestration, and templates

All extracted files publish through `window.FitnessCoach` and are loaded as classic scripts in dependency order. This preserves the existing no-bundler delivery model and direct-file-compatible script format. P0 batteries, Radar normalization, missing-value rules, percentile authority, Backend endpoints, and Mock prescription selection are unchanged.

## [CONFIRMED / P3 COMPLETE] Responsive presentation

P3 keeps the P0 policy, P1 mobile information order, P2 classic-script structure, Vue state, API contracts, Radar meaning, measurement validation, and media lifecycle unchanged.

- 320–767px uses a full-screen mobile application shell.
- 768–1023px uses a guttered tablet shell.
- 1024px and above uses a full-viewport shell. The 1180px limit applies only to the centered effective content area inside `.fc-body`, never to `.fc-phone`.
- `.fc-body` is the single normal page-content scroll owner at every breakpoint.
- Route, CENTER input, Report, Recommendation, Video, and HOME guide use additional width selectively.
- PAR-Q and Active Measurement retain focused single-column reading widths.
- Radar geometry and `viewBox="0 0 300 300"` are unchanged; only its responsive container and legend presentation change.
- `js/config/*`, `js/data/*`, `js/utils/*`, `js/services/*`, and `docs/index.html` remain unchanged from the P3 baseline.
- `js/app.js` changes are limited to 11 presentation-only `fc-page-*` class additions.

Desktop content widths at 1024px and above:

- General, Report, Recommendation, and Video: up to 1180px
- Measurement Dashboard: up to 920px
- Login and Basic Information: up to 720px
- PAR-Q, Active Measurement, and Safety Guidance: focused 680–720px

The full-width desktop shell does not alter the tablet/mobile breakpoints, topbar, sticky CTA, drawer, or internal scrolling behavior.

P2 verification counts remain historical records. P3 verification distinguishes target-local reproducible checks from test assets executed from the external Codex workspace.
