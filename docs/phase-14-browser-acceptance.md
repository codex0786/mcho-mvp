# Phase 14 — Browser acceptance tests

## Objective

Exercise the interactive prototype in a real browser against the built Next.js production server. The tests are intended to verify the most important user-visible paths, not to prove that live sources or production hosting are configured.

## Coverage

- Prominent synthetic-data notice and expected illustrative marker count.
- Navigation across Overview, Event explorer, Satellite observations, Humanitarian indicators, Maritime aggregates, and Methodology & provenance.
- Status filtering, search and empty states.
- Record selection from the list and map marker, with matching provenance details.
- Keyboard activation of a marker.
- Preview-only review feedback and explicit synthetic provenance when copying.
- Basic mobile-width navigation and search.

## Run locally

From `apps/web`, install the repository dependencies and Playwright's Chromium browser, then create a production build and run the test command:

```bash
npm install
npx playwright install chromium
NEXT_PUBLIC_API_BASE_URL=https://api.example.invalid/api/v1 NEXT_PUBLIC_MAP_STYLE_URL= npm run build
npm run test:e2e
```

The Playwright config starts `next start` on `127.0.0.1:3000` and reuses a matching local server outside CI. The demo route uses synthetic fixtures and makes no backend requests; the build environment values above are placeholders, not configured source integrations.

## Continuous integration

The web-build job installs Playwright Chromium with its OS dependencies after the production build and runs `npm run test:e2e`. Test results, the HTML report and failure diagnostics are uploaded as a CI artifact. Browser checks use one worker in CI and retry failed tests once for stability; persistent failures still fail the job.

## Acceptance criteria

1. The demo route renders in the production Next.js build without credentials or a map provider.
2. All six module tabs render the intended content.
3. Search and filter state update results accurately, including the no-results case.
4. Selecting a map marker and selecting a list row update the selected record and its provenance.
5. Keyboard marker selection works.
6. Review remains explicitly preview-only; the demo does not mutate API records.
7. Copied provenance includes a synthetic-data warning.
8. Basic navigation and filtering work at mobile width.

## Limitations

These tests do not replace API integration tests, an end-to-end analyst authentication test against a real OIDC provider, source-provider validation, independent security review, or a deployed staging smoke test.
