# Stage P3 Responsive UI Refactoring Verification

- Date: 2026-09-11
- Target: `C:\Users\user\Desktop\frontend_v3`
- Scope: Responsive presentation layer only

## 1. Current-state audit

P3 started from the P2 classic-script structure recorded in `docs/09_P2_STRUCTURE.md`. Vue 3 global build, `window.FitnessCoach`, all ten dependency scripts, and `js/app.js` remain loaded in their original order. The pre-P3 shell was full-screen only through 480px, constrained to 430px from 481px through 767px, and constrained to 720px from 768px upward. Its declared `.fc-body` overflow did not have a definite parent height, so the effective scroll owner could vary with content.

## 2. Prompt-level corrections

The P2 counts in `docs/10_P2_VERIFICATION.md` are historical evidence. The corresponding Node and PowerShell runners are not packaged inside `frontend_v3`. Current external test assets were found in the Codex workspace and were executed from that location; they are reported separately from target-local reproducible checks.

The P3-0 design document was corrected before implementation so it does not describe historical P2 counts as newly reproducible from the target folder.

## 3. Code/document conflict

`CONFLICT: None`

No current code behavior contradicted a confirmed or blocked policy in `docs/06_DECISION_LOG.md`.

## 4. Responsive and scroll strategy

P3 formalizes strategy A: app-internal scrolling at every breakpoint.

- `html`, `body`, `.fc-root`, and `.fc-phone` are viewport-bounded.
- `.fc-body` is the normal page-content scroll owner.
- The topbar remains outside the scrolling body.
- Sticky CTAs remain inside `.fc-body` with safe-area bottom padding.
- Drawers remain viewport-fixed and independently scrollable.
- 320–767px uses a full-screen shell.
- 768–1023px uses a guttered tablet shell.
- 1024px and above uses a full-viewport shell; only the `.fc-body` content area is centered and limited by page type.

## 5. Stage changes

### P3-1 — Responsive foundation

- Removed the 430px shell trap from 481–767px.
- Added explicit viewport-bounded shell height.
- Made `.fc-body` the deterministic content scroll owner.
- Kept sticky and safe-area behavior.

### P3-2 — Entry flow

- Kept Landing and Login visually restrained.
- Constrained Basic Information to a readable desktop width.
- Placed HOME and CENTER route cards side by side on tablet and desktop.

### P3-3 — Safety and measurement

- Kept PAR-Q and Active Measurement in bounded single reading columns.
- Arranged CENTER input fields in two columns on tablet and desktop.
- Used tablet width for HOME guide cards.
- Preserved the measurement dashboard, validation, optional grip, and navigation behavior.

### P3-4 — Report and Radar

- Placed Radar and raw measurement details beside each other on desktop.
- Increased the CSS-only Radar maximum to 460px on wider screens.
- Allowed the Radar legend to wrap without clipping.
- Preserved report DOM order, Radar viewBox, data mapping, missing values, partial segments, and Backend-only peer data.

### P3-5 — Recommendation and media

- Arranged ordered routine cards and video cards in two desktop columns.
- Kept step numbering and Mock recommendation meaning unchanged.
- Corrected the mobile measurement-video frame from a forced 200px minimum to a responsive 16:9 ratio.
- Kept drawers full-width on mobile and bounded on larger screens.

### P3-6 — Responsive polish

- Verified all required viewport sizes.
- Verified narrow sticky CTA visibility, keyboard focus indication, reduced motion, portrait/landscape dimensions, a 200%-zoom-equivalent CSS viewport, drawer controls, and iframe ratio.

### P3 desktop shell refinement

- Removed desktop-only outer padding from `.fc-root`.
- Expanded `.fc-phone` to the full viewport width and height at 1024px and above.
- Removed the desktop shell border, radius, shadow, and maximum-width constraint.
- Kept the topbar full width while limiting the effective `.fc-body` content area to 1180px for general, Report, Recommendation, and Video screens.
- Preserved the existing 720px Login/Basic width, 920px Measurement Dashboard width, and 680–720px focused PAR-Q/Active Measurement/Safety Guidance widths.
- Removed the superseded 1280px global `padding-inline: 56px` override.
- Did not change the 768–1023px tablet frame or the 767px-and-below mobile presentation.

## 6. Changed files

Product source:

- `css/style.css`
- `js/app.js` — presentation classes only

Documentation:

- `docs/P3_BASELINE_SHA256.txt`
- `docs/11_P3_VERIFICATION.md`
- `docs/06_DECISION_LOG.md`
- `docs/superpowers/specs/2026-09-11-p3-responsive-ui-refactoring-design.md`
- `docs/superpowers/plans/2026-09-11-p3-responsive-ui-refactoring.md`

External Codex workspace verification assets, not packaged in `frontend_v3`:

- `tests/frontend-v3-p3-responsive-browser.test.js`
- `tests/frontend-v3-p3-capture.js`
- `tests/frontend-v3-p1-visual-contract.test.js` — removed the superseded 430px shell assertion

`docs/index.html` and all protected modules were not modified.

## 7. Protected-module hash comparison

All 10 protected files match `docs/P3_BASELINE_SHA256.txt`:

```text
js/config/measurement-config.js  MATCH
js/config/radar-config.js        MATCH
js/config/video-config.js        MATCH
js/data/mock-data.js             MATCH
js/services/percentile-service.js MATCH
js/services/report-service.js     MATCH
js/services/video-service.js      MATCH
js/utils/measurement-utils.js    MATCH
js/utils/radar-utils.js          MATCH
js/utils/youtube-utils.js        MATCH
```

Protected mismatches: `0`.

## 8. app.js and index.html diff judgment

`docs/index.html` retained SHA-256:

```text
EDBD3BB1273AFF33BC95C86400635DE66D147FBF79185A14C37960C17838DE05
```

P3 added 11 presentation classes to existing `.fc-body` class attributes:

```text
fc-page-login
fc-page-basic
fc-page-route
fc-page-parq
fc-page-home-guide
fc-page-measure
fc-page-center-input
fc-page-center-guidance
fc-page-report
fc-page-recommend
fc-page-video
```

Removing those 11 class tokens in memory produces the exact pre-P3 `app.js` SHA-256:

```text
A38D38081E1EA988E3F2B054D84236168DC27897EA3406229EC81A2CB147220A
```

This proves the P3 `app.js` change is limited to presentation class additions. State, computed properties, methods, bindings, events, APIs, navigation, Radar geometry, and video lifecycle are unchanged.

## 9. Actual checks and results

Target-local reproducible checks:

- Current JavaScript files: 11
- JavaScript syntax: 11/11 PASS
- Protected hashes: 10/10 MATCH
- `docs/index.html` baseline hash: MATCH
- Normalized `app.js` baseline hash: MATCH

External Codex workspace assets actually executed on the P3 result:

- Node test files: 13/13 PASS
- Node assertions/tests: 49/49 PASS
- PowerShell contracts: 4/4 PASS
- Browser layout assertions are included in the 49 Node tests.

The browser test used installed Chrome with bundled Playwright and loaded the existing Vue CDN dependency. Network permission was required only to load that existing CDN resource.

The four current PowerShell contract files were executed with PowerShell 7.6.5. They are UTF-8 files without a BOM; Windows PowerShell 5.1 does not decode their Korean regular expressions correctly and is not reported as a valid contract run.

## 10. Checks not reproducible from frontend_v3 alone

The historical P2 Node and PowerShell counts cannot be rerun from `frontend_v3` alone because their runners are not included in that folder. They remain historical evidence in `docs/10_P2_VERIFICATION.md`.

The current P3 external workspace tests were actually executed, but another worker receiving only `frontend_v3` will not have those test files. No claim is made that the target folder contains a packaged test runner.

Actual browser zoom UI controls were not automated. A 720×450 CSS viewport was used as the responsive-layout equivalent of viewing a 1440×900 surface at 200% zoom; focus visibility was tested independently with keyboard navigation.

## 11. Viewport and visual verification

Automated Chrome checks passed at:

```text
320×568
360×800
390×844
430×932
480×900
768×1024
820×1180
1024×768
1280×800
1440×900
1920×1080
```

All sizes passed shell containment and horizontal-overflow checks. Sticky CTA, mobile drawer, desktop drawer, close control, 16:9 measurement video, Radar width/viewBox, legend overflow, keyboard focus, and reduced motion also passed.

Representative screenshots:

- `outputs/p3/390x844-landing.png`
- `outputs/p3/820x1180-route.png`
- `outputs/p3/1440x900-report.png`

The screenshots are stored in the external Codex workspace, not the product source folder.

## 12. Remaining risks and follow-up

The application still depends on the existing remote Vue CDN. Offline direct-file use cannot mount Vue unless that dependency is already available. P3 does not alter this delivery decision.

```text
OUT OF SCOPE
- 문제: `homeGuide` 화면 템플릿은 존재하지만 현재 navigation method에서 직접 도달하는 경로가 없다.
- 근거: `TITLE_MAP`과 template에는 `homeGuide`가 있으나 `go('homeGuide')` 호출이 없다.
- 영향: P3에서는 화면의 반응형 표현을 검증할 수 있지만 제품 흐름에서 직접 진입할 수 없다.
- 권장 후속 Stage: Navigation/product-flow review
```

No route was added because navigation changes are explicitly outside P3.
