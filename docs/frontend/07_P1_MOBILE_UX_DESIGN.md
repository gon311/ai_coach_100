# Stage P1 — Mobile UX & Report Redesign Design

Date: 2026-09-09  
Status: Approved — official P1 design  
Target: `C:\Users\user\Desktop\frontend_v3`

## 1. Purpose

P1 turns the verified P0 webview into a mobile fitness-measurement coach that is easy to use during an actual measurement session. It changes information order, layout, interaction, and visual hierarchy without changing P0 policy, data meaning, or backend contracts.

The top-level product principle is:

> 사용자가 체력측정을 시작하고, 진행 상황을 이해하고, 자신의 실제 기록과 또래 비교를 해석한 뒤, 다음 운동 행동까지 최소한의 탐색으로 도달할 수 있는 모바일 웹뷰를 만든다.

The attached healthcare UI is a directional reference, not a screen to copy. P1 adopts its selection cards, step-by-step input, compact dashboard, and prominent CTA structure while retaining the existing white/blue fitness-coach identity.

## 2. Stage boundaries

P1 keeps:

- Vue CDN runtime and the single `js/app.js` file.
- Existing P0 routes, policies, validation rules, measurement batteries, backend request shape, and mock prescription data.
- `Measurement Raw Value`, `Radar Display Value`, and backend `Percentile` as separate concepts.
- YouTube privacy-enhanced iframe playback.
- Existing focus-visible and reduced-motion behavior.

P1 must not:

- Split `app.js` or introduce a build tool.
- Migrate Vue to React or another framework.
- Change Adult HOME, Senior HOME, CENTER, Under-19, PAR-Q, optional grip, or negative-flexibility rules.
- Change radar normalization or expose its 0–100 geometry as a score.
- Generate percentile, average, strength/weakness, or prescription decisions in the frontend.
- Invent or alter a backend API contract.
- Develop a new recommendation algorithm.

JavaScript structure refactoring is deferred to P2.

## 3. P0 baseline protection

The immutable baseline is `C:\Users\user\Desktop\frontend_v3_p0_baseline`. It contains the four P0 source files and `P0_BASELINE_SHA256.txt`.

Verified source hashes:

| File | SHA-256 |
| --- | --- |
| `css/style.css` | `A849BFBFBA65A67083D337AC10D48271928CF22C9D44E8E1FE269273338EB600` |
| `docs/06_DECISION_LOG.md` | `E2164362D10CF9D6561E16DA5FF4E521CA9258F62D36B936ADC79193B196CE6C` |
| `docs/index.html` | `16D9C4EC91A3C07041149843388FEBFF3ADFB532AC29536608AE1A046FD79CB7` |
| `js/app.js` | `880A9406B433DFC9C52F91B05A6D3862C4C0779372C1CFF2BF2B467ED468B142` |

All eight P0 tests pass when the PowerShell contract scripts are executed in a UTF-8-aware PowerShell host. Windows PowerShell 5.1 must not be used without explicitly selecting UTF-8 because it corrupts Korean regex literals. This is a runner constraint, not a product failure.

`06_DECISION_LOG.md` will receive a `[CONFIRMED / STAGE SCOPE UPDATE]` entry stating that the earlier JavaScript-splitting definition of P1 is superseded by mobile UX and report redesign, and that file splitting moves to P2.

## 4. Change-isolation strategy

P1 uses incremental vertical slices. Each slice changes only the screen and CSS directly related to that phase. A later screen is not redesigned early. After every slice, its focused checks and relevant P0 regression tests run before the next slice starts.

The sequence is:

1. P1-1 Landing and Route selection
2. P1-2 Basic Information and PAR-Q
3. P1-3 Measurement UX
4. P1-4 Radar and Report
5. P1-5 Recommendation and Video
6. P1-6 Global visual polish
7. P1-7 Full regression and mobile verification

This makes regressions attributable to a single phase and avoids an unreviewable full-template rewrite.

## 5. Global interaction model

Every screen has one primary goal. Standard screens show a back action, current step, and concise supporting state. Measurement screens prioritize actual item progress such as `2 / 4 완료` over an abstract page percentage.

Primary actions use a bottom-accessible CTA with at least a 48px touch target and sufficient content padding so the CTA never covers the final field. Selection cards are semantic buttons whose entire surface is clickable. Selected, completed, waiting, reference, blocked, and unmeasured states use text or badges in addition to color.

The content remains mobile-first at 360–480px and retains a constrained webview width on larger screens rather than stretching into a desktop dashboard.

## 6. Screen design

### 6.1 Landing and Route selection

Landing communicates the service value within the first viewport: direct fitness measurement, approximate duration, self-measurement availability, and National Fitness 100 data context. It has one dominant `체력 측정 시작` CTA and a secondary path for users who already have center results. No synthetic score appears.

Route selection uses two large, fully clickable HOME and CENTER cards. Each card explains what happens next and exposes an unambiguous selected state.

### 6.2 Basic Information and PAR-Q

Basic Information becomes a compact card form. Gender is a segmented, semantic selection; age, height, and weight keep explicit labels and units. BMI remains contextual information only and receives no invented risk grade.

PAR-Q becomes a question-focused seven-step interaction with current-question progress and large `아니오`/`예` choices. The wording, answer storage, and P0 pass/fail route are unchanged. Any YES continues to use the existing safety path.

### 6.3 Measurement

A measurement dashboard precedes individual tests. It shows required item count, completed count, raw result for completed items, current item, waiting items, and optional grip separately.

The active test screen focuses on one item. Test name, concise method, guide/video access, raw input, unit, retry, and completion action remain close together. Numeric input configuration follows the item: flexibility accepts negatives, time and count inputs keep their existing nonnegative policy, and optional grip remains optional.

Completing a valid item advances to the next pending item while preserving the ability to revisit a completed item. Completing all required items continues directly to the report as established in P0.

### 6.4 Radar and Report

The report order is:

1. Result summary
2. Fitness-profile radar
3. Detailed raw measurements
4. Peer comparison
5. Unmeasured areas
6. Exercise-recommendation CTA
7. Center guidance

The summary states the route and number of completed items. It may mention backend-provided comparison conclusions only when those conclusions exist; the frontend does not infer strengths or priorities.

Radar is a visual profile, not a scorecard. Visible 20/40/60/80/100 labels are removed or visually suppressed. Axis labels show the factor, raw value, and unit. Unmeasured axes say `미측정`, have no user dot, and are not converted to zero. Partial results draw dots and only adjacent measured segments. A closed, filled polygon appears only when every axis is measured. Backend average uses a lighter secondary or dashed treatment and renders only when valid backend data exists.

Metric details present raw values first. Percentile or an interval appears in a separate peer-comparison area only when supplied by the backend; otherwise the UI says that peer comparison is being prepared. Senior chair stand maps to muscular endurance, the 3m return remains a `참고값`, HOME power remains unmeasured unless valid CENTER data exists, and grip is shown only when actually measured.

The unmeasured section is actionable. It explains how optional grip can be added or which data requires center measurement without implying a zero result.

### 6.5 Recommendation and Video

Recommendation changes from an undifferentiated card list to an ordered daily routine. It shows total duration, exercise count, numbered sequence, phase, exercise, duration, and video action. `MOCK_WORKOUT_RECOMMENDATIONS` remains the source, and development UI identifies the prescription as mock data.

Video cards prioritize thumbnails and concise metadata. Playback stays inside the webview with the current YouTube iframe path. Invalid or non-YouTube values show `현재 재생할 수 없는 영상입니다.` and never trigger automatic external navigation.

## 7. Visual system

The final visual pass standardizes tokens only after the screen slices work:

- White and off-white backgrounds, blue primary, navy text, restrained neutral/status colors.
- Clear type hierarchy: 26–30px page title, 22–28px primary metric, 17–20px section title, 14–16px body, 12–13px caption.
- Distinct selection, metric, action, warning, reference, and video-card hierarchy.
- Moderate radius and soft shadow; no glassmorphism, heavy 3D, strong gradients, or decorative card overload.
- One consistent icon style. Emoji are not mixed arbitrarily with unrelated icon sets.
- Motion is limited to selection feedback, progress, drawer/page transitions, and radar reveal, with reduced-motion support.

## 8. Accessibility and error handling

- Every input has an associated label and persistent unit.
- Selectable cards use button semantics and `aria-pressed` or the appropriate selected state.
- Guide drawers use dialog semantics, sensible focus handling, and Escape close.
- Keyboard order follows the visual order, and focus indicators remain visible.
- Status meaning never depends only on color.
- Backend percentile failure clears comparison data without exposing technical chart errors or fabricating fallback values.
- Invalid media stays in context with a safe unavailable message.
- Existing validation messages remain attached to the relevant item.

## 9. Verification strategy

After each phase, run the relevant focused tests plus all P0 tests that touch the changed flow. Final regression covers:

- Adult HOME four items and optional grip.
- Senior HOME four items and optional grip.
- CENTER and Under-19 block.
- PAR-Q pass and fail.
- Negative flexibility validation.
- Radar normalization, partial segments, full polygon, and missing `null` state.
- Backend percentile unavailable and available states.
- Senior 3m reference behavior.
- Embedded YouTube and invalid-video handling.
- Mock prescription and report-to-recommendation navigation.

Manual browser verification runs at 360, 390, 430, and 480px. It checks first-viewport CTA visibility, one-hand measurement usability, progress clarity, raw/percentile/radar separation, unmeasured representation, recommendation sequence, focus behavior, and reduced motion.

## 10. Definition of done

P1 is complete when users can select a route through large cards, understand their current stage, complete one measurement at a time, read raw results without mistaking radar geometry for a score, distinguish backend peer comparison from frontend visualization, see unmeasured items as missing rather than zero, and move directly from the report to an ordered exercise routine and embedded video.

All P0 regression tests must pass, all target mobile widths must be usable, Vue CDN and the single `app.js` must remain, and no P0 policy or data contract may change.
