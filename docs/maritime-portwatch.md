# Shipping aggregates (IMF PortWatch)

MCHO shows **aggregate** shipping traffic for key chokepoints and MENA ports,
from the IMF's [PortWatch](https://portwatch.imf.org). It never shows or stores
individual vessels or positions.

## Source and licence
- Public ArcGIS feature services published by the IMF: `Daily_Chokepoints_Data`,
  `Daily_Ports_Data`, `PortWatch_chokepoints_database`, `PortWatch_ports`.
- The item licence points to the [IMF terms](https://www.imf.org/external/terms.htm).
  Its "Use of IMF Data" special terms allow users to *download, extract, copy,
  create derivative works, publish, distribute, and use* the data, on three
  conditions: attribution ("Source: International Monetary Fund, PortWatch,
  <link>"), no alteration that affects the data's nature or accuracy, and an
  explicit statement of any material transformation. MCHO shows this
  attribution and states that its 7-day averages, year-on-year changes and
  series are computed by MCHO.
- PortWatch derives its counts from AIS signals (third-party data processed by
  the IMF). Only the IMF's published daily aggregates are used.

## What is stored
- Chokepoints: Suez Canal, Bosporus, Bab el-Mandeb, Strait of Hormuz, Cape of
  Good Hope (ships rerouted from the Red Sea pass here) and Gibraltar. Daily
  transits in total and by type (tanker, container, dry bulk, cargo), plus
  deadweight capacity.
- Ports in the 22 MENA countries: daily port calls (total and by type), plus
  estimated import and export tonnes.
- Rows go into the existing `maritime_aggregates` table (one row per area, day
  and metric, unique) with `quality_flags = ["ais_derived"]`. Areas and their
  coordinates go into `maritime_areas`.

## Refresh
About 400 days are backfilled on first run, so last year can be compared.
After that, the last 7 days are re-pulled for revisions. It runs at most every
6 hours, triggered in the background by `GET /api/v1/maritime/overview` (which
the hourly GitHub workflow requests). Failures are recorded in
`maritime_refreshes` and never affect the satellite feed.

## Analysis (`GET /api/v1/maritime/overview?country=ISO3`)
- **7-day average** per day for the latest 7 published days. It needs at least
  5 of the 7 days; otherwise it is empty.
- **Same days last year** (same calendar days, same rule), with % change.
- **90-day daily series** for sparklines; missing days stay empty, never zero.
- Ports follow the country filter; without one, the 25 busiest MENA ports are
  shown.

## Limits
AIS can be switched off, spoofed or missed, especially near conflict zones, so
counts can understate traffic. PortWatch publishes with a delay of a few days.
Transit counts are not cargo values. These are aggregate indicators for
context, not evidence of specific events.
