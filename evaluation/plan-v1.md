
# 측정 데이터 정규화 스펙 v1
 
> 대상: 백엔드 담당자
> 작성: 데이터 분석 파트
> 관련 문서: 「홈측정 설계기준 v1」
 
---
 
## 0. 한 줄 요약
 
**측정값은 원값 그대로 저장한다. 센터 값과 홈 값을 서로 변환하지 않는다.** 비교 가능성은 저장 시점이 아니라 조회 시점의 **백분위 변환**에서 확보된다.
 
---
 
## 1. 설계 원칙
 
### 1-1. 값 변환 금지
 
"홈 측정값에 보정 계수를 곱해 센터 기준으로 환산"하는 방식은 채택하지 않는다.
 
- 그런 계수를 산출하려면 동일인이 두 방식으로 측정한 가교 표본이 필요하며, 우리에겐 없다
- 근거 없는 계수를 넣는 순간 서비스의 통계적 신뢰성 주장이 무너진다
- **홈 배터리는 애초에 센터와 동일 프로토콜로 수행 가능한 종목만 선정했으므로 변환이 불필요하다**
### 1-2. 정규화의 두 층
 
| 층 | 내용 | 구현 위치 |
|---|---|---|
| 스키마 정규화 | 종목을 컬럼이 아닌 **행**으로 저장 (wide → long) | 테이블 설계 |
| 통계적 표준화 | 서로 다른 단위(cm·회·초)를 **백분위**로 통일 | 규준 테이블 조회 |
 
센터 트랙과 홈 트랙은 `source` 컬럼으로만 구분되며, **동일한 규준 테이블과 동일한 조회 로직을 사용한다.** 트랙별 분기 로직을 만들지 않는다.
 
### 1-3. 표준화 지표로 z-score가 아닌 백분위를 사용하는 이유
 
- 체력 측정값 분포는 왜도가 있어 정규분포 가정이 성립하지 않는 종목이 많다. z-score는 정규성을 전제하므로 부적합
- 백분위는 순위 기반이라 분포 가정이 불필요
- 사용자 전달력이 높다 ("상위 32%" vs "z = +0.47")
- 단위가 다른 종목 간 비교(레이더 차트)가 자연스럽게 성립
---
 
## 2. 반드시 주의할 함정 2가지
 
### 2-1. 방향성은 3종이다 (boolean으로 설계 금지)
 
| 방향성 | 의미 | 해당 종목 |
|---|---|---|
| `HIGHER_BETTER` | 값이 클수록 우수 | 상대악력, 교차윗몸일으키기, 앉아윗몸앞으로굽히기, 제자리멀리뛰기, 왕복오래달리기(회), 의자에앉았다일어서기, 2분제자리걷기, 6분걷기 |
| `LOWER_BETTER` | 값이 작을수록 우수 | 10m 왕복달리기(초), 8자보행(초), 의자에앉아 3m 표적돌아오기(초), 반응시간 |
| `OPTIMAL_RANGE` | 중간값이 최적 (U자) | BMI, 체지방률 |
 
`LOWER_BETTER` 종목은 백분위 산출 시 순위를 반전시켜야 한다.
 
```
percentile = (direction == 'LOWER_BETTER')
             ? 100 - raw_percentile
             : raw_percentile
```
 
### 2-2. BMI는 백분위 파이프라인에서 제외한다
 
BMI는 양극단이 모두 위험한 U자 구조다. 백분위로 표현하면 **"상위 5%"가 저체중인지 비만인지 구분되지 않는다.**
 
- BMI·체지방률은 `percentile_eligible = FALSE`로 고정
- 별도의 **구간 판정**(저체중 / 정상 / 과체중 / 비만)으로 처리
- **레이더 차트에 포함하지 않는다**
### 2-3. 규준의 단위는 요인이 아니라 종목이다
 
같은 심폐지구력이라도 20m 왕복오래달리기와 스텝검사는 측정 단위와 분포가 다르다. 규준 테이블의 키는 반드시 `item_code`이며 `factor_code`가 아니다.
 
---
 
## 3. 테이블 설계
 
### 3-1. 종목 마스터
 
```sql
CREATE TABLE fitness_item (
  item_code          VARCHAR(40)  NOT NULL,
  item_name          VARCHAR(100) NOT NULL,
  factor_code        VARCHAR(30)  NOT NULL,   -- 신체조성/근력/근지구력/심폐지구력/유연성/민첩성/순발력/협응력
  age_group_code     VARCHAR(20)  NOT NULL,   -- ADULT / SENIOR / YOUTH ...
  unit               VARCHAR(10)  NOT NULL,   -- cm / kg / 회 / 초 / % / bpm
  direction          ENUM('HIGHER_BETTER','LOWER_BETTER','OPTIMAL_RANGE') NOT NULL,
  home_capable       ENUM('EXACT','CONDITIONAL','NONE') NOT NULL,
  required_equipment VARCHAR(200) NULL,
  PRIMARY KEY (item_code)
);
```
 
- `home_capable = 'EXACT'`인 종목만 홈 측정 UI에 노출
- `'CONDITIONAL'`은 기구 보유 확인 후 노출 (예: 상대악력 → 악력계)
### 3-2. 규준 테이블 (백분위 컷포인트)
 
공단 측정결과 데이터로부터 사전 산출해 적재한다. 데이터 갱신 주기가 연 단위이므로 배치 적재로 충분하다.
 
```sql
CREATE TABLE fitness_norm (
  item_code     VARCHAR(40) NOT NULL,
  sex           ENUM('M','F') NOT NULL,
  age_band      VARCHAR(10) NOT NULL,   -- '19-24','25-29',... 5세 단위
  percentile    TINYINT     NOT NULL,   -- 0 ~ 100
  cut_value     DECIMAL(8,2) NOT NULL,
  sample_n      INT         NOT NULL,   -- 해당 셀의 표본 수
  norm_version  VARCHAR(20) NOT NULL,   -- 예: '2025H2'
  PRIMARY KEY (item_code, sex, age_band, percentile, norm_version),
  INDEX idx_lookup (item_code, sex, age_band, norm_version, cut_value)
);
```
 
- 백분위 1 단위로 101개 행을 사전 계산해 적재 → **런타임은 단순 범위 조회**로 끝난다
- `norm_version`으로 데이터 개편 이력을 관리한다 (2025.10 개편 반영분과 이전 분 병존 가능)
- **규준 산출은 분석 파트(Python)에서 수행하고 결과 테이블만 전달한다.** 백엔드는 조회만 담당
### 3-3. 측정 레코드
 
```sql
CREATE TABLE measurement (
  measurement_id      BIGINT AUTO_INCREMENT,
  user_id             BIGINT      NOT NULL,
  item_code           VARCHAR(40) NOT NULL,
  raw_value           DECIMAL(8,2) NOT NULL,   -- 원값. 절대 변환 금지
  source              ENUM('CENTER','HOME') NOT NULL,
  protocol_match      ENUM('EXACT','PARTIAL','NONE') NOT NULL,
  equipment_verified  BOOLEAN     NOT NULL DEFAULT FALSE,
  percentile_eligible BOOLEAN     NOT NULL,
  measured_at         DATETIME    NOT NULL,
  PRIMARY KEY (measurement_id),
  INDEX idx_user_item (user_id, item_code, measured_at),
  FOREIGN KEY (item_code) REFERENCES fitness_item(item_code)
);
```
 
`percentile_eligible` 산정 규칙 (저장 시점에 계산해 고정):
 
```
percentile_eligible =
    protocol_match = 'EXACT'
AND equipment_verified = TRUE
AND direction != 'OPTIMAL_RANGE'
AND 해당 (item, sex, age_band) 규준 셀의 sample_n >= MIN_SAMPLE
```
 
### 3-4. 문진 결과 (민감정보)
 
```sql
CREATE TABLE user_screening (
  user_id      BIGINT NOT NULL,
  parq_passed  BOOLEAN NOT NULL,   -- 판정 결과만 저장. 문항별 응답 저장 금지
  screened_at  DATETIME NOT NULL,
  valid_until  DATE NOT NULL,      -- 재문진 주기 (예: 6개월)
  PRIMARY KEY (user_id)
);
```
 
**중요**: PAR-Q 개별 문항 응답은 건강 관련 민감정보이므로 저장하지 않는다. 세션에서 판정 후 폐기한다.
 
---
 
## 4. 백분위 산출 절차
 
### 4-1. 조회 로직
 
```sql
-- HIGHER_BETTER 종목
SELECT MAX(n.percentile)
FROM fitness_norm n
WHERE n.item_code    = :item_code
  AND n.sex          = :sex
  AND n.age_band     = :age_band
  AND n.norm_version = :norm_version
  AND n.cut_value   <= :raw_value;
 
-- LOWER_BETTER 종목은 부등호 방향과 집계를 반전
--   AND n.cut_value >= :raw_value  →  SELECT MIN(n.percentile)
```
 
단순 인덱스 조회이므로 별도 연산 서버가 필요 없다. **백분위 산출은 백엔드에서 처리하고, AI 서버는 처방·RAG에 집중하는 분담을 권장한다.** (기획서 초안에서는 AI 서버에 배치되어 있었으나, 사전 계산 테이블 방식으로 전환되면서 런타임 연산이 사라졌다. 팀 논의 필요.)
 
### 4-2. 표본 부족 셀 처리
 
> **실측 검증 완료 (2022~2026 종합데이터 EDA).** 성인·어르신 전 연령대×성별 셀이 `MIN_SAMPLE=100`을 모두 충족했다(최소 797건, 어르신 남성 85세 이상·허리둘레). **현재 데이터 기준으로는 아래 병합 로직이 한 번도 발동하지 않는다.**
> 그럼에도 로직은 제거하지 않고 유지한다 — 청소년기 이하 연령군을 추가하거나 `norm_version`을 단일 연도 기준으로 재산출할 경우 발동할 수 있다. 백엔드는 구현하되 "현재 미발동" 상태로 이해하면 된다.
 
`sample_n < MIN_SAMPLE` (**확정값: 100**) 인 셀은 다음 순서로 처리한다.
 
1. 인접 연령대와 병합해 재산출 (예: `60-64` → `55-64`)
2. 병합 후에도 미달이면 **백분위를 제공하지 않는다** (`percentile_eligible = FALSE`)
3. UI에는 "해당 연령·성별 구간은 비교 표본이 부족해 백분위를 제공하지 않습니다"로 표기
임계값을 채우려고 억지로 추정하지 않는다. 커버리지 경계를 투명하게 드러내는 편이 신뢰도에 유리하다.
 
### 4-3. 자가측정 오차 표기
 
동일 종목이라도 감독자 유무에 따라 오차 구조가 다르다. 백분위 값 자체는 동일하게 산출하되, **표기 단계에서 구간으로 확장**한다.
 
확장 폭은 **종목마다 다르다.** 프로토콜 통제 변수의 개수와 민감도가 종목별로 다르기 때문이다(근거: 「홈측정 설계기준 v2」 4-6절 편향 판단표).
 
| 종목 | `CENTER` 표기 | `HOME` 표기 | 확장 폭(초기안) |
|---|---|---|---|
| 앉아윗몸앞으로굽히기 | 상위 32% | 상위 22~42% | ±10%p |
| 교차윗몸일으키기 | 상위 32% | 상위 25~39% | ±7%p |
| 2분제자리걷기 | 상위 32% | 상위 25~39% | ±7%p |
| 제자리멀리뛰기 | 상위 32% | 상위 27~37% | ±5%p |
| 의자에앉았다일어서기 | 상위 32% | 상위 27~37% | ±5%p |
| 의자에앉아 3m 표적돌아오기 | 상위 32% | **미정** | **미정** |
 
- 확장 폭은 리포트 조립 계층의 **설정값(종목별 맵)** 으로 관리한다. 쿼리를 분기하지 않는다.
- **초기안 수치는 실측 근거가 아니라 편향 요인 크기에 대한 판단값이다.** 센터·홈 페어 표본을 확보하면 실측값으로 교체한다.
- BMI·허리둘레·혈압은 `percentile_eligible = FALSE`이므로 백분위를 산출하지 않는다. 따라서 **구간 폭 논의 대상이 아니다.** 값 자체(예: BMI 22.4)는 점추정으로 표시하고, 해석은 구간 판정(저체중/정상/과체중/비만 등)으로 처리한다.
---
 
## 5. 엣지 케이스
 
| 상황 | 처리 |
|---|---|
| 만 65세 생일 경과 | `age_group_code`가 ADULT → SENIOR로 전환. **과거 레코드는 재계산하지 않고** 측정 시점 연령군 기준을 유지 |
| 만 60~64세에 어르신 종목 측정 | 해당 종목의 성인기 규준이 없으므로 `percentile_eligible = FALSE` |
| 동일 종목 재측정 | 레코드를 갱신하지 않고 **행을 추가**한다. 추이 트래킹의 근거가 됨 |
| 센터 측정 후 홈 재측정 | 같은 user에 두 `source`가 혼재해도 정상. 최신 레코드 기준으로 리포트 산출 |
| 심폐지구력 종목이 여러 개 | 왕복오래달리기·스텝검사·트레드밀은 별개 `item_code`. 요인 단위 집계 시 **가장 최근 1건만** 사용 |
| 규준 버전 갱신 | 과거 리포트 재현을 위해 `measurement`에 산출 시 사용한 `norm_version`을 함께 기록하는 것을 권장 |
 
---
 
## 6. 분석 파트 ↔ 백엔드 인계 항목
 
**분석 파트가 제공**
- `fitness_item` 초기 데이터 (종목·요인·단위·방향성·홈가능여부)
- `fitness_norm` 적재용 CSV (종목×성별×연령대×백분위 컷포인트, `sample_n` 포함)
- `MIN_SAMPLE` 최종값(**100 확정**) 및 인접 연령대 병합 규칙
- 종목별 홈 측정 구간 확장 폭 설정값 (4-3절 표)
**백엔드가 담당**
- 위 3개 테이블 DDL 및 적재 배치
- `percentile_eligible` 산정 로직
- 백분위 조회 API
- `user_screening` 기반 기능 게이트
**해소된 사항**
- ~~`age_band` 구간 폭: 5세 단위 vs 10세 단위~~ → **5세 단위로 확정.** 2022~2026 종합데이터(55개월, 143만 행) 전수 분석 결과 성인·어르신 전 셀이 `MIN_SAMPLE=100`을 충족했다(최소 797건). 10세 단위 병합이나 인접 구간 스무딩은 필요하지 않다. (EDA 3절 / 「홈측정 설계기준 v2」 8-2절)
- ~~`MIN_SAMPLE` 초기값 제안~~ → **100으로 확정.**
**미결 사항 (팀 논의 필요)**
1. 백분위 산출 위치: 백엔드 vs AI 서버 (4-1절)
2. `norm_version` 이력 보관 정책
3. 홈 측정 구간 확장 폭 최종 수치 (4-3절 초기안 검토) — 특히 3m표적돌아오기 미정
4. 어르신 절대악력 규준의 데이터 기간 — **2024년 1월 이후만 사용 권고** (2022년 미수집, 2023년 채움률 62.2%). `norm_version`에 이 제약을 어떻게 표기할지 결정 필요
 
