# Stage P3 — Responsive UI Refactoring Design

- Date: 2026-09-11
- Status: Approved design
- Target: `C:\Users\user\Desktop\frontend_v3`
- Scope: Presentation-layer responsive refactoring only

## 1. Objective

P3 preserves the verified P0 policy, P1 mobile UX, and P2 JavaScript structure while allowing tablet and desktop layouts to use additional space selectively. The application must stop looking like a narrow phone mockup above mobile widths without turning every screen into a dashboard.

## 2. Source of truth

The implementation follows this order:

1. Confirmed and blocked entries in `docs/06_DECISION_LOG.md`
2. Current executable code and API contracts
3. `docs/09_P2_STRUCTURE.md`
4. `docs/10_P2_VERIFICATION.md`
5. `docs/07_P1_MOBILE_UX_DESIGN.md`
6. `docs/08_P1_VERIFICATION.md`
7. Earlier specs and plans
8. P3 presentation requirements

No policy conflict was found during P3-0. If a policy or API conflict appears during implementation, the affected slice stops and is reported instead of being resolved by inference.

## 3. Current-state audit

The application uses Vue 3 global build and ten ordered classic dependency scripts before `js/app.js`. All modules publish through `window.FitnessCoach`; there is no bundler or native module migration.

Current layout behavior:

- `.fc-phone` defaults to `max-width: 430px` and `min-height: 780px`.
- At 480px and below the shell becomes full-screen.
- From 481px through 767px the shell remains constrained to 430px.
- At 768px and above the shell grows only to 720px and keeps a rounded device-like frame.
- `.fc-body` declares `overflow-y: auto`, while `.fc-phone` has only a minimum height. Because no definite shell height constrains it, the effective scroll owner can vary with content.
- `.fc-topbar` and `.fc-sticky-action` are sticky; drawers are viewport-fixed.
- Radar uses the protected `300 × 300` viewBox and a CSS maximum width of 380px.

P2 historical verification recorded in `docs/10_P2_VERIFICATION.md`:

- JavaScript syntax: 11/11 PASS
- Node test files: 12/12 PASS
- Node assertions/contracts: 31/31 PASS
- PowerShell contracts: 4/4 PASS

Current P3-0 reproducible verification:

- Current JavaScript files: 11
- JavaScript syntax: 11/11 PASS
- Current source hashes match the hashes recorded in `docs/10_P2_VERIFICATION.md`.
- The Node and PowerShell test runners used for the documented P2 results are not present in the current `frontend_v3` folder; therefore, those historical counts were not independently re-executed during P3-0.

## 4. Responsive and scroll strategy

P3 keeps and formalizes one app-internal scroll model across viewport sizes.

- `.fc-root` remains the viewport-level presentation surface.
- `.fc-phone` receives a definite viewport-bounded height and becomes a responsive application shell.
- `.fc-body` remains the only normal page-content scroll owner.
- The topbar stays outside the scrolling body and remains visible.
- Sticky CTAs stay within `.fc-body` and are tested against final-content overlap and safe-area padding.
- Drawers remain viewport-fixed and scroll independently.

This strategy minimizes behavioral change and avoids mixing document and nested scrolling by breakpoint.

## 5. Breakpoints and shell behavior

Final breakpoint values may be adjusted only where real content demonstrates a break, starting from:

- Base / mobile, 320–767px: full-width, full-height application shell without a device frame.
- Tablet, 768–1023px: viewport-guttered shell with a wider bounded content area.
- Desktop, 1024px and above: full-viewport application shell with a centered `.fc-body` content area limited to 1180px or the narrower page-specific reading width.
- Wide, 1280px and above: no additional columns unless the page content benefits.
- Existing 380px narrow overrides remain targeted; reduced-motion support remains unchanged.

## 6. Page layout policy

Existing `.fc-body` elements receive presentation-only page classes where needed. No state, computed value, method, binding, event meaning, condition, loop, or navigation route changes.

Actively multi-column on tablet or desktop:

- Route selection: HOME and CENTER cards side by side after the shared introduction.
- CENTER input: measurement fields use a responsive two-column grid.
- Report: summary and actions retain order; Radar, raw metrics, comparison, and supporting sections use bounded grid regions.
- Recommendation: routine content uses additional horizontal space while preserving exercise order.
- Video list: responsive card grid with stable media ratios.

Limited multi-column use:

- Basic information: fields may use two columns while the form remains a single conceptual card.
- Measurement dashboard: list and optional-grip panel may share space only where reading order remains clear.

Reading-width constrained:

- PAR-Q
- Active measurement
- Safety guidance
- Long explanatory content

Mobile DOM order remains the visual and keyboard order.

## 7. Radar presentation

P3 may change only the Radar container width, maximum width, spacing, responsive legend arrangement, and label readability styling.

The following remain byte-for-byte or behaviorally unchanged:

- SVG `viewBox="0 0 300 300"`
- center, radius, axes, and axis order
- normalization and coordinate functions
- polygon, partial segment, and dot conditions
- raw-value and peer-average mappings
- missing/null handling
- Backend-only percentile and peer-average authority

## 8. Drawer and media behavior

Drawers remain fixed dialogs with independent vertical scrolling. On mobile they use the full viewport width; tablet and desktop widths are bounded. Close controls remain visible, YouTube embeds retain their existing privacy-enhanced lifecycle, and iframe aspect ratios remain responsive.

## 9. Files and invariants

Primary modification:

- `css/style.css`

Secondary modification when required:

- `js/app.js`, limited to presentation classes or layout wrappers
- `docs/index.html`, only if presentation markup cannot otherwise be expressed

Protected modules must retain their baseline SHA-256 hashes:

- `js/config/*`
- `js/data/*`
- `js/utils/*`
- `js/services/*`

If `app.js` changes, an exact diff must show template-only changes. `data()`, computed properties, methods, handlers, API use, Radar calculations, and video lifecycle must remain unchanged.

## 10. Verification strategy

Each P3 slice is verified before continuing:

1. Responsive foundation
2. Entry flow
3. Safety and measurement
4. Report and Radar
5. Recommendation and media
6. Narrow and large-screen polish
7. Final regression

Automated checks include:

- syntax checks for all 11 current JavaScript files
- execution of any test assets actually present at implementation time
- protected-module hash comparison
- exact `app.js`/`index.html` diff review
- browser and viewport regression verification

The historical Node and PowerShell counts documented in `docs/10_P2_VERIFICATION.md` must not be reported as newly executed results unless the corresponding runners are available and actually run.

Viewport checks cover 320×568, 360×800, 390×844, 430×932, 480×900, 768×1024, 820×1180, 1024×768, 1280×800, 1440×900, and 1920×1080. Representative screenshot checkpoints are 390×844, 820×1180, and 1440×900. The audit checks horizontal overflow, clipping, sticky overlap, keyboard focus, 200% zoom, Radar labels and legend, drawer controls, iframe ratios, mobile order, and excessive desktop dashboard treatment.

## 11. Out-of-scope changes

P3 does not change product policy, measurement batteries, validation, state, navigation, API contracts, response parsing, Radar data or geometry, percentile authority, recommendation selection, media lifecycle, protected modules, Vue runtime, or P2 file structure.
