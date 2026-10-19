# Phase 13 — Interactive prototype

## Purpose

The /demo route is a reviewable user-interface prototype that runs inside the Next.js web application. Its records, labels, dates, references, and marker positions are synthetic fixtures. It must never be represented as a live conflict observatory.

## What's included

- Overview dashboard with clearly synthetic metrics.
- Search and status filters for the example record queue.
- Clickable illustrative SVG markers linked to selected example records.
- Selected-record panel with metadata provenance and copy-to-clipboard action.
- Preview-only review action that does not write to the API.
- Satellite, humanitarian-indicator, aggregate maritime, and methodology modules.
- Responsive styles and a route link from the application homepage.

## Local run

From the repository root, configure the environment as required by README.md, then start the web service using the existing Docker Compose setup. The route is available at:

- Homepage: http://localhost:3000
- Interactive prototype: http://localhost:3000/demo

The demo route has no API calls and does not require a database, identity provider, map style, or external data feed for its synthetic interface. Running the full Compose stack still uses the repository's normal environment requirements.

## Acceptance checks

1. The demo route renders without a map-provider URL or backend service.
2. Tab controls switch between all six modules.
3. Search and status filters update the record list.
4. Selecting a record from the list or marker updates the details panel.
5. The copy action states clearly that the provenance is synthetic.
6. Review actions remain preview-only; no API mutation is issued.
7. Small screens keep navigation and panels usable.
8. All demo screens keep the non-live-data warning visible.

## Not in scope

This phase does not enable source connectors, create hosted infrastructure, configure production OIDC, publish actual event data, or replace the main application homepage with synthetic content.
