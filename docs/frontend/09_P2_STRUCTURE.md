# Stage P2 JavaScript Structure

- Date: 2026-09-11
- Status: Implemented
- Runtime: Vue 3 global build, classic scripts, no bundler
- Namespace: `window.FitnessCoach`

## Purpose

P2 reorganizes the existing implementation without changing its visible behavior or policy. The existing `app.js` was edited in place: constants and pure functions were moved to focused files, then reconnected through one namespace.

## Load order

`docs/index.html` loads JavaScript in this order:

1. Vue CDN
2. `config/measurement-config.js`
3. `config/radar-config.js`
4. `config/video-config.js`
5. `data/mock-data.js`
6. `utils/measurement-utils.js`
7. `utils/radar-utils.js`
8. `utils/youtube-utils.js`
9. `services/percentile-service.js`
10. `services/report-service.js`
11. `services/video-service.js`
12. `app.js`

Native ES modules and a bundler were not introduced, preserving the existing direct-file script format and local HTTP operation.

## Ownership

### Configuration

- `measurement-config.js`: measurement definitions, HOME/CENTER batteries, validation ranges
- `radar-config.js`: Adult/Senior axes, raw display ranges, Backend percentile range metadata
- `video-config.js`: measurement guide IDs and video category mapping

### Data

- `mock-data.js`: `MOCK_WORKOUT_RECOMMENDATIONS`

### Pure utilities

- `measurement-utils.js`: validation, battery resolution, Backend measurement payload construction
- `radar-utils.js`: raw-range normalization, partial runs, polygon/segment/dot coordinates
- `youtube-utils.js`: supported YouTube URL/ID extraction

### Services

- `percentile-service.js`: `/api/center-percentiles`
- `report-service.js`: `/api/report-summary`
- `video-service.js`: `/api/top-videos/{category}`

Services only transport and parse Backend data. They do not calculate grades, percentile, peer averages, Radar meaning, or workout prescriptions.

### Vue application

`app.js` retains Vue state, computed presentation models, navigation, user actions, player lifecycle, and the complete existing template.

## Preserved invariants

- Adult and Senior HOME/CENTER batteries are unchanged.
- Negative flexibility remains valid from -30cm.
- Radar normalized values remain internal SVG positions, not fitness scores.
- Missing values remain `null`/`미측정`, never zero.
- Backend remains the only percentile and peer-average authority.
- Senior 3m target return remains a reference value without frontend percentile.
- Relative grip construction and optional-grip behavior are unchanged.
- YouTube remains embedded through the privacy-enhanced player.
- Workout recommendations remain explicitly Mock data.
