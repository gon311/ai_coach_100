# Stage P1 Verification

- Date: 2026-09-09
- Scope: P1 Mobile UX & Report Redesign
- Runtime: Vue CDN, single `js/app.js`
- Policy baseline: `frontend_v3_p0_baseline`

## Final report policy

- The report does not display a fitness grade or a frontend-generated score.
- Radar blue series means **나의 측정값**. Axis labels show the measured raw value and unit.
- Radar light-orange series means **또래 평균** and is rendered only when Backend comparison data is available.
- Radar normalized values are SVG coordinates only and are never exposed as scores.
- Percentile output is separate from Radar. It uses Backend results only.
- Percentile ranges are displayed only where the existing Backend/P0 range contract supplies a range width. The frontend does not invent a range.
- Missing measurement and unavailable comparison data are shown as `미측정` and `또래 비교 준비 중`; neither is converted to zero.

## Automated regression

Fresh verification result:

- JavaScript syntax: PASS
- Node test files: 10/10 PASS
- Node assertions: 24/24 PASS
- PowerShell contracts: 4/4 PASS
- Failures: 0

Covered flows:

- Adult HOME battery: sit-and-reach, cross sit-up, standing long jump, 10m four-round shuttle
- Senior HOME battery and senior measurement-video mapping
- CENTER battery
- Under-19 blocked flow
- PAR-Q pass/fail
- Optional grip
- Negative flexibility input
- Radar partial/full rendering and missing data
- Backend-only percentile behavior
- Recommendation Mock data contract
- YouTube no-cookie embedded playback and safe unavailable state

## Browser regression

Verified in the local webview:

- Landing and HOME/CENTER route selection
- Basic information and focused PAR-Q navigation
- Adult HOME 4-item dashboard and single-item measurement screen
- `-5cm` flexibility input accepted
- Four required values completed and optional grip explicitly marked not measured
- Direct transition to the fitness report (no intermediate result-confirmation page)
- Report displays raw values, missing items, Backend comparison pending state, and no grade
- Recommendation page displays total time and ordered exercise steps
- Video API failure displays a friendly retry message instead of a raw parser error

## Responsive visual check

The Landing screen was rendered side-by-side at exact iframe widths of 360, 390, 430, and 480px. All four widths kept readable typography, intact cards, full-width CTA, and no horizontal clipping. The shared mobile CSS contract also verifies 48px touch targets, the 480px breakpoint, the narrow-width rule, focus-visible styles, and reduced-motion support.

## Stage boundary

P1 preserves the Vue CDN runtime, single `app.js`, P0 batteries, Radar policy, percentile contract, Backend API contract, and Mock recommendation selection. JavaScript file splitting remains deferred to P2.

## Final P1 refinement

- The `체력코치 AI` header brand is a semantic button that returns to Landing.
- A complete user Radar series uses a high-opacity light-blue fill with a blue outline.
- A complete Backend peer-average series uses a high-opacity light-orange fill with an orange outline.
- Partial series remain dots and adjacent segments; missing axes are not closed through zero.
