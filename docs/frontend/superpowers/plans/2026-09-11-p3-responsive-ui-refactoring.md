# Stage P3 Responsive UI Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Preserve the P0/P1/P2 product behavior while turning the existing mobile-first shell into a deliberate responsive application at 320px through 1920px.

**Architecture:** Keep Vue 3, the existing classic-script dependency order, and `window.FitnessCoach`. Make CSS the primary implementation layer, add only presentation classes to existing `.fc-body` elements in `js/app.js`, keep `.fc-body` as the single page scroll owner, and leave every protected config/data/utils/service module unchanged.

**Tech Stack:** Vue 3 global build, classic JavaScript, HTML, CSS Grid/Flexbox, Node built-in test runner, PowerShell contracts, browser viewport inspection.

**Spec:** `C:\Users\user\Desktop\frontend_v3\docs\superpowers\specs\2026-09-11-p3-responsive-ui-refactoring-design.md`

## Global Constraints

- Target the existing `C:\Users\user\Desktop\frontend_v3`; do not regenerate it.
- Preserve P0 policy, P1 mobile information order, P2 modules, Vue state, computed properties, methods, bindings, events, API contracts, Radar calculations, and YouTube lifecycle.
- Keep classic scripts, no bundler, no native ES modules, and the current `docs/index.html` load order.
- Do not modify `js/config/*`, `js/data/*`, `js/utils/*`, or `js/services/*`.
- Keep Radar `viewBox="0 0 300 300"`, geometry, axis order, missing/null behavior, and partial-series rules unchanged.
- Keep one app-internal scroll model with `.fc-body` as the normal content scroll owner.
- Treat tests under the Codex workspace as external verification assets; do not claim they are packaged in `frontend_v3`.
- The target is not a Git repository. Replace commit steps with SHA-256 and diff checkpoints.

---

### Task 1: Lock the P3 baseline and add responsive contract coverage

**Files:**
- Create: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`
- Create: `C:\Users\user\Desktop\frontend_v3\docs\P3_BASELINE_SHA256.txt`
- Verify: `C:\Users\user\Desktop\frontend_v3\docs\superpowers\specs\2026-09-11-p3-responsive-ui-refactoring-design.md`

**Interfaces:**
- Consumes: current CSS selectors and Vue template markup.
- Produces: a persistent external browser-behavior test and a pre-change target hash manifest.

- [x] **Step 1: Write a failing responsive browser test**

Start a local static server from the test, launch installed Chrome through the bundled Playwright package, and assert observable layout results: a 600px viewport is no longer trapped at 430px, a desktop viewport has a full-width shell with a centered `.fc-body` content area no wider than 1180px, the shell stays inside the viewport, `.fc-body` is the scrolling element for long content, and the page remains free of horizontal overflow. Navigate through the existing UI to exercise page layouts rather than searching CSS source text.

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

test('P3 expands the application shell at 600px and desktop widths', async () => {
  const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
  const page = await browser.newPage({ viewport: { width: 600, height: 900 } });
  await page.goto(appUrl);
  const mediumWidth = await page.locator('.fc-phone').evaluate(el => el.getBoundingClientRect().width);
  assert.ok(mediumWidth >= 560, `expected a fluid shell at 600px, got ${mediumWidth}`);
  await page.setViewportSize({ width: 1440, height: 900 });
  const desktop = await page.locator('.fc-phone').evaluate(el => el.getBoundingClientRect());
  assert.ok(desktop.width >= 1000 && desktop.width <= 1200);
  assert.ok(desktop.height <= 900);
  await browser.close();
});
```

- [x] **Step 2: Run the contract and verify RED**

Run:

```powershell
$env:NODE_PATH='C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node --test .\tests\frontend-v3-p3-responsive-browser.test.js
```

Expected: FAIL because P3 page classes, desktop breakpoint, and explicit shell height are not implemented.

- [x] **Step 3: Record the pre-change SHA-256 manifest**

Use `Get-FileHash -Algorithm SHA256` for `docs/index.html`, `css/style.css`, `js/app.js`, and every file under `js/config`, `js/data`, `js/utils`, and `js/services`. Save exact relative paths and hashes to `docs/P3_BASELINE_SHA256.txt`.

- [x] **Step 4: Verify the documentation correction**

Confirm the spec labels the P2 counts as historical and limits current reproducible P3-0 verification to JavaScript syntax and matching hashes.

---

### Task 2: Implement P3-1 responsive shell and scroll foundation

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css:50-130`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css:463-500`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`

**Interfaces:**
- Consumes: `.fc-root`, `.fc-phone`, `.fc-topbar`, `.fc-body`, `.fc-sticky-action`.
- Produces: one viewport-bounded application shell and one internal content scroll owner.

- [x] **Step 1: Add exact foundation assertions**

Require `height:100dvh` on the mobile shell, `min-height:0`, `.fc-body{min-height:0;overflow-y:auto}`, and separate 768px and 1024px minimum-width rules.

- [x] **Step 2: Run the focused test and verify RED**

Run the P3 browser test and confirm the medium/desktop shell and scroll-behavior assertions fail for the pre-P3 layout.

- [x] **Step 3: Implement mobile-first shell CSS**

Implement these semantics without changing visual tokens:

```css
.fc-root{height:100vh;height:100dvh;padding:0;overflow:hidden}
.fc-phone{width:100%;max-width:none;height:100vh;height:100dvh;min-height:0;border:0;border-radius:0;box-shadow:none}
.fc-topbar{flex:0 0 auto}
.fc-body{min-width:0;min-height:0;overscroll-behavior:contain}
```

At 768px add outer gutter and a tablet shell; at 1024px set a bounded desktop maximum near 1200px. Use `height:calc(100dvh - 40px)` or the tested viewport-safe equivalent at larger widths.

- [x] **Step 4: Stabilize sticky and safe-area spacing**

Keep the topbar outside `.fc-body`; ensure `.fc-sticky-action` uses safe-area bottom padding and does not cover the final content. Do not switch to document scrolling.

- [x] **Step 5: Run focused and existing style contracts**

Run the P3 browser test and `frontend-v3-style-contract.ps1`. If the historical style contract encodes the old 430px shell, update only that external test to assert the new P3 contract and label it as an external test asset.

- [x] **Step 6: Record a foundation hash checkpoint**

Confirm only `css/style.css`, the external P3 test, and the baseline manifest changed.

---

### Task 3: Implement P3-2 entry-flow responsiveness

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js:445-511`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`

**Interfaces:**
- Consumes: existing Landing, Login, Basic Information, and Route Selection DOM.
- Produces: `.fc-page-login`, `.fc-page-basic`, and `.fc-page-route` hooks without changing DOM order or behavior.

- [x] **Step 1: Add failing template-hook and layout assertions**

Drive the UI to Basic Information and Route Selection. Assert that route cards form one column on mobile and two columns on tablet/desktop, while Basic Information remains within its intended reading width and all original controls remain reachable in DOM order.

- [x] **Step 2: Run focused test and verify RED**

- [x] **Step 3: Add presentation classes only**

Change existing class attributes, for example:

```html
<div class="fc-body fc-page-basic" v-if="page==='basicInfo'">
<div class="fc-body fc-page-route" v-if="page==='routeSelect'">
```

Do not move or rewrite `v-if`, `@click`, `v-model`, `:disabled`, `aria-*`, or user-facing copy.

- [x] **Step 4: Add responsive entry-flow CSS**

At tablet and desktop widths, use a two-column route grid with navigation and introductory content spanning both columns. Keep Login and Basic Information at a readable width; allow only the Basic Information field card to use a limited two-column arrangement where labels and units remain connected.

- [x] **Step 5: Run P1 entry, Basic Information, PAR-Q, and header tests**

Run the relevant external Node tests plus the P3 contract. Confirm navigation and Under-19 behavior remain unchanged.

- [x] **Step 6: Review the `app.js` diff**

Verify the diff contains class-attribute changes only in this slice.

---

### Task 4: Implement P3-3 safety and measurement responsiveness

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js:514-652`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`

**Interfaces:**
- Consumes: PAR-Q, HOME guide, measurement dashboard, active measurement, CENTER input, and CENTER guidance.
- Produces: page hooks and selective grids while preserving question focus and one-measurement focus.

- [x] **Step 1: Add failing assertions for safety and measurement hooks**

Drive the existing UI through PAR-Q, HOME measurement, and CENTER input. Assert the PAR-Q and active measurement cards remain single bounded reading columns, CENTER fields form the intended responsive grid, and no viewport gains horizontal overflow.

- [x] **Step 2: Run focused test and verify RED**

- [x] **Step 3: Add page classes to existing body elements**

Do not change template branches, measurement `v-for`, state expressions, validation attributes, buttons, or navigation.

- [x] **Step 4: Add responsive safety and measurement CSS**

- Keep PAR-Q centered in a bounded reading column.
- Keep active measurement in one bounded column.
- Permit HOME guide cards and CENTER fields to use two columns at suitable widths.
- Permit dashboard and optional grip to share space only on wide screens while DOM order remains unchanged.
- Keep 320px controls, touch targets, and negative-flexibility input usable.

- [x] **Step 5: Run measurement and policy regression tests**

Run P0 measurement, P1 Basic/PAR-Q, P1 measurement UX, senior-flow, and P3 responsive contracts.

- [x] **Step 6: Review template-only diff**

Confirm no `data()`, computed property, method, handler, validation, measurement config, or route semantics changed.

---

### Task 5: Implement P3-4 report and Radar responsiveness

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js:654-728`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`

**Interfaces:**
- Consumes: existing report sections and protected Radar SVG.
- Produces: `.fc-page-report` and responsive report regions without altering semantic order.

- [x] **Step 1: Add failing report/Radar responsive assertions**

Open a report state through the existing Vue flow or an isolated browser setup that uses the real application instance. Assert the rendered Radar grows within its container on large screens, its legend remains unclipped, report columns use available space, and the live SVG retains `viewBox="0 0 300 300"`.

- [x] **Step 2: Run focused test and verify RED**

- [x] **Step 3: Add the report page class only**

Retain the exact report section order: summary, Radar, raw values, peer comparison, unmeasured, action, center guidance.

- [x] **Step 4: Implement bounded report grids**

Use CSS Grid so Radar and detail sections use tablet/desktop width without reordering the mobile DOM. Keep raw values primary and peer comparison separate. Make the Radar container larger only through CSS; preserve labels, legend colors, partial series, and missing data.

- [x] **Step 5: Run Radar, percentile, report UX, and report contract tests**

Confirm `viewBox`, normalization, missing/null, Backend-only average/percentile, and section order all pass.

- [x] **Step 6: Compare protected Radar-related hashes**

Confirm `js/config/radar-config.js` and `js/utils/radar-utils.js` match the baseline manifest.

---

### Task 6: Implement P3-5 recommendation, video, and drawer responsiveness

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js:730-783`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`

**Interfaces:**
- Consumes: ordered routine, video list, guide/video/chat drawers, and current embedded player.
- Produces: `.fc-page-recommend` and `.fc-page-video` hooks plus responsive cards/dialogs.

- [x] **Step 1: Add failing recommendation/media assertions**

Drive the real UI to Recommendation and Video, then open each relevant drawer. Assert visible routine/video columns, bounded desktop drawer width, full-width mobile drawer behavior, reachable close controls, and a 16:9 embedded frame from computed dimensions.

- [x] **Step 2: Run focused test and verify RED**

- [x] **Step 3: Add presentation classes only**

Keep workout order, Mock labels, `v-for`, video API state, drawer conditions, and click handlers unchanged.

- [x] **Step 4: Implement responsive recommendation and media CSS**

- Keep routine sequence visually explicit.
- Use two-column video cards only when card content remains readable.
- Keep drawers full-width on mobile and bounded on larger screens.
- Preserve independently scrollable drawer content and 16:9 YouTube frames.
- Keep chat input and close control reachable at narrow and short heights.

- [x] **Step 5: Run recommendation, media, and YouTube contracts**

Run P0 media, P1 recommendation/video, recommendation-flow PowerShell, report PowerShell, and P3 responsive contracts.

- [x] **Step 6: Compare video-related protected hashes**

Confirm video config, YouTube utility, and video service hashes are unchanged.

---

### Task 7: Complete P3-6 viewport, zoom, focus, and motion polish

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: browser runtime using `C:\Users\user\Desktop\frontend_v3\docs\index.html`

**Interfaces:**
- Consumes: all previous responsive slices.
- Produces: final narrow, tablet, desktop, zoom, focus, orientation, safe-area, and reduced-motion presentation.

- [x] **Step 1: Serve the existing app without changing delivery format**

Run a temporary local static server for browser inspection. Do not add server files to `frontend_v3`.

- [x] **Step 2: Inspect every required viewport**

Verify 320×568, 360×800, 390×844, 430×932, 480×900, 768×1024, 820×1180, 1024×768, 1280×800, 1440×900, and 1920×1080.

- [x] **Step 3: Capture representative screenshots**

Capture 390×844, 820×1180, and 1440×900 for Landing/Route plus information-dense Report or Recommendation screens where reachable without inventing data.

- [x] **Step 4: Check interaction presentation**

Verify horizontal overflow, clipping, sticky CTA overlap, drawer width, close control, iframe aspect ratio, keyboard focus, 200% zoom, orientation, Radar label/legend clipping, mobile order, and reduced motion.

- [x] **Step 5: Apply only evidenced CSS polish**

Adjust gutters, `minmax()`, wrapping, reading widths, and short-height behavior only where a checked viewport demonstrates a problem. Do not change templates or product logic during polish.

- [x] **Step 6: Repeat failed viewport checks**

Recheck every viewport affected by a CSS adjustment and retain the representative final screenshots outside the product source tree or in a clearly labeled verification-output location.

---

### Task 8: Run P3-7 regression, hash/diff review, and documentation

**Files:**
- Create: `C:\Users\user\Desktop\frontend_v3\docs\11_P3_VERIFICATION.md`
- Modify: `C:\Users\user\Desktop\frontend_v3\docs\06_DECISION_LOG.md`
- Verify: all product and test files

**Interfaces:**
- Consumes: completed P3 presentation changes and baseline manifest.
- Produces: evidence-backed final verification and stage decision record.

- [x] **Step 1: Run JavaScript syntax checks**

Run `node --check` against all 11 current target JavaScript files. Record exact current count and failures.

- [x] **Step 2: Run every external test asset actually present**

Run all discovered `.test.js` files and PowerShell contracts from the Codex workspace. Report their location and explicitly state they are not packaged inside `frontend_v3`.

- [x] **Step 3: Compare protected-module hashes**

Compare final hashes against `docs/P3_BASELINE_SHA256.txt`. All config/data/utils/services hashes must match.

- [x] **Step 4: Review `app.js` and `index.html` changes**

Confirm `docs/index.html` remains unchanged. Diff `js/app.js` against the P3 baseline or P1 baseline source and verify all P3 changes are template presentation classes/wrappers only. Confirm no state, computed, methods, events, APIs, Radar geometry, or media lifecycle changed.

- [x] **Step 5: Run final browser regression**

Recheck Landing, Login, Basic Information, HOME/CENTER route selection, Under-19 blocking, PAR-Q pass/fail, Adult/Senior measurement flows, optional grip, negative flexibility, partial/full Radar, Backend comparison unavailable/available presentation, recommendation, video, and drawers to the extent supported by the current standalone frontend.

- [x] **Step 6: Document results precisely**

Write `docs/11_P3_VERIFICATION.md` using the requested 12-part report format. Separate historical P2 counts, target-local reproducible checks, external workspace tests actually executed, browser results, skipped checks, risks, and out-of-scope findings.

- [x] **Step 7: Record the P3 decision**

Append a `[CONFIRMED / P3 COMPLETE]` entry to `docs/06_DECISION_LOG.md` describing the responsive shell, app-internal scroll model, selective multi-column policy, and preserved P0/P1/P2 invariants.

- [x] **Step 8: Perform final placeholder and scope scans**

Scan the new plan and verification docs for unfinished placeholders and ambiguous claims. Search product diffs for changes outside the approved presentation files. Resolve documentation errors only; report any policy conflict or out-of-scope issue without implementing it.
