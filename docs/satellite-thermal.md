# Satellite heat detections (NASA FIRMS)

MCHO's live layer shows heat that satellites detected across the MENA region,
and summarises where activity is unusual. This page explains where the data comes
from, how it is analysed, and what it can and cannot tell you.

## What the data is

- **Source:** NASA [FIRMS](https://firms.modaps.eosdis.nasa.gov/) near-real-time
  active fire / thermal anomaly product from the VIIRS instrument on three
  satellites: Suomi NPP, NOAA-20 and NOAA-21 (`VIIRS_*_NRT`).
- **What a detection is:** a ~375 m pixel that was significantly hotter than its
  surroundings during a satellite pass, with its time, fire radiative power (MW,
  a measure of intensity) and a confidence level.
- **Timeliness:** usually available within about 3 hours of the pass. Each
  location is seen a few times a day; clouds and thick smoke hide fires.
- **Licence:** NASA open data. Credit: *NASA Fire Information for Resource
  Management System (FIRMS)*.

**A detection is a heat signature, not a verified event.** Causes include fires
from conflict, crop and stubble burning, wildfires, gas flares and industry. No
detection does not mean nothing happened. These observations are leads for human
review; MCHO never turns them into published events automatically. **Not for
targeting or tactical use.**

## Pipeline

1. **Fetch.** The API requests the FIRMS area API for `FIRMS_AREA`
   (default `-18,8,64,40`). The first run backfills ~10 days for the baseline;
   later runs request the last 2 days.
2. **Store.** Rows are validated (coordinates, time, confidence; malformed rows
   are dropped and counted). Only detections inside the 22 MENA country borders
   (Natural Earth 1:50m, public domain) are kept, each tagged with its country.
   Offshore detections (e.g. platform flares) are excluded. A detection is unique
   per product, time and location, so re-fetching never duplicates it. Data older
   than `FIRMS_RETENTION_DAYS` (21) is deleted.
3. **Schedule.** The free hosting tier has no background worker. When data is
   older than `FIRMS_REFRESH_MINUTES` (45), the next request to a thermal endpoint
   starts a refresh in the background. An advisory lock and the refresh log allow
   only one at a time, and a failure is retried no sooner than 10 minutes later.
   The **Refresh satellite data** GitHub workflow requests the API hourly so data
   stays fresh without visitors.
4. **Analyse** (in PostGIS SQL, `services/api/app/thermal/analysis.py`):

| Term | Rule |
|---|---|
| Window | Detections in the last 24 hours |
| Baseline | The 7 days before the window |
| Cell | ~2 km grid square (0.02°) |
| **Persistent site** | A cell with detections on ≥ 4 distinct baseline days: usually gas flares or industry. Shown in grey, excluded from activity counts |
| **New activity** | A detection in a cell with no baseline detections |
| **Recurring** | Neither new nor persistent |
| **Above normal** (country) | ≥ 10 non-persistent detections in the window **and** ≥ 2× the baseline's non-persistent daily average (or no baseline activity) |
| **New-activity cluster** | ≥ 2 new detections in the same ~10 km square (0.1°) |

The rules are deliberately simple so every number can be traced back to
individual detections. Until 7 days of history exist, the panel says the
baseline is still building.

## API

Both endpoints are public and read-only, and every response includes
`freshness`, `caveats` and attribution.

- `GET /api/v1/thermal/detections?west=&south=&east=&north=&hours=24` returns GeoJSON points with
  `classification`, `frp_mw`, `confidence`, `satellite`, `acquired_at` and
  `country`, at most 5,000 per request (`truncated` says if more exist).
- `GET /api/v1/thermal/insights?hours=24` returns totals, per-country activity against the
  baseline, new-activity clusters, method parameters and caveats.

## Setup

1. Request a free MAP_KEY at <https://firms.modaps.eosdis.nasa.gov/api/map_key>.
2. In **Render → mcho-api → Environment**, add `NASA_FIRMS_API_KEY` with that
   value, then save and deploy. It is a credential: never commit it.
3. Open the site. The first download takes about a minute, and the insights panel
   updates by itself.

## Known limitations

- Grid cells don't account for detections just across a cell edge, so a
  persistent site on a boundary can occasionally show as recurring.
- The fire radiative power of overlapping passes is not de-duplicated across
  satellites; counts are detections, not distinct fires.
- Borders are 1:50m generalised; detections within ~1 km of a border may be
  attributed to the neighbouring country.
- Cloud cover and smoke reduce detections; a fall in counts can be weather.
