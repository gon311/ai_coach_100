# P1 Radar Refinement and P2 JavaScript Structure Design

**Date:** 2026-09-09  
**Status:** Approved in chat; awaiting document review  
**Project:** `frontend_v3`

## Purpose

Apply three final P1 interaction and Radar refinements, verify the complete P0/P1 behavior, freeze that result as `frontend_v3_p1_baseline`, and then split the JavaScript by responsibility without changing behavior.

## Existing-file modification rule

- All work modifies the current files in `C:\Users\user\Desktop\frontend_v3` in place.
- The application is not regenerated, scaffolded again, or implemented from the beginning.
- Existing Vue templates, CSS, data contracts, navigation, and tested behavior remain the source of truth.
- P1 refinements use minimal edits to the existing header and Radar implementation.
- P2 moves existing constants and functions from `app.js` into focused files, then reconnects them through `window.FitnessCoach`; it does not rewrite those features with new implementations.
- Newly created files are limited to the P2 modules, tests, baseline manifest, and required design/verification documentation.

## Confirmed P1 refinements

### Header home navigation

- The full `체력코치 AI` brand area is a semantic button.
- Activating it returns to the existing Landing screen through the app's navigation method.
- It has a minimum 48px×48px touch area, keyboard focus-visible styling, and an accessible label.
- It does not reset policy program data beyond the state changes already performed by the existing Landing navigation.

### Radar series

- `나의 측정값`: light blue fill with a blue outline.
- `또래 평균`: light orange fill with an orange outline.
- Both closed polygons use a clearly visible, relatively high-opacity light fill so their overlap remains readable.
- Average data is displayed only when supplied by Backend comparison results. Frontend does not synthesize peer averages.
- With all axes measured, the user series is a closed filled polygon.
- With all peer-average axes available, the average series is a closed filled polygon.
- Partial user or average data remains dots and adjacent line segments. Missing axes are not converted to zero and no artificial polygon is closed.
- The legend, axis raw values, and average labels use the same blue/orange semantic mapping.

### Data meaning

- Radar coordinates remain normalized display positions only.
- User-facing labels show raw measurement plus unit.
- Backend percentile and peer-average data remain separate from Radar normalization.
- No fitness grade or frontend-generated percentile is introduced.

## P1 verification and baseline

Before P2 begins:

1. Run JavaScript syntax validation.
2. Run all existing P0 and P1 Node tests and PowerShell contracts.
3. Browser-check header navigation and Radar behavior.
4. Render the mobile layout at 360, 390, 430, and 480px.
5. Copy the verified project to `C:\Users\user\Desktop\frontend_v3_p1_baseline`.
6. Record SHA-256 checksums for the baseline's implementation and documentation files.

## P2 objective

Transform the verified single `app.js` into focused configuration, data, service, utility, and Vue application files while preserving the exact P1 UI and P0 behavior.

## Runtime decision

The current project is opened directly through `file://` as well as through a local HTTP server. Native ES modules can be restricted when loaded from `file://`, so P2 will use dependency-ordered classic scripts and one explicit namespace:

```js
window.FitnessCoach = window.FitnessCoach || {};
```

Each extracted file assigns only its public constants or functions to this namespace. `app.js` consumes those members and remains responsible for Vue state, computed properties, event handlers, and the template.

### Rejected alternatives

- **Native ES modules:** clean imports, but direct `file://` execution can fail because of browser origin restrictions.
- **Bundler migration:** provides module tooling, but adds a build system and changes the current no-build delivery contract.
- **Unscoped global variables:** works with classic scripts but increases collision risk and makes dependencies unclear.

## Target file structure

```text
js/
├── config/
│   ├── measurement-config.js
│   ├── radar-config.js
│   └── video-config.js
├── data/
│   └── mock-data.js
├── services/
│   ├── percentile-service.js
│   ├── report-service.js
│   └── video-service.js
├── utils/
│   ├── measurement-utils.js
│   ├── radar-utils.js
│   └── youtube-utils.js
└── app.js
```

## File responsibilities and interfaces

### `config/measurement-config.js`

Owns measurement item definitions, validation ranges, HOME/CENTER batteries, and PAR-Q question configuration. Exposes immutable configuration through `FitnessCoach.measurementConfig`.

### `config/radar-config.js`

Owns Adult/Senior Radar axes, raw display ranges, direction flags, and Backend percentile range-width metadata. Exposes `FitnessCoach.radarConfig`.

### `config/video-config.js`

Owns measurement-video guides and Radar-label-to-video-category mappings. Exposes `FitnessCoach.videoConfig`.

### `data/mock-data.js`

Owns `MOCK_WORKOUT_RECOMMENDATIONS` and other explicitly Mock-only presentation data. Exposes `FitnessCoach.mockData`.

### `utils/measurement-utils.js`

Provides pure measurement validation, age grouping, battery resolution, and percentile-measurement payload helpers. It does not access Vue state or the DOM.

### `utils/radar-utils.js`

Provides raw-value normalization, partial-run calculation, polygon points, indexed segment points, and dot coordinates. Returned normalized values remain visualization coordinates only.

### `utils/youtube-utils.js`

Provides YouTube ID extraction and embed URL helpers without navigating to YouTube pages.

### `services/*.js`

Wrap existing fetch calls without altering endpoint paths, request payloads, response interpretation, or Backend authority. Services convert network/parser failures into stable application errors but do not calculate percentile, fitness score, peer average, or prescriptions.

### `app.js`

Owns Vue application state, computed UI models, screen navigation, user-event orchestration, the YouTube player component lifecycle, and the existing Vue template. It imports nothing; it reads the dependency namespace populated by earlier classic scripts.

## Script loading order

`docs/index.html` loads files in this order:

1. Vue CDN
2. measurement, Radar, and video configuration
3. Mock data
4. measurement, Radar, and YouTube utilities
5. percentile, report, and video services
6. `app.js`

Every extracted script is safe to evaluate exactly once. Missing dependencies fail with a clear startup error during development rather than silently changing behavior.

## Error handling

- Existing Backend-unavailable report and percentile states remain unchanged.
- Video API failure continues to show the friendly retry copy.
- Invalid or non-JSON service responses are treated as unavailable data.
- Missing Backend peer-average values keep the orange series hidden.
- Direct `file://` use is supported; expected unavailable Backend calls must not break local rendering.

## Testing strategy

Every extraction follows red-green-refactor:

1. Add or update a test that expects the new namespace interface or script order.
2. Run it and observe the expected failure.
3. Extract the minimum code.
4. Run the focused test.
5. Run the full P0/P1 regression suite.

Final validation covers Adult HOME, Senior HOME, CENTER, Under-19, PAR-Q pass/fail, optional grip, negative flexibility, Radar partial/full, Backend percentile available/unavailable, peer average available/unavailable, YouTube playback/error, Mock prescription, brand-to-Landing navigation, `file://`, local HTTP, and 360/390/430/480px mobile widths.

## Non-goals

- No regeneration or ground-up rewrite of the existing frontend.
- No Vue-to-React migration.
- No bundler or package-manager requirement.
- No UI redesign beyond the confirmed header and Radar refinements.
- No measurement battery, Radar range, percentile, Backend contract, or recommendation algorithm change.
- No new frontend-derived average, fitness score, grade, or percentile.
