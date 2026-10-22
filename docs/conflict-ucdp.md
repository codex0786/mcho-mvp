# Verified conflict events and deaths (UCDP)

## Source and licence

- **Publisher:** Uppsala Conflict Data Program (UCDP), Uppsala University.
- **Dataset:** UCDP Candidate Events Dataset. These are preliminary monthly releases of the georeferenced event data
  that becomes UCDP GED each year.
- **Access:** public CSV downloads, with no token: `https://ucdp.uu.se/downloads/candidateged/GEDEvent_vYY_0_M.csv`.
  - Release `YY.0.M` covers month M and is published around the 20th of the following month.
  - The UCDP REST API needs a token (free on request), but it is **not needed**: the same releases are public
    downloads.
- **Licence:** CC BY 4.0 ("All datasets are free of charge and licensed under CC BY 4.0", UCDP download centre).
- **Required citation:** Hegre, Håvard, Mihai Croicu, Kristine Eck and Stina Högbladh (2020), "Introducing the UCDP
  Candidate Events Dataset", *Research & Politics*, doi:10.1177/2053168020935257. Also cite the codebook, v1.5
  (Högbladh 2026), where appropriate.

## What is stored

- **Releases fetched:** the current and previous 6 months, checked every 12 hours with conditional requests (ETag and
  Last-Modified).
- **Fetch log:** each downloaded release is recorded in `ucdp_releases`. A month without a release is reported as
  **missing**, never as zero.
- **Event fields:** stored unchanged from UCDP (`ucdp_events`, keyed by UCDP's stable `id`):
  - type of violence, conflict, dyad and sides;
  - place and admin-1 area, with UCDP's precision codes (`where_prec`, `date_prec`, `event_clarity`, `code_status`);
  - deaths as best, low and high estimates, plus civilian deaths.
- **Country assignment:**
  1. Containment in one of the 22 MENA borders.
  2. Otherwise, only when UCDP itself names a MENA country (for example events just off the coast), the nearest
     MENA border within about 50 km.
  3. Events in neighbouring countries close to a border (Chad, Ethiopia and so on) are not pulled in.
- **Retention:** 400 days.

## Heat cross-check ("cause matching")

1. **Eligible events:** `where_prec` 1 or 2 (exact, or within about 25 km) and `date_prec` 1 or 2 (within 6 days),
   spanning at most 7 days. Other events are `not_checkable`.
2. **Window and radius:** day before `date_start` to day after `date_end`. Radius is 5 km for an exact place and
   25 km otherwise.
3. **Data source:** NASA FIRMS area API, VIIRS NOAA-20 and Suomi NPP. The archive (SP) product is used where available,
   otherwise NRT, chosen with the FIRMS data-availability API.
4. **Batching:** events within 1° and the same 7-day bin share requests. Each run has a budget of 200 FIRMS requests
   (FIRMS allows 5,000 per 10 minutes per key). While events are pending, a run is due every 10 minutes.
   - Each run records the requests made and the detections FIRMS returned in the search boxes
     (`freshness.last_attempt.heat_requests` / `heat_detections_fetched` in the API).
   - This separates "FIRMS returned nothing" from "heat was nearby but did not match".
5. **Persistent sites:** about 2 km cells with heat on at least 4 of the 7 days before the window (flares, industry)
   are counted separately and do not make a match. This is the same rule as the main heat map.
6. **Result per event:** `heat`, `no_heat`, `persistent_only`, `pending` or `not_checkable`. It includes the detection
   count, the nearest distance and the maximum fire radiative power.

**Interpretation:** a match means heat was seen near a verified, deadly event at about the same time. It does not show
that the event caused the fire. No heat does not mean nothing burned: clouds, smoke, overpass timing and small fires all
leave gaps.

### Today's heat fronts and recent violence

UCDP runs about 3–7 weeks behind the satellites, so current heat cannot be matched to verified events yet. The overview
instead lists **active moving fronts** (last 7 days) that lie within 25 km of UCDP events in the previous 180 days. This
is context, not cause.

## API

`GET /api/v1/conflict/overview?country=ISO3` returns:

- the period (the latest 3 months, with any missing months);
- totals, by country and by month;
- heat cross-check counts;
- the deadliest events and the events with heat;
- fronts near recent violence;
- the events as GeoJSON for the map;
- attribution, citation, caveats and freshness.

The endpoint also triggers the background sync when due. The hourly GitHub workflow pings it.

## Not included

- **The stable UCDP GED** (annual, up to the previous year). Recent months are what matter for comparison with
  satellite data.
- **Air traffic.** OpenSky's terms require a written licence for any automated or operational use of its REST API,
  even non-profit. It stays out until such a licence is granted; see the roadmap.
