# P1 Radar Refinement and P2 Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the existing `frontend_v3` files to add brand-to-Landing navigation and blue/orange filled Radar series, freeze a verified P1 baseline, and split the existing JavaScript by responsibility without changing behavior.

**Architecture:** Preserve Vue CDN and the current templates. P2 uses classic dependency-ordered scripts that publish existing constants and functions through `window.FitnessCoach`, retaining direct `file://` execution without a bundler.

**Tech Stack:** HTML, CSS, JavaScript, Vue 3 global build, Node test runner, PowerShell contract tests.

**Spec:** `docs/superpowers/specs/2026-09-09-p1-radar-p2-structure-design.md`

## Global Constraints

- Modify the existing files in `C:\Users\user\Desktop\frontend_v3`; do not regenerate the application.
- Preserve P0 measurement batteries, Radar ranges, percentile rules, Backend contracts, and Mock recommendation selection.
- Keep Vue CDN, the existing UI structure, and direct `file://` execution.
- Do not introduce frontend-derived grades, scores, averages, or percentiles.
- Peer averages appear only when Backend data is available.
- This directory is not a Git repository; use tests and SHA-256 manifests instead of commits.

---

### Task 1: Header and Radar refinement

**Files:**
- Modify: `js/app.js`
- Modify: `css/style.css`
- Modify: workspace `tests/frontend-v3-p1-report-ux.test.js`
- Create: workspace `tests/frontend-v3-p1-header-navigation.test.js`

**Interfaces:**
- Consumes: existing `go('landing')`, `radarUserPolygonPoints`, `radarAveragePolygonPoints`, and partial segment models.
- Produces: semantic brand button and blue/orange high-opacity filled polygons.

- [ ] Write tests requiring brand button navigation, blue user fill, orange average fill, matching legend colors, and unchanged partial-data behavior.
- [ ] Run focused tests and observe failures caused by the missing header button and orange/high-opacity styles.
- [ ] Modify only the existing header template and Radar SVG/CSS.
- [ ] Run focused tests and the full P0/P1 suite.
- [ ] Browser-check brand navigation, full/partial Radar behavior, and 360/390/430/480px layout.

### Task 2: Freeze the verified P1 baseline

**Files:**
- Create: `C:\Users\user\Desktop\frontend_v3_p1_baseline\**`
- Create: `C:\Users\user\Desktop\frontend_v3_p1_baseline\P1_BASELINE_SHA256.txt`
- Modify: `docs/08_P1_VERIFICATION.md`

**Interfaces:**
- Consumes: fully verified Task 1 project tree.
- Produces: byte-for-byte P1 recovery reference and checksum manifest.

- [ ] Verify the exact baseline destination and confirm it is absent or empty.
- [ ] Copy the verified existing project without altering the source.
- [ ] Generate SHA-256 hashes for implementation and documentation files.
- [ ] Compare source and baseline hashes and require zero mismatches.

### Task 3: Extract configuration and Mock data

**Files:**
- Create: `js/config/measurement-config.js`
- Create: `js/config/radar-config.js`
- Create: `js/config/video-config.js`
- Create: `js/data/mock-data.js`
- Modify: `js/app.js`
- Modify: `docs/index.html`
- Create: workspace `tests/frontend-v3-p2-module-contract.test.js`

**Interfaces:**
- Produces: `FitnessCoach.measurementConfig`, `FitnessCoach.radarConfig`, `FitnessCoach.videoConfig`, and `FitnessCoach.mockData`.
- `app.js` aliases the same existing constant names from these namespace members.

- [ ] Write a failing namespace and script-order contract test.
- [ ] Run it and observe missing files/exports.
- [ ] Move the existing constants verbatim into the four files and expose frozen namespace objects.
- [ ] Replace removed declarations in `app.js` with namespace aliases.
- [ ] Add classic scripts to `docs/index.html` in dependency order.
- [ ] Run the module contract and full regression suite.

### Task 4: Extract pure utilities

**Files:**
- Create: `js/utils/measurement-utils.js`
- Create: `js/utils/radar-utils.js`
- Create: `js/utils/youtube-utils.js`
- Modify: `js/app.js`
- Modify: `docs/index.html`
- Modify: workspace `tests/frontend-v3-p2-module-contract.test.js`

**Interfaces:**
- Produces: `FitnessCoach.measurementUtils`, `FitnessCoach.radarUtils`, and `FitnessCoach.youtubeUtils`.
- Functions retain their current signatures and outputs.

- [ ] Extend the contract test to execute pure helpers from the namespace.
- [ ] Run it and observe missing utility exports.
- [ ] Move existing pure functions without changing algorithms.
- [ ] Alias them in `app.js` and load utility scripts after configuration/data.
- [ ] Run focused behavior tests and the full regression suite.

### Task 5: Extract Backend services

**Files:**
- Create: `js/services/percentile-service.js`
- Create: `js/services/report-service.js`
- Create: `js/services/video-service.js`
- Modify: `js/app.js`
- Modify: `docs/index.html`
- Modify: workspace `tests/frontend-v3-p2-module-contract.test.js`

**Interfaces:**
- Produces async `FitnessCoach.services.loadPercentiles`, `loadReportSummary`, and `loadWorkoutVideos` functions.
- Services accept existing payload/category inputs and return response data or stable unavailable errors; they do not calculate domain results.

- [ ] Extend the contract test for endpoint, method, payload, response, and parser-error behavior.
- [ ] Run it and observe missing service exports.
- [ ] Move fetch/parsing responsibility into services with dependency-injected `fetchImpl` for tests.
- [ ] Keep Vue methods responsible for loading flags and user-facing fallback copy.
- [ ] Load services before `app.js` and run the full regression suite.

### Task 6: Final P2 verification and documentation

**Files:**
- Create: `docs/09_P2_STRUCTURE.md`
- Create: `docs/10_P2_VERIFICATION.md`
- Modify: `docs/06_DECISION_LOG.md`

**Interfaces:**
- Consumes: Tasks 1–5 final tree.
- Produces: documented module ownership, load order, invariant list, and evidence-backed verification result.

- [ ] Run syntax checks for every JavaScript file.
- [ ] Run all P0/P1/P2 Node tests and PowerShell contracts.
- [ ] Browser-check `file://` and local HTTP startup, navigation, Adult HOME, Senior HOME, CENTER, PAR-Q, Radar, percentile states, recommendation, and video error UI.
- [ ] Render 360/390/430/480px mobile widths.
- [ ] Record final SHA-256 hashes and test counts in `docs/10_P2_VERIFICATION.md`.
- [ ] Update `docs/06_DECISION_LOG.md` with confirmed P2 structure and unchanged policy contracts.
