# P4 Flow, Auth & Report UX Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve P0–P3 policy, P2 module contracts, and the P3 responsive shell while replacing the approved P1 interaction patterns with P4 Auth entry, single-page PAR-Q, single-page HOME measurement, a simplified accessible Report, and Report-only Floating Chat.

**Architecture:** Keep Vue 3 global build, classic script loading, `window.FitnessCoach`, and the single `js/app.js` orchestration/template file. Add only UI state and methods required by P4, reuse existing measurement/percentile/video/chat services and data, and keep all policy calculations in their existing modules. Implement each slice test-first against the rendered application, then run all enduring contracts before continuing.

**Tech Stack:** Vue 3 global CDN build, plain JavaScript classic scripts, CSS, Node.js `node:test`, Playwright with installed Chrome, PowerShell 7 contract scripts.

**Spec:** `C:\Users\user\Desktop\frontend_v3\docs\12_P4_FLOW_AUTH_REPORT_DESIGN.md`

## Global Constraints

- Work in place at `C:\Users\user\Desktop\frontend_v3`; do not regenerate the application.
- P4 intentionally supersedes only P1 PAR-Q one-question-at-a-time and P1 Measurement Dashboard → Active Measurement presentation.
- Keep Adult HOME, Senior HOME, CENTER, optional grip, negative flexibility, and Under-19 policies unchanged.
- Keep Radar normalization, geometry, axis order, partial/full series behavior, raw values, and missing/null rules unchanged.
- Keep percentile and peer averages Backend-only.
- Keep `/api/health`, `/api/percentile`, `/api/report/summary`, `/api/videos`, `/api/coach`, and `/api/chat` contracts unchanged.
- Do not invent Auth endpoints, sessions, tokens, localStorage users, or successful Auth responses.
- Keep `js/config/*`, `js/data/*`, `js/utils/*`, `js/services/*`, and `docs/index.html` unchanged.
- Keep the P3 breakpoints and shell: mobile 320–767 full screen, tablet 768–1023 guttered, desktop 1024+ full viewport.
- Use the verified official center URL `https://nfa.kspo.or.kr/intro/centerList.kspo`.
- External tests live at `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests` and must continue targeting `C:\Users\user\Desktop\frontend_v3`.
- `frontend_v3` is not a Git repository. Do not initialize Git there; use fresh tests, hashes, and documented stage checkpoints instead of commit steps.

## File Map

**Product files modified**

- `C:\Users\user\Desktop\frontend_v3\js\app.js` — P4 UI state, computed validation, navigation, templates, official link, and Chat focus behavior.
- `C:\Users\user\Desktop\frontend_v3\css\style.css` — P4 Auth, PAR-Q list, compact measurement cards, Report grid/footer, and Floating Chat presentation.

**Documentation created or modified**

- Create `C:\Users\user\Desktop\frontend_v3\docs\P4_BASELINE_SHA256.txt` — exact pre-implementation hashes.
- Modify `C:\Users\user\Desktop\frontend_v3\docs\06_DECISION_LOG.md` — mark implementation completion only after verification.
- Create `C:\Users\user\Desktop\frontend_v3\docs\13_P4_VERIFICATION.md` — actual commands, PASS/FAIL/SKIP/BLOCKED, viewport results, and residual risks.

**External verification files created or modified**

- Create `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-policy-contract.test.js`.
- Create `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`.
- Modify superseded expectations in `frontend-v3-p1-basic-parq.test.js`, `frontend-v3-p1-measurement-ux.test.js`, `frontend-v3-p1-report-ux.test.js`, and `frontend-v3-p3-responsive-browser.test.js` while retaining enduring P0–P3 policy assertions.

---

### Task 1: Freeze the P4 Source Baseline and Add the P4 Test Harness

**Files:**
- Create: `C:\Users\user\Desktop\frontend_v3\docs\P4_BASELINE_SHA256.txt`
- Create: `C:\Users\user\Desktop\frontend_v3\docs\13_P4_VERIFICATION.md`
- Create: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-policy-contract.test.js`
- Create: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`

**Interfaces:**
- Consumes: current `frontend_v3` source and P4-0 verified test path.
- Produces: immutable baseline hashes plus reusable `openApp(width,height)`, `goToAuth(page)`, `continueAsGuest(page)`, and `fillBasicInfo(page, age)` browser helpers.

- [ ] **Step 1: Record baseline hashes before production edits**

Run from PowerShell:

```powershell
$target = 'C:\Users\user\Desktop\frontend_v3'
$files = @(
  'docs/index.html',
  'css/style.css',
  'js/app.js',
  'js/config/measurement-config.js',
  'js/config/radar-config.js',
  'js/config/video-config.js',
  'js/data/mock-data.js',
  'js/services/percentile-service.js',
  'js/services/report-service.js',
  'js/services/video-service.js',
  'js/utils/measurement-utils.js',
  'js/utils/radar-utils.js',
  'js/utils/youtube-utils.js'
)
$files | ForEach-Object {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $target $_)).Hash
  "$hash  $($_ -replace '\\','/')"
}
```

Save the exact output with the heading `# Stage P4 source baseline — 2026-09-11`.

- [ ] **Step 2: Create a real-browser P4 harness**

Use the same local static server, installed Chrome path, Vue CDN diagnostics, and cleanup pattern as `frontend-v3-p3-responsive-browser.test.js`. Add these exact helpers:

```javascript
async function goToAuth(page) {
  await page.getByRole('button', { name: '체력 측정 시작' }).click();
  await page.getByRole('heading', { name: '체력코치 AI' }).waitFor();
}

async function continueAsGuest(page) {
  await goToAuth(page);
  await page.getByRole('button', { name: '비로그인으로 이용하기' }).click();
  await page.getByRole('heading', { name: '측정에 필요한 정보만 알려주세요' }).waitFor();
}

async function fillBasicInfo(page, age = '34') {
  await page.getByRole('button', { name: '여성' }).click();
  await page.getByLabel('만 나이').fill(age);
  await page.getByLabel('키').fill('165');
  await page.getByLabel('체중').fill('60');
}

async function reachParq(width = 390, height = 844, age = '34') {
  const page = await openApp(width, height);
  await continueAsGuest(page);
  await fillBasicInfo(page, age);
  await page.getByRole('button', { name: '다음' }).click();
  await page.getByRole('button', { name: /직접 측정하기/ }).click();
  return page;
}
```

- [ ] **Step 3: Add an initial policy-contract test**

```javascript
test('P4 does not invent an Auth backend or alter protected API endpoints', () => {
  assert.doesNotMatch(appSource, /fetch\(['"`]\/api\/(?:login|signup|logout|session|profile)/);
  assert.doesNotMatch(appSource, /localStorage|sessionStorage/);
  for (const endpoint of ['/api/coach', '/api/chat']) {
    assert.match(appSource, new RegExp(endpoint.replace('/', '\\/')));
  }
});
```

- [ ] **Step 4: Run the existing baseline and new policy test**

Run:

```powershell
$env:NODE_PATH='C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node --test .\tests\*.test.js
```

Expected before P4 behavior tests are added: all existing 49 tests and the new policy test pass.

- [ ] **Step 5: Record the checkpoint**

Record the exact test count and baseline hashes in a temporary “P4-0” section of `docs/13_P4_VERIFICATION.md`; do not claim later P4 UI behavior yet.

---

### Task 2: Implement Auth Entry, Signup Validation, and Guest Continuation

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-policy-contract.test.js`

**Interfaces:**
- Consumes: existing `go('basicInfo')`, `form`, Basic Information page, and no-Auth-backend boundary.
- Produces: `authView`, `loginForm`, `signupForm`, `authNotice`, `loginFormValid`, `signupFormValid`, `showAuthUnavailable(kind)`, and `continueAsGuest()`.

- [ ] **Step 1: Write failing browser tests for the three branches**

```javascript
test('P4 Auth entry exposes Login, Signup, and Guest without fake success', async () => {
  const page = await openApp(390, 844);
  await goToAuth(page);
  await page.getByRole('button', { name: '로그인' }).waitFor();
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByRole('heading', { name: '회원가입' }).waitFor();
  await page.getByRole('button', { name: '비로그인으로 이용하기' }).click();
  await page.getByRole('heading', { name: '측정에 필요한 정보만 알려주세요' }).waitFor();
  await page.close();
});

test('P4 Signup validates only the confirmed frontend rules', async () => {
  const page = await openApp(390, 844);
  await goToAuth(page);
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByLabel('비밀번호', { exact: true }).fill('one');
  await page.getByLabel('비밀번호 확인').fill('different');
  await page.getByText('비밀번호가 일치하지 않습니다.').waitFor();
  await page.close();
});
```

- [ ] **Step 2: Run the Auth tests and verify RED**

Run:

```powershell
node --test --test-name-pattern="P4 Auth|P4 Signup" .\tests\frontend-v3-p4-flow-browser.test.js
```

Expected: FAIL because Signup and Guest controls do not exist.

- [ ] **Step 3: Add minimal Auth UI state and validation**

Add to `data()`:

```javascript
authView: 'login',
loginForm: { identifier: '', password: '' },
signupForm: {
  identifier: '', password: '', passwordConfirm: '',
  gender: '', age: '', height: '', weight: ''
},
authNotice: '',
```

Add computed properties:

```javascript
loginFormValid() {
  return Boolean(this.loginForm.identifier.trim() && this.loginForm.password);
},
signupPasswordMismatch() {
  return Boolean(this.signupForm.passwordConfirm) &&
    this.signupForm.password !== this.signupForm.passwordConfirm;
},
signupFormValid() {
  const age = Number(this.signupForm.age);
  const height = Number(this.signupForm.height);
  const weight = Number(this.signupForm.weight);
  return Boolean(
    this.signupForm.identifier.trim() &&
    this.signupForm.password &&
    this.signupForm.password === this.signupForm.passwordConfirm &&
    this.signupForm.gender &&
    Number.isFinite(age) && age > 0 &&
    Number.isFinite(height) && height > 0 &&
    Number.isFinite(weight) && weight > 0
  );
},
```

Add methods:

```javascript
showAuthUnavailable(kind) {
  if (kind === 'signup' && this.signupForm.password !== this.signupForm.passwordConfirm) {
    this.authNotice = '비밀번호가 일치하지 않습니다.';
    return;
  }
  this.authNotice = '현재 인증 서버가 연결되지 않아 이 기능을 사용할 수 없습니다.';
},
continueAsGuest() {
  this.authNotice = '';
  this.go('basicInfo');
},
```

Replace the Mock login template with tab/segment controls for Login and Signup plus an independent `비로그인으로 이용하기` button. Do not copy Signup profile values into `form` because no account was created.

- [ ] **Step 4: Add Auth CSS without changing breakpoints**

Add `.fc-auth-switch`, `.fc-auth-panel`, `.fc-auth-divider`, `.fc-auth-notice`, and `.fc-signup-profile`. Keep the existing `.fc-page-login` 720px desktop reading width and use one column on mobile.

- [ ] **Step 5: Run Auth and enduring entry tests**

```powershell
node --test .\tests\frontend-v3-p4-policy-contract.test.js .\tests\frontend-v3-p4-flow-browser.test.js .\tests\frontend-v3-p1-landing-route.test.js .\tests\frontend-v3-p1-basic-parq.test.js
```

Expected: PASS for Auth, Guest → Basic, Basic validation, and no invented Auth contracts.

- [ ] **Step 6: Record the P4-1 checkpoint**

Capture `app.js` and `style.css` hashes plus exact test output in the verification working notes.

---

### Task 3: Replace PAR-Q Presentation and Improve Center Guidance

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p1-basic-parq.test.js`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`

**Interfaces:**
- Consumes: `parqQuestions`, `parqAnswers`, `setParq(index,value)`, `parqAnswered`, and unchanged `submitParq()`.
- Produces: seven visible `.fc-parq-item` rows and verified external center-search links.

- [ ] **Step 1: Replace superseded P1 assertions with enduring policy assertions**

Remove the test that requires one-question-at-a-time. Keep a direct state test proving all seven answers are stored and `submitParq()` still uses `parqAnswers.some(a => a === true)`.

```javascript
test('P4 PAR-Q retains seven answers and the existing YES decision', () => {
  const App = loadApp();
  const state = App.data();
  for (let index = 0; index < 7; index += 1) {
    App.methods.setParq.call(state, index, index === 4);
  }
  assert.deepEqual(state.parqAnswers, [false, false, false, false, true, false, false]);
  assert.match(App.methods.submitParq.toString(), /parqAnswers\.some\(a => a === true\)/);
});
```

- [ ] **Step 2: Write failing rendered-flow tests**

```javascript
test('P4 shows all seven PAR-Q questions and requires every answer', async () => {
  const page = await reachParq();
  assert.equal(await page.locator('.fc-parq-item').count(), 7);
  const submit = page.getByRole('button', { name: '확인하고 다음' });
  assert.equal(await submit.isDisabled(), true);
  await page.locator('.fc-parq-item').getByRole('button', { name: '아니오' }).all().then(buttons => Promise.all(buttons.map(button => button.click())));
  assert.equal(await submit.isEnabled(), true);
  await page.close();
});

test('P4 routes one YES to Center Guidance and exposes the verified official link', async () => {
  const page = await reachParq();
  const rows = page.locator('.fc-parq-item');
  for (let index = 0; index < 7; index += 1) {
    await rows.nth(index).getByRole('button', { name: index === 2 ? '예' : '아니오' }).click();
  }
  await page.getByRole('button', { name: '확인하고 다음' }).click();
  const link = page.getByRole('link', { name: '가까운 체력인증센터 찾기' });
  assert.equal(await link.getAttribute('href'), 'https://nfa.kspo.or.kr/intro/centerList.kspo');
  assert.equal(await link.getAttribute('rel'), 'noopener');
  await page.close();
});
```

- [ ] **Step 3: Run PAR-Q tests and verify RED**

Expected failures: only one `.fc-parq-focus` exists, the new CTA copy is absent, and Center Guidance still uses a root-domain `window.open` button.

- [ ] **Step 4: Implement the seven-question template**

Use:

```html
<section class="fc-parq-list" aria-labelledby="parq-heading">
  <article class="fc-parq-item" v-for="(question,index) in parqQuestions" :key="index">
    <h2 :id="'parq-question-'+index"><span>{{ index + 1 }}</span>{{ question }}</h2>
    <div class="fc-yn" :aria-labelledby="'parq-question-'+index">
      <button type="button" :class="['no',parqAnswers[index]===false?'active':'']"
        :aria-pressed="parqAnswers[index]===false" @click="setParq(index,false)">아니오</button>
      <button type="button" :class="['yes',parqAnswers[index]===true?'active':'']"
        :aria-pressed="parqAnswers[index]===true" @click="setParq(index,true)">예</button>
    </div>
  </article>
</section>
<div class="fc-sticky-action">
  <button class="fc-btn fc-btn-primary" :disabled="!parqAnswered" @click="submitParq">확인하고 다음</button>
</div>
```

Keep `parqQuestionIndex`, `currentParqQuestion`, and the old navigation methods in code unless a later exact-diff review proves they are safe to remove.

- [ ] **Step 5: Replace Center Guidance copy and root URL**

Use a semantic external link:

```html
<a class="fc-btn fc-btn-outline" href="https://nfa.kspo.or.kr/intro/centerList.kspo"
   target="_blank" rel="noopener" aria-label="가까운 체력인증센터 찾기, 새 창">
  가까운 체력인증센터 찾기
</a>
```

Keep CENTER result input and official exercise video actions available; keep HOME and personalized prescription visually locked after a YES result.

- [ ] **Step 6: Add PAR-Q single-column styles**

Keep `.fc-page-parq` at 680px and `.fc-parq-list` one column at every breakpoint. Only the YES/NO controls may remain side-by-side.

- [ ] **Step 7: Update P3 browser helpers**

Change Guest navigation and answer each visible PAR-Q row by index. Remove the P3 assertion that requires `.fc-parq-focus`; replace it with a body-content width assertion no greater than 720px.

- [ ] **Step 8: Run focused and full tests**

Run the P4 browser tests, P0 measurement tests, updated P1 PAR-Q tests, and P3 responsive browser tests. Expected: all pass; one YES still blocks HOME and all NO reaches HOME measurement.

---

### Task 4: Replace HOME Dashboard/Active Measurement with Compact Single-Page Cards

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p1-measurement-ux.test.js`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`

**Interfaces:**
- Consumes: `battery`, `homeMeasuredItems`, `homeValues`, `measurementMin(item)`, `measurementValueValid(item,value)`, `homeInputAllFilled`, `showMeasureGuide(item)`, `showMeasurementVideo(item)`, and `openReport()`.
- Produces: ordered `.fc-measure-card` inputs bound directly to existing `homeValues[item.code]`.

- [ ] **Step 1: Replace superseded P1 UI assertions**

Keep tests for Adult/Senior item counts, optional grip, and existing validation. Remove requirements for `.fc-measure-dashboard`, `.fc-active-measurement`, and `completeActiveMeasurement()` navigation. Add:

```javascript
test('P4 binds every HOME card directly to the existing homeValues record', () => {
  assert.match(source, /v-for="\(it,i\) in homeMeasuredItems"/);
  assert.match(source, /v-model="homeValues\[it\.code\]"/);
  assert.match(source, /:min="measurementMin\(it\)"/);
  assert.match(source, /:disabled="!homeInputAllFilled"/);
});
```

- [ ] **Step 2: Write failing Adult and Senior browser tests**

For Adult, assert this exact order: 앉아윗몸앞으로굽히기, 교차윗몸일으키기, 제자리멀리뛰기, 10m 4회 왕복달리기. Fill `-5` for flexibility and valid values for the remaining required cards; verify submission stays disabled until grip is explicitly set to measured or not measured.

For Senior, set age 70 and assert: 의자에 앉았다 일어서기, 앉아윗몸앞으로굽히기, 2분 제자리걷기, 의자에 앉아 3m 표적 돌아오기. Verify no HOME power estimate appears.

- [ ] **Step 3: Run focused tests and verify RED**

Expected: FAIL because the current page renders dashboard buttons and only one active input.

- [ ] **Step 4: Implement the compact-card template**

```html
<div class="fc-measure-grid">
  <article class="fc-measure-card" v-for="(it,i) in homeMeasuredItems" :key="it.code">
    <div class="fc-measure-card-head">
      <span>{{ i + 1 }}</span><h2>{{ it.name }}</h2>
    </div>
    <label class="fc-label" :for="'measure-'+it.code">측정값</label>
    <div class="fc-raw-input">
      <input :id="'measure-'+it.code" type="number" step="any" inputmode="decimal"
        :min="measurementMin(it)" v-model="homeValues[it.code]" />
      <span>{{ it.unit }}</span>
    </div>
    <div class="fc-input-actions">
      <button type="button" class="fc-measure-guide-btn" @click="showMeasureGuide(it)">측정 방법</button>
      <button v-if="measurementVideoFor(it)" type="button" class="fc-measure-video-btn"
        @click="showMeasurementVideo(it)">영상 보기</button>
    </div>
  </article>
</div>
```

Place the existing explicit grip selection before the final sticky CTA. When `gripOwned===true`, `homeMeasuredItems` includes the grip card; when false it does not. Do not create a second values object.

- [ ] **Step 5: Add responsive compact-card CSS**

Mobile uses one column. At 768px and above use `grid-template-columns: repeat(2,minmax(0,1fr))`. Do not equalize card heights; preserve DOM order and prevent horizontal overflow.

- [ ] **Step 6: Run validation, guide, and video regressions**

Verify negative flexibility, required invalid values, optional grip true/false/null, guide drawer, YouTube measurement drawer, Adult/Senior ordering, direct Report transition, and CENTER input unchanged.

- [ ] **Step 7: Record the P4-3 checkpoint**

Run all Node tests and PowerShell contracts before starting Report work.

---

### Task 5: Simplify Report, Improve Radar Text Access, and Link Directly to Center Search

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p1-report-ux.test.js`
- Modify: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p3-responsive-browser.test.js`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`

**Interfaces:**
- Consumes: unchanged `radarAxes`, `comparisonRows`, `unmeasuredList`, `radar*Points`, `radar*Segments`, and `radar*Dots`.
- Produces: `radarAccessibleDescription`, simplified Report order, direct external center CTA, and footer note.

- [ ] **Step 1: Write failing Report tests**

Add this browser fixture before the tests so the rendered Report uses literal raw values without depending on unavailable Backend responses:

```javascript
async function openAdultReport({ includeGrip }) {
  const page = await openApp(1440, 900);
  await page.evaluate(({ includeGrip }) => {
    const vm = document.querySelector('#app').__vue_app__._instance.proxy;
    vm.form = { gender: '여성', age: '34', height: '165', weight: '60' };
    vm.route = 'HOME';
    vm.gripOwned = includeGrip;
    vm.homeValues = {
      sit_and_reach: '12',
      cross_situp: '35',
      standing_long_jump: '180',
      agility_shuttle: '12.5',
      grip_strength: includeGrip ? '32' : ''
    };
    vm.percentileResults = [];
    vm.chartLoading = false;
    vm.reportSummaryLoading = false;
    vm.reportSummary = '측정 결과 요약';
    vm.page = 'report';
  }, { includeGrip });
  await page.getByRole('heading', { name: '나의 체력 리포트' }).waitFor();
  return page;
}
```

```javascript
test('P4 Report removes duplicate raw cards but keeps raw values on Radar', async () => {
  const page = await openAdultReport({ includeGrip: true });
  assert.equal(await page.locator('.fc-report-raw-section').count(), 0);
  await page.getByText('12cm', { exact: true }).waitFor();
  await page.getByText(/32kg/).waitFor();
  await page.getByText(/상대악력/).waitFor();
  await page.close();
});

test('P4 Report exposes accessible Radar values and a footer disclaimer', async () => {
  const page = await openAdultReport({ includeGrip: false });
  const label = await page.locator('.fc-radar').getAttribute('aria-label');
  assert.match(label, /유연성.*12cm/);
  assert.match(label, /악력.*미측정/);
  await page.locator('.fc-report-footer-note').getByText(/의학적 진단을 대체하지 않습니다/).waitFor();
  await page.close();
});
```

- [ ] **Step 2: Run Report tests and verify RED**

Expected: duplicate `.fc-report-raw-section` exists, current SVG label lacks raw values, and footer-note class is absent.

- [ ] **Step 3: Add the accessible description without changing geometry**

```javascript
radarAccessibleDescription() {
  return this.radarAxes.map(axis => {
    const reference = this.ageGroup === 'senior' && axis.valueCode === 'chair_sit_and_reach_3m'
      ? ', 참고값, 백분위 미제공'
      : '';
    return `${axis.label} ${axis.measured ? axis.raw : '미측정'}${reference}`;
  }).join('; ');
},
```

Bind it as `:aria-label="'체력 프로필 레이더 차트. '+radarAccessibleDescription"`. Keep `viewBox="0 0 300 300"` and every existing polygon/segment/dot condition unchanged.

- [ ] **Step 4: Remove only the duplicate visual raw section**

Delete the `.fc-report-raw-section` template. Do not delete `axis.raw`, `axis.chartRaw`, `axis.averageValue`, Report payload fields, or Radar labels.

- [ ] **Step 5: Reorder the Report and update the center/footer elements**

Use the order Summary → Radar → Peer Comparison → Unmeasured → Recommendation action → Center action → footer. Replace the internal center-navigation button with the verified external link and use:

```html
<footer class="fc-report-footer-note">
  본 리포트는 자가측정 기반 참고 정보이며,<br>
  국민체력100 공식 인증 결과가 아닙니다.<br>
  의학적 진단을 대체하지 않습니다.
</footer>
```

- [ ] **Step 6: Remove the obsolete desktop raw-section grid rules**

Create a desktop grid with Radar and Peer Comparison in the second row, Unmeasured and Recommendation in the next available row, and Center/footer spanning the full width. Verify no empty grid track remains when `unmeasuredList` is empty.

- [ ] **Step 7: Run Report regressions**

Verify raw values/units, grip kg and relative %, missing null, partial/full Radar, peer Backend available/unavailable, Senior 3m reference, no score labels, Recommendation, and direct center link.

---

### Task 6: Replace the Report Chat Section with an Accessible Floating Chat

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\js\app.js`
- Modify: `C:\Users\user\Desktop\frontend_v3\css\style.css`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-policy-contract.test.js`
- Test: `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\frontend-v3-p4-flow-browser.test.js`

**Interfaces:**
- Consumes: unchanged `chatMessages`, `chatInput`, `chatLoading`, `chatInitialized`, `openChat()` API body, and `sendChat()` API body/history.
- Produces: `closeChat()`, `handleChatDialogKeydown(event)`, trigger/input refs, Report-only floating trigger, and responsive dialog.

- [ ] **Step 1: Write failing Chat accessibility tests**

Intercept `/api/coach` and `/api/chat` in Playwright with complete responses. Assert the floating control only exists on Report, opening moves focus to the Chat input, Tab remains within the dialog, ESC closes it, and focus returns to the trigger.

```javascript
await page.route('**/api/coach', route => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ answer: '측정 결과를 확인했습니다.' })
}));
await page.route('**/api/chat', route => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ answer: '안전한 범위에서 천천히 시작하세요.' })
}));
```

Also capture requests and assert the existing endpoint, method, `user_id`, `message`, and `history` shapes remain unchanged.

- [ ] **Step 2: Run Chat tests and verify RED**

Expected: no floating trigger, no focus transfer/return, and current Chat uses the general drawer.

- [ ] **Step 3: Add explicit open/close/focus methods**

```javascript
async openChat() {
  this.videoSidebarOpen = false;
  this.guideSidebarOpen = false;
  this.measurementVideoSidebarOpen = false;
  this.chatSidebarOpen = true;
  await this.$nextTick();
  this.$refs.chatInput?.focus();
  if (this.chatInitialized || this.chatLoading) return;
  this.chatLoading = true;
  const ranked = this.radarAxes.filter(axis => axis.compared).slice()
    .sort((a,b) => Number(b.topPercent) - Number(a.topPercent));
  const focus = ranked[0]?.label || '전신 체력';
  const context = this.radarAxes.filter(axis => axis.measured)
    .map(axis => `${axis.label} ${axis.raw}`).join(', ');
  try {
    const response = await fetch('/api/coach', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        user_id:'fitness-report-user',
        question:`${focus} 보완 운동을 추천해줘`,
        age:Number(this.form.age),
        sex:this.form.gender,
        height_cm:Number(this.form.height),
        weight_kg:Number(this.form.weight),
        goal:`${focus} 보완`,
        equipment:'없음',
        home_measurement_context:context
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '하네스 준비 실패');
    const answer = data.answer || {};
    const intro = typeof answer === 'string' ? answer :
      [answer['운동명'],answer['추천이유'],answer['운동방법']].filter(Boolean).join('\n');
    this.chatMessages.push({role:'assistant',content:intro || '측정 결과를 바탕으로 대화 준비가 완료되었습니다. 궁금한 점을 물어보세요.'});
    this.chatInitialized = true;
  } catch (error) {
    this.chatMessages.push({role:'assistant',content:'하네스 연결 오류: '+String(error.message || error)});
  } finally {
    this.chatLoading = false;
  }
},
closeChat() {
  this.chatSidebarOpen = false;
  this.$nextTick(() => this.$refs.chatTrigger?.focus());
},
handleChatDialogKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    this.closeChat();
    return;
  }
  if (event.key !== 'Tab') return;
  const controls = [...event.currentTarget.querySelectorAll(
    'button:not([disabled]),input:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'
  )];
  if (!controls.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
},
```

Change global `handleEscape` so Chat uses `closeChat()`; keep other drawer closing unchanged.

- [ ] **Step 4: Replace the general Report Chat section**

Add outside the scrolling Report body but inside `.fc-phone`:

```html
<button v-if="page==='report'" ref="chatTrigger" class="fc-chat-fab"
  aria-label="체력코치 AI에게 질문하기" @click="openChat">AI</button>
<aside v-if="chatSidebarOpen" class="fc-chat-panel" role="dialog" aria-modal="true"
  aria-labelledby="chat-panel-title" @keydown="handleChatDialogKeydown">
  <header><h2 id="chat-panel-title">체력코치 AI</h2>
    <button type="button" @click="closeChat" aria-label="채팅 닫기">×</button>
  </header>
  <div class="fc-chat-messages">
    <div v-for="(message,index) in chatMessages" :key="index"
      :class="['fc-chat-bubble',message.role]">{{ message.content }}</div>
    <div v-if="chatLoading" class="fc-chat-bubble assistant">답변을 준비하고 있습니다…</div>
  </div>
  <form class="fc-chat-form" @submit.prevent="sendChat">
    <input ref="chatInput" class="fc-input" v-model="chatInput" maxlength="500"
      autocomplete="off" placeholder="질문 입력" aria-label="질문 입력">
    <button class="fc-btn fc-btn-primary" type="submit"
      :disabled="chatLoading || !chatInitialized || !chatInput.trim()">전송</button>
  </form>
</aside>
```

Backdrop clicks call `closeChat()` for Chat so focus is restored.

- [ ] **Step 5: Add responsive Floating Chat CSS**

Use a fixed 48px trigger with `right:max(18px,env(safe-area-inset-right))` and bottom spacing that clears safe areas and sticky controls. Desktop panel is bounded near 380×560px; mobile panel is a bottom sheet with `max-height:calc(100dvh - 88px)`, messages as the only flexible scroll region, and the form retained above `env(safe-area-inset-bottom)`.

- [ ] **Step 6: Run Chat and API contract tests**

Verify init, send, error, ESC, focus open/return, Tab trap, Report-only trigger, mobile keyboard-sized viewport, endpoint/payload invariance, and no overlap at 320×568 and 200% zoom equivalent.

---

### Task 7: Reconcile Superseded Tests and Run Full Responsive Regression

**Files:**
- Modify: superseded P1/P3 tests listed in the File Map.
- Test: all `C:\Users\user\Documents\Codex\2026-09-08\figma-plugin-figma-openai-curated-remote\tests\*.test.js`
- Test: all four current PowerShell contract files.

**Interfaces:**
- Consumes: completed P4 UI.
- Produces: one coherent suite where P0/P2/P3 contracts remain protected and P1-only presentation assertions are explicitly superseded.

- [ ] **Step 1: Audit every changed legacy assertion**

Delete or replace only assertions that require one-question PAR-Q, Dashboard/Active Measurement, duplicate raw Report cards, Mock login, or Radar beside raw section. Keep business-policy assertions.

- [ ] **Step 2: Run all JavaScript tests**

```powershell
$env:NODE_PATH='C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node --test .\tests\*.test.js
```

Expected: zero failures. Record the new file and test counts from output.

- [ ] **Step 3: Run PowerShell contracts with the UTF-8-capable runtime**

```powershell
Get-ChildItem .\tests\*.ps1 | Sort-Object Name | ForEach-Object {
  & pwsh -NoProfile -File $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "$($_.Name) failed" }
}
```

Expected: 4/4 PASS. Do not use Windows PowerShell 5.1 because these UTF-8-no-BOM scripts contain Korean regular expressions.

- [ ] **Step 4: Run JavaScript syntax and protected hashes**

Run `node --check` for all 11 current JavaScript files. Compare `js/config/*`, `js/data/*`, `js/utils/*`, `js/services/*`, and `docs/index.html` against `P4_BASELINE_SHA256.txt`. Expected protected mismatches: 0.

- [ ] **Step 5: Run viewport matrix**

Exercise 320×568, 390×844, 430×932, 768×1024, 820×1180, 1024×768, 1440×900, and 1920×1080. Assert no horizontal overflow/clipping, preserved shell metrics, single `.fc-body` scrolling, sticky input visibility, Radar labels, Floating Chat placement, safe-area spacing, keyboard order, and 200%-zoom usability.

- [ ] **Step 6: Inspect the exact product diff**

Confirm changes are limited to `js/app.js` and `css/style.css`. Verify no new Auth fetch, storage, or service file and no modification to protected API bodies, Radar calculations, recommendation selection, or YouTube lifecycle.

---

### Task 8: Document P4 Results and Refresh the Existing Preview

**Files:**
- Modify: `C:\Users\user\Desktop\frontend_v3\docs\13_P4_VERIFICATION.md`
- Modify: `C:\Users\user\Desktop\frontend_v3\docs\06_DECISION_LOG.md`
- Deployment source: the existing private preview Site, updated only after all verification passes.

**Interfaces:**
- Consumes: fresh verification output and exact final hashes.
- Produces: reproducible P4 report and updated mobile/tablet review URL.

- [ ] **Step 1: Write the verification report using actual results only**

Include:

```text
1. P4-0 Current-state audit
2. CONFLICT and superseded UI decisions
3. Backend Auth support
4. BLOCKED/OUT OF SCOPE
5. Stage-by-stage implementation
6. Changed files
7. Protected hash comparison
8. app.js and API diff judgment
9. Actual commands and test counts
10. PASS/FAIL/SKIP/BLOCKED
11. Viewport results
12. Remaining risks
```

Mark real signup/login/logout/session/profile checks `BLOCKED`, not PASS.

- [ ] **Step 2: Update Decision Log completion status**

Append `[CONFIRMED / P4 COMPLETE]` only after every required current-Frontend check passes. Preserve `[BLOCKED] Backend Auth contract required`.

- [ ] **Step 3: Run one final verification after documentation edits**

Repeat all Node tests, PowerShell contracts, syntax checks, protected hashes, and viewport checks. Require exit code 0 and fresh output before making completion claims.

- [ ] **Step 4: Refresh the existing private preview**

Copy only the verified final `css`, `js`, and root-adjusted `index.html` into the existing preview staging project, save a new Site version, deploy it privately, wait for `succeeded`, and return the exact existing preview URL. Do not change audience or create a second Site.

- [ ] **Step 5: Final report**

Report changed files, exact test counts, protected hash result, blocked Auth capabilities, viewport result, and preview URL. Do not report any unexecuted check as PASS.
