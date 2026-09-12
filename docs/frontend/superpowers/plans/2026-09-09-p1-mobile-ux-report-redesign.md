# Stage P1 Mobile UX & Report Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the verified P0 Vue webview into a mobile-first measurement coach while preserving every P0 policy, calculation, data boundary, and backend contract.

**Architecture:** Keep Vue CDN and the single `js/app.js`. Implement one vertical screen slice at a time, limiting each slice to its template state/methods and directly related CSS, then run focused and P0 regression checks before proceeding. Defer JavaScript module extraction to P2.

**Tech Stack:** Vue 3 CDN, plain JavaScript, HTML template strings, CSS, Node built-in test runner, PowerShell contract tests, browser responsive-mode verification.

**Spec:** `C:\Users\user\Desktop\frontend_v3\docs\07_P1_MOBILE_UX_DESIGN.md`

## Global Constraints

- Keep Vue CDN and a single `js/app.js`; do not introduce modules or a build tool.
- Preserve Adult HOME: sit-and-reach, cross sit-up, standing long jump, and 10m four-return shuttle run.
- Preserve Senior HOME: chair stand, sit-and-reach, two-minute step, and 3m chair target return.
- Preserve optional grip, CENTER, Under-19 blocking, PAR-Q routing, and negative flexibility.
- Radar normalization remains geometry only; it must never become a score, percentile, comparison, or prescription input.
- Missing radar values remain `null`; partial segments and full polygon rules remain unchanged.
- Percentile and average data remain backend-only, and the API request shape must not change.
- Keep `MOCK_WORKOUT_RECOMMENDATIONS` and privacy-enhanced YouTube iframe playback.
- Change only the current phase's screen and directly related CSS; do not pre-edit later screens.
- Run PowerShell contracts in a UTF-8-aware PowerShell host.
- This directory is not a Git repository. Replace commit checkpoints with test evidence and file hashes; do not initialize Git without separate approval.

---

### Task 1: P1-0 Baseline and official scope record

**Files:**
- Verify: `C:\Users\user\Desktop\frontend_v3_p0_baseline\P0_BASELINE_SHA256.txt`
- Modify: `C:\Users\user\Desktop\frontend_v3\docs\06_DECISION_LOG.md`
- Verify: `C:\Users\user\Desktop\frontend_v3\docs\07_P1_MOBILE_UX_DESIGN.md`

**Interfaces:**
- Consumes: the four P0 source hashes recorded in the baseline manifest.
- Produces: an immutable recovery point and an explicit P1/P2 scope decision used by every later task.

- [ ] **Step 1: Verify baseline hashes against copied files**

Run `Get-FileHash -Algorithm SHA256` for the four files in `frontend_v3_p0_baseline` and compare them to `P0_BASELINE_SHA256.txt`.

Expected: all four values match.

- [ ] **Step 2: Add the stage-scope decision**

Append this decision to `06_DECISION_LOG.md`:

```markdown
## [CONFIRMED / STAGE SCOPE UPDATE] P1 and P2

Previous P1: JavaScript file split and structural refactoring.

Superseded by: P1 = Mobile UX & Report Redesign.

P1 constraints:
- Keep Vue runtime.
- Keep single `app.js`.
- Preserve P0 policy, calculations, contracts, and behavior.
- Redesign information architecture, interaction, accessibility, and visual presentation only.

JavaScript file splitting into config/data/services/app is deferred to P2.
```

- [ ] **Step 3: Run the complete P0 suite**

Run the four `node --test tests/frontend-v3-p0-*.test.js` tests and invoke the four `.ps1` contract scripts directly in PowerShell.

Expected: eight passes and zero failures.

- [ ] **Step 4: Record the working-source hashes**

Record SHA-256 for `js/app.js`, `css/style.css`, `docs/index.html`, and `docs/06_DECISION_LOG.md` as the P1-0 checkpoint.

### Task 2: P1-1 Landing and Route selection

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js` landing and `routeSelect` template blocks.
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` landing, route-card, CTA, and mobile rules only.
- Create: `tests/frontend-v3-p1-landing-route.test.js`

**Interfaces:**
- Consumes: existing `go('login')`, `go('parq')`, `startCenterRoute()`, and `page` route names.
- Produces: semantic route-card buttons and unchanged navigation destinations for P1-2.

- [ ] **Step 1: Write the failing P1-1 contract test**

The Node test must assert that the template contains:

```js
assert.match(js, /체력 측정 시작/);
assert.match(js, /이미 센터에서 측정했다면/);
assert.match(js, /<button[^>]+fc-route-card[^>]+@click="go\('parq'\)"/);
assert.match(js, /<button[^>]+fc-route-card[^>]+@click="startCenterRoute"/);
assert.doesNotMatch(js, /74점|체력점수/);
assert.match(css, /\.fc-route-card[^}]*min-height:\s*120px/);
assert.match(css, /\.fc-btn[^}]*min-height:\s*48px/);
```

- [ ] **Step 2: Run the P1-1 test and confirm failure**

Run: `node --test tests/frontend-v3-p1-landing-route.test.js`

Expected: FAIL because current route cards are `div` elements and the landing lacks the center shortcut/value chips.

- [ ] **Step 3: Implement the Landing hierarchy**

Keep the existing start destination while rendering:

```html
<p class="fc-eyebrow">체력코치 AI</p>
<h1 class="fc-hero-title">내 체력을 직접 확인하고<br>다음 운동까지 이어가세요.</h1>
<p class="fc-hero-copy">약 10~15분이면 자가측정을 시작할 수 있어요.</p>
<ul class="fc-value-list" aria-label="서비스 특징">
  <li>자가측정 가능</li>
  <li>국민체력100 데이터 기반</li>
</ul>
<button class="fc-btn fc-btn-primary" @click="go('login')">체력 측정 시작</button>
<p class="fc-secondary-prompt">이미 센터에서 측정했다면 로그인 후 센터 결과를 입력할 수 있어요.</p>
```

Do not add scores, grades, or new routes.

- [ ] **Step 4: Implement semantic HOME/CENTER route cards**

Replace clickable `div` cards with `button type="button"` cards. Preserve `startCenterRoute` for CENTER and `go('parq')` for HOME. Use text labels (`HOME`, `CENTER`) and consistent inline SVG/icon treatment without mixing icon families.

- [ ] **Step 5: Add only P1-1 CSS**

Add landing value-chip, hero, selection-card, and 48px CTA rules. Keep the existing white/off-white/blue palette and desktop max-width. Do not edit form, PAR-Q, measurement, report, or recommendation selectors.

- [ ] **Step 6: Run focused and regression tests**

Run the new P1-1 Node test, measurement behavior test, style contract, and Under-19/navigation assertions.

Expected: all pass.

### Task 3: P1-2 Basic Information and PAR-Q

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js` data/computed/methods needed for question position plus Basic Info and PAR-Q template blocks.
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` form, segmented choice, PAR-Q question, and sticky-action rules only.
- Create: `tests/frontend-v3-p1-basic-parq.test.js`

**Interfaces:**
- Consumes: `form`, `basicInfoValid`, `under19Blocked`, `parqQuestions`, `parqAnswers`, `setParq`, and `submitParq`.
- Produces: `parqQuestionIndex`, `currentParqQuestion`, `answeredParqCount`, `showPreviousParq()`, and `answerCurrentParq(value)` while retaining `submitParq()` as the sole P0 decision point.

- [ ] **Step 1: Write failing Basic/PAR-Q behavior tests**

Assert semantic gender buttons with `aria-pressed`, connected labels and inputs, persistent units, one visible current question, `n / 7` progress, and unchanged `submitParq` routing.

- [ ] **Step 2: Run the focused test and confirm failure**

Expected: FAIL because gender uses clickable `div` elements and all seven PAR-Q questions render together.

- [ ] **Step 3: Add minimal question-position state**

Use an integer `parqQuestionIndex` initialized to `0`. `answerCurrentParq(value)` calls the existing `setParq(index, value)`, advances to the next unanswered question, and calls no safety decision logic. Final submission still calls `submitParq()`.

- [ ] **Step 4: Redesign Basic Information**

Wrap fields in one compact form card, use buttons for gender, add IDs/`for` links, keep age/height/weight `v-model` bindings, and show BMI as a neutral context value only when height and weight are valid.

- [ ] **Step 5: Redesign PAR-Q as one-question-at-a-time**

Show current count, progress, the unchanged current question text, large yes/no buttons, previous-question navigation, and the final existing submit action. Preserve every answer while navigating backward.

- [ ] **Step 6: Add sticky-action spacing and accessibility CSS**

Ensure at least 48px buttons, keyboard focus, visible selected state, and bottom padding that prevents the sticky CTA from covering fields.

- [ ] **Step 7: Verify P1-2**

Run the focused test, measurement test, Under-19 checks, and explicit PAR-Q all-NO/all-answered-with-YES checks.

### Task 4: P1-3 Measurement dashboard and single-test flow

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js` measurement-only state/computed/methods and HOME measurement template blocks.
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` dashboard, item-state, active-test, raw-input, guide, and sticky-action selectors.
- Create: `tests/frontend-v3-p1-measurement-ux.test.js`

**Interfaces:**
- Consumes: `battery`, `homeMeasuredItems`, `homeValues`, `gripOwned`, `measurementMin(item)`, `showMeasureGuide(item)`, `showMeasurementVideo(item)`, `homeInputAllFilled`, and `openReport()`.
- Produces: `activeMeasurementIndex`, `activeMeasurementItem`, `completedMeasurementCount`, `measurementState(item)`, `selectMeasurement(item)`, and `completeActiveMeasurement()`.

- [ ] **Step 1: Write failing measurement-UX tests**

Cover Adult four-item order, Senior four-item order, optional grip inclusion/exclusion, negative flexibility, completed count, active item, invalid input blocking, and direct report navigation after all required inputs.

- [ ] **Step 2: Run tests and confirm the new UX contract fails while P0 passes**

- [ ] **Step 3: Add derived measurement state without changing battery configuration**

Derive completion only from existing raw values and `isMeasurementValueValid`. Do not duplicate measurement rules or create fallback values.

- [ ] **Step 4: Build the measurement dashboard**

Render each item as a button with completed/current/waiting text and raw value for completed entries. Present optional grip as a separate add-on action.

- [ ] **Step 5: Build the one-test screen**

Show item count, factor and test names, concise method, guide/video actions, large numeric input and unit, retry/clear action, and `기록 완료`. Keep `:min="measurementMin(it)"` so flexibility can remain negative.

- [ ] **Step 6: Advance safely**

`completeActiveMeasurement()` validates the active raw value, advances to the next pending required item, and calls `openReport()` only when all required items are valid. Revisiting an item must not erase other measurements.

- [ ] **Step 7: Verify P1-3**

Run P1-3 tests plus all four P0 Node behavior tests and senior-flow contract.

### Task 5: P1-4 Radar and Report dashboard

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js` report template and presentation-only computed properties.
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` report-summary, radar, metric, comparison, unmeasured, and action sections.
- Create: `tests/frontend-v3-p1-report-ux.test.js`

**Interfaces:**
- Consumes without modifying: `RADAR_CONFIG`, `normalizeRadarValue`, `measuredRadarRuns`, `radarAxes`, `radarUserDots`, `radarUserSegments`, `radarUserPolygonPoints`, `radarAveragePolygonPoints`, `unmeasuredAxes`, and backend percentile results.
- Produces: presentation-only grouping for report summary, raw details, backend comparison, unmeasured actions, and next actions.

- [ ] **Step 1: Write failing report-UX tests**

Assert the section order, absence of visible 20/40/60/80/100 labels, raw value plus unit on axes, `미측정` copy, conditional backend comparison, Senior `참고값`, partial segment/full polygon conditions, and exercise CTA.

- [ ] **Step 2: Run focused tests and confirm failure**

- [ ] **Step 3: Reorder report information architecture**

Render summary → radar → raw details → peer comparison → unmeasured actions → recommendation CTA → center guidance. Do not change API requests or fitness interpretation.

- [ ] **Step 4: Simplify radar semantics**

Retain grid geometry but remove numeric scale labels. Make user data dominant, average secondary/dashed, and render raw/unit or `미측정` beside each axis label.

- [ ] **Step 5: Separate raw and percentile presentation**

Raw cards always show actual recorded values. A dedicated comparison block renders backend `topPercent`/interval only when present; otherwise show `또래 비교 준비 중` without generating a number.

- [ ] **Step 6: Make unmeasured areas actionable**

Use the existing `unmeasuredAxes` notes for grip and center guidance, preserving Senior HOME power as unmeasured and 3m as reference.

- [ ] **Step 7: Verify P1-4**

Run P1 report tests, all radar/percentile tests, report contract, senior contract, and measurement tests.

### Task 6: P1-5 Recommendation and Video

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js` recommendation/video presentation and presentation-only duration helpers.
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` routine and video-card selectors.
- Create: `tests/frontend-v3-p1-recommendation-video.test.js`

**Interfaces:**
- Consumes: `MOCK_WORKOUT_RECOMMENDATIONS`, `recommendedWorkout`, `openVideoLibrary()`, `dbVideos`, `extractYouTubeId`, and existing iframe components.
- Produces: ordered routine metadata, total duration display, thumbnail-first cards, and safe invalid-media state.

- [ ] **Step 1: Write failing recommendation/video tests**

Assert mock disclosure, numbered sequence, total duration, exercise count, per-item video action, privacy-enhanced embed, unavailable message, and no automatic external navigation.

- [ ] **Step 2: Confirm focused test failure**

- [ ] **Step 3: Render an ordered daily routine**

Use the existing mock items in their existing order. Calculate display totals only from their existing duration fields; do not rank or prescribe new exercises.

- [ ] **Step 4: Redesign video cards**

Show thumbnail, title, category/duration when available, and one video action. Invalid IDs render `현재 재생할 수 없는 영상입니다.` in place.

- [ ] **Step 5: Verify P1-5**

Run focused tests, P0 media test, recommendation-flow contract, report contract, and navigation tests.

### Task 7: P1-6 Global visual polish

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css` tokens, typography, spacing, radius, shadow, responsive, focus, and reduced-motion sections.
- Create: `tests/frontend-v3-p1-visual-contract.test.js`

**Interfaces:**
- Consumes: all P1 semantic classes introduced by Tasks 2–6.
- Produces: a coherent visual system without changing markup behavior.

- [ ] **Step 1: Write visual-token and accessibility contracts**

Assert primary/off-white/navy tokens, defined title/body/caption scale, 48px touch targets, constrained desktop width, 360px rules, focus-visible, and reduced-motion.

- [ ] **Step 2: Normalize tokens and hierarchy**

Consolidate repeated colors, spacing, radius, and shadow values at `:root`. Keep gradients subtle and reserve stronger emphasis for primary CTA and key dashboard components.

- [ ] **Step 3: Verify responsive behavior in CSS contracts**

Run P1 visual contract and existing style contract.

### Task 8: P1-7 Final regression and mobile verification

**Files:**
- Create: `C:\Users\user\Desktop\frontend_v3\docs\08_P1_VERIFICATION.md`
- Verify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Verify: `C:\Users\user\Desktop\frontend_v3\css\style.css`

**Interfaces:**
- Consumes: all completed P1 slices and every P0/P1 automated test.
- Produces: a reproducible completion record and final source hashes.

- [ ] **Step 1: Run JavaScript syntax and all automated tests**

Run `node --check` on `app.js`, every P0/P1 Node test, and all PowerShell contracts in the UTF-8-aware host.

Expected: zero failures.

- [ ] **Step 2: Exercise required flows in a browser**

At 360, 390, 430, and 480px verify Landing, HOME/CENTER route choice, Basic Information, Under-19 block, PAR-Q pass/fail, Adult/Senior measurement, optional grip, negative flexibility, report partial/full radar, percentile unavailable/available presentation, recommendation, valid YouTube, invalid video, focus navigation, and reduced motion.

- [ ] **Step 3: Compare P0 policies**

Diff P1 against `frontend_v3_p0_baseline` and inspect every change touching measurement configuration, normalization, backend payload, or mock data. Expected: no policy/data-contract modifications.

- [ ] **Step 4: Write the verification record**

Record commands, pass counts, manual viewport results, known runner constraint, and SHA-256 for final `app.js`, `style.css`, and docs.

- [ ] **Step 5: Final completion gate**

Confirm the official design Definition of Done line by line. Do not mark P1 complete if any automated test fails or any target viewport blocks its primary CTA.
