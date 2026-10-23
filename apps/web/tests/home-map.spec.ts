import { expect, test, type Page, type Route } from "@playwright/test";

const STYLE_URL = "https://style.mcho.test/style.json";

// Tile requests are held open to simulate a slow basemap; release them after each
// test so page and worker teardown never wait on them.
let heldTileRequests: Route[] = [];
test.afterEach(async () => {
  const held = heldTileRequests;
  heldTileRequests = [];
  await Promise.all(held.map((route) => route.abort().catch(() => undefined)));
});

const NOW = new Date().toISOString();
const FRESHNESS = {
  configured: true, refresh_scheduled: false, refresh_running: false,
  last_successful_refresh_at: NOW, last_attempt: { status: "succeeded", started_at: NOW, error_summary: null },
};
const THERMAL_DETECTIONS = {
  type: "FeatureCollection", truncated: false, feature_limit: 5000, freshness: FRESHNESS,
  features: [
    { type: "Feature", id: "a", geometry: { type: "Point", coordinates: [32.53, 15.55] }, properties: {
      acquired_at: "2026-10-21T01:42:00+00:00", frp_mw: 24.5, confidence: "n", satellite: "N20", product: "VIIRS_NOAA20_NRT",
      daynight: "N", country_code: "SDN", country: "Sudan", classification: "new", baseline_days: 0 } },
    { type: "Feature", id: "b", geometry: { type: "Point", coordinates: [47.5, 30.5] }, properties: {
      acquired_at: "2026-10-21T00:10:00+00:00", frp_mw: 8.1, confidence: "h", satellite: "N", product: "VIIRS_SNPP_NRT",
      daynight: "N", country_code: "IRQ", country: "Iraq", classification: "persistent", baseline_days: 6 } },
  ],
};
const THERMAL_INSIGHTS = {
  window_hours: 24, latest_detection_at: NOW, baseline_days_available: 7,
  totals: { active_detections: 14, new_detections: 12, persistent_detections: 30, elevated_countries: 1 },
  countries: [
    { iso_a3: "SDN", name: "Sudan", active_detections: 12, new_detections: 12, persistent_detections: 0, baseline_daily_average: 2.1, ratio_to_baseline: 5.7, max_frp_mw: 31, elevated: true, year_on_year_7d: { days: 7, this_year: 350, last_year: 420, ratio: 0.83 } },
    { iso_a3: "IRQ", name: "Iraq", active_detections: 2, new_detections: 0, persistent_detections: 30, baseline_daily_average: 2.4, ratio_to_baseline: 0.8, max_frp_mw: 12, elevated: false },
  ],
  new_activity_clusters: [{ country: "Sudan", detections: 12, longitude: 32.55, latitude: 15.57, max_frp_mw: 31, first_seen: NOW, last_seen: NOW, satellites: 2 }],
  method: { cell_degrees: 0.02, cluster_degrees: 0.1, baseline_days: 7, persistent_min_days: 4, elevated_rule: "at least 10 non-persistent detections and at least 2x the baseline daily average" },
  caveats: "Satellite heat detections (NASA FIRMS). Each is a heat signature, not a verified event.",
  source: { name: "NASA FIRMS", url: "https://firms.modaps.eosdis.nasa.gov/", attribution: "NASA FIRMS" },
  freshness: FRESHNESS,
};

const COUNTRIES = {
  items: [
    { iso_a3: "IRQ", iso_a2: "IQ", name: "Iraq", bbox: [38.8, 29.1, 48.6, 37.4] },
    { iso_a3: "SDN", iso_a2: "SD", name: "Sudan", bbox: [21.8, 8.7, 38.6, 22.2] },
  ],
};

function trendFor(iso3: string, name: string) {
  const today = new Date();
  const series = Array.from({ length: 22 }, (_, i) => {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - (21 - i)));
    const covered = i >= 8;
    return {
      date: d.toISOString().slice(0, 10), covered, partial: i === 21,
      total: covered ? 40 + i : null, persistent: covered ? 10 : null, other: covered ? 30 + i : null, max_frp_mw: covered ? 12 : null,
      comparable_total: covered ? 40 + i : null, last_year_total: covered ? 60 : null,
    };
  });
  return {
    iso_a3: iso3, name, days: 21, series, generated_at: NOW,
    year_on_year_7d: { days: 7, this_year: 350, last_year: 420, ratio: 0.83 },
    comparison_note: "Last year's totals come from NASA's FIRMS archive for the same calendar days.",
    persistent_rule: "Sites with heat on at least 4 of the 7 days before the last 24 hours, applied to every day.",
    coverage_note: "Days before data collection began show no counts: missing data is not zero. Today is incomplete.",
    caveats: "Not a verified event.", freshness: FRESHNESS,
  };
}

const TRACKS = {
  type: "FeatureCollection", total_tracks: 2, days: 7, daily_clusters: 9,
  caveats: "A track shows how heat moved, not why. Not a verified event.",
  method: { cluster_eps_km: 6, cluster_min_detections: 3, link_km: 30, max_gap_days: 2 },
  features: [
    { type: "Feature", geometry: { type: "LineString", coordinates: [[30.0, 12.0], [30.08, 12.0], [30.16, 12.0]] }, properties: {
      country_code: "SDN", country: "Sudan", first_day: "2026-10-18", last_day: "2026-10-20", days_active: 3, detections: 312,
      max_frp_mw: 40, displacement_km: 17.4, direction: "E", bearing_degrees: 90, km_per_day: 8.7, active: true,
      latest: { longitude: 30.16, latitude: 12.0 }, daily: [] } },
    { type: "Feature", geometry: { type: "LineString", coordinates: [[44.0, 33.0], [44.01, 33.0]] }, properties: {
      country_code: "IRQ", country: "Iraq", first_day: "2026-10-15", last_day: "2026-10-16", days_active: 2, detections: 20,
      max_frp_mw: 5, displacement_km: 0.9, direction: null, bearing_degrees: null, km_per_day: 0.9, active: false,
      latest: { longitude: 44.01, latitude: 33.0 }, daily: [] } },
  ],
};

function maritimeFor(country: string | null) {
  const series = Array.from({ length: 90 }, (_, i) => ({ day: `2026-07-${String((i % 28) + 1).padStart(2, "0")}`, value: i === 40 ? null : 20 + (i % 5) }));
  const chokepoint = (id: string, name: string, avg: number, last: number, change: number) => ({
    id, name, country_code: null, longitude: 43.35, latitude: 12.79, avg_7d: avg, avg_7d_last_year: last,
    change_vs_last_year_pct: change, series, tankers_avg_7d: 5, capacity_dwt_avg_7d: 900000,
  });
  const ports = [
    { id: "port9", name: "Aden", country_code: "YEM", longitude: 44.95, latitude: 12.78, avg_7d: 3, avg_7d_last_year: 4,
      change_vs_last_year_pct: -25, series, import_tonnes_7d: 30000, export_tonnes_7d: 5600 },
    { id: "port1", name: "Port Said", country_code: "EGY", longitude: 32.3, latitude: 31.26, avg_7d: 40, avg_7d_last_year: 41,
      change_vs_last_year_pct: -2, series, import_tonnes_7d: 900000, export_tonnes_7d: 700000 },
  ];
  return {
    latest_day: "2026-10-18", country,
    chokepoints: [chokepoint("chokepoint4", "Bab el-Mandeb Strait", 30.4, 72.1, -58), chokepoint("chokepoint1", "Suez Canal", 41, 44, -7)],
    ports: country ? ports.filter((p) => p.country_code === country) : ports,
    attribution: "Source: International Monetary Fund, PortWatch, https://portwatch.imf.org",
    caveats: "Counts come from AIS ship signals.", transformation: "7-day averages are computed by MCHO.",
    freshness: { refresh_scheduled: false, last_successful_refresh_at: NOW, last_attempt: { status: "succeeded", error_summary: null } },
  };
}

const DAMAGE = {
  assessments: [
    { id: "p-strip", title: "UNOSAT Gaza Strip Comprehensive Damage Assessment - 11 October 2025", country_code: "PSE", unosat_code: "CE20231007PSE",
      published_on: "2025-10-31", imagery_date: "2025-10-11", status: "mapped", status_detail: "Layer Damage_Sites", on_map: true, superseded_by: null,
      counts: { destroyed: 123464, severe: 17116, moderate: 33857, possible: 23836, unclassified: 0 }, bbox: [34, 31, 35, 32],
      hdx_url: "https://data.humdata.org/dataset/unosat-gaza", licence: "Creative Commons Attribution Share-Alike (CC BY-SA)", licence_url: null,
      summary: "This map illustrates a satellite imagery based comprehensive assessment of damage.", caveats: "Preliminary." },
    { id: "p-old", title: "UNOSAT Gaza Strip Comprehensive Damage Assessment - 08 July 2025", country_code: "PSE", unosat_code: "CE20231007PSE",
      published_on: "2025-08-05", imagery_date: "2025-07-08", status: "mapped", status_detail: null, on_map: false,
      superseded_by: "UNOSAT Gaza Strip Comprehensive Damage Assessment - 11 October 2025",
      counts: { destroyed: 102067, severe: 17421, moderate: 41895, possible: 31194, unclassified: 0 }, bbox: [34.2, 31.2, 34.6, 31.6],
      hdx_url: "https://data.humdata.org/dataset/unosat-gaza-july", licence: "CC BY-SA", licence_url: null, summary: "Earlier.", caveats: null },
  ],
  cells: { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [34.45, 31.5] },
    properties: { destroyed: 40, severe: 5, moderate: 3, possible: 2, unclassified: 0, total: 50, destroyed_share: 0.8,
      assessment: "UNOSAT Gaza Strip Comprehensive Damage Assessment - 11 October 2025", imagery_date: "2025-10-11" } }] },
  totals_on_map: { destroyed: 123464, severe: 17116, moderate: 33857, possible: 23836, unclassified: 0 }, cell_km: 0.6,
  attribution: "Source: United Nations Satellite Centre (UNOSAT), via the Humanitarian Data Exchange (HDX)",
  caveats: "UNOSAT assessments are preliminary.", transformation: "MCHO counts structures in grid cells.",
  freshness: { refresh_scheduled: false, last_successful_refresh_at: NOW, last_attempt: { status: "succeeded", error_summary: null } },
};

const UCDP_EVENT = {
  id: 101, date_start: "2026-09-10", date_end: "2026-09-10", country_code: "SDN", country: "Sudan", place: "El Fasher town", adm_1: "North Darfur",
  type: "State-based conflict", type_code: 1, dyad: "Government of Sudan - RSF", conflict: "Sudan: Government", side_a: "Government of Sudan",
  side_b: "RSF", deaths_best: 30, deaths_low: 25, deaths_high: 40, deaths_civilians: 12, code_status: "Clear", where_prec: 1, date_prec: 1,
  longitude: 25.35, latitude: 13.6, heat: { status: "heat", detections: 3, nearest_km: 2.4, radius_km: 5, max_frp_mw: 25, persistent_excluded: 0 },
};
const CONFLICT = {
  releases: [{ release: "26.0.9", month: "2026-09", fetched_at: NOW, events_mena: 430 }, { release: "26.0.8", month: "2026-08", fetched_at: NOW, events_mena: 300 }],
  period: { start: "2026-07-01", end: "2026-09-30", months: ["2026-07", "2026-08", "2026-09"], missing_months: ["2026-07"] },
  totals: { events: 730, deaths_best: 4330, deaths_low: 3900, deaths_high: 5100, deaths_civilians: 800 },
  by_country: [{ country_code: "YEM", country: "Yemen", events: 358, deaths_best: 2100, deaths_low: 1900, deaths_high: 2500, deaths_civilians: 300,
    by_type: { "State-based conflict": 2000, "Non-state conflict": 0, "One-sided violence against civilians": 100 } }],
  by_month: [{ month: "2026-07", fetched: false, events: null, deaths_best: null }, { month: "2026-08", fetched: true, events: 300, deaths_best: 1800 },
    { month: "2026-09", fetched: true, events: 430, deaths_best: 2530 }],
  top_events: [UCDP_EVENT], events_with_heat: [UCDP_EVENT],
  fronts_near_violence: [{ country: "Sudan", first_day: "2026-10-16", last_day: "2026-10-21", detections: 40, latest: { longitude: 30.16, latitude: 12.0 },
    ucdp_events: 5, ucdp_deaths_best: 61, ucdp_latest: "2026-09-28", ucdp_dyad: "Government of Sudan - RSF", nearest_event_km: 6.2 }],
  events: { type: "FeatureCollection", features: [] },
  heat_check: { configured: true, checked: 400, with_heat: 120, no_heat: 270, persistent_only: 10, pending: 20, not_checkable: 310, share_with_heat: 0.3 },
  attribution: "Source: Uppsala Conflict Data Program (UCDP) Candidate Events Dataset, CC BY 4.0", citation: "Hegre et al. (2020)",
  caveats: "UCDP Candidate data are preliminary.", heat_note: "Heat cross-check.", transformation: "Totals computed by MCHO.",
  freshness: { refresh_scheduled: false, last_successful_refresh_at: NOW, last_attempt: { status: "succeeded", error_summary: null } },
};

async function mockThermal(page: Page, configured = true) {
  await page.route("**/conflict/overview**", (route) => route.fulfill({ json: CONFLICT }));
  await page.route("**/damage/overview**", (route) => {
    const country = new URL(route.request().url()).searchParams.get("country");
    return route.fulfill({ json: country && country !== "PSE" ? { ...DAMAGE, assessments: [], cells: { type: "FeatureCollection", features: [] } } : DAMAGE });
  });
  await page.route("**/maritime/overview**", (route) => {
    const country = new URL(route.request().url()).searchParams.get("country");
    return route.fulfill({ json: maritimeFor(country) });
  });
  await page.route("**/thermal/tracks**", (route) => route.fulfill({ json: configured ? TRACKS : { ...TRACKS, features: [], total_tracks: 0 } }));
  await page.route("**/thermal/countries", (route) => route.fulfill({ json: COUNTRIES }));
  await page.route("**/thermal/countries/*/trend**", (route) => {
    const iso3 = new URL(route.request().url()).pathname.split("/").at(-2) ?? "SDN";
    return route.fulfill({ json: trendFor(iso3, iso3 === "SDN" ? "Sudan" : "Iraq") });
  });
  const freshness = configured ? FRESHNESS : { ...FRESHNESS, configured: false, last_successful_refresh_at: null, last_attempt: null };
  await page.route("**/thermal/detections**", (route) => route.fulfill({
    json: configured ? THERMAL_DETECTIONS : { ...THERMAL_DETECTIONS, features: [], freshness },
  }));
  await page.route("**/thermal/insights**", (route) => {
    // Like the API, echo the requested country and window.
    const query = new URL(route.request().url()).searchParams;
    const echo = { country: query.get("country"), window_hours: Number(query.get("hours") ?? 24) };
    return route.fulfill({
      json: configured ? { ...THERMAL_INSIGHTS, ...echo } : {
        ...THERMAL_INSIGHTS, ...echo, latest_detection_at: null, countries: [], new_activity_clusters: [], freshness,
        totals: { active_detections: 0, new_detections: 0, persistent_detections: 0, elevated_countries: 0 },
      },
    });
  });
}

async function mockRuntime(page: Page, style: "slow-tiles" | "broken") {
  await mockThermal(page);
  await page.route("**/api/public-config", (route) => route.fulfill({
    json: { oidcAuthority: "", oidcClientId: "", oidcResource: "", mapStyleUrl: STYLE_URL },
  }));
  if (style === "broken") {
    await page.route(STYLE_URL, (route) => route.fulfill({ status: 404, body: "not found" }));
  } else {
    await page.route(STYLE_URL, (route) => route.fulfill({
      json: {
        version: 8,
        sources: { base: { type: "raster", tiles: ["https://tiles.mcho.test/{z}/{x}/{y}.png"], tileSize: 256 } },
        layers: [{ id: "base", type: "raster", source: "base" }],
      },
    }));
    // Tiles never arrive during the test, so MapLibre's "load" event never fires.
    await page.route("https://tiles.mcho.test/**", (route) => { heldTileRequests.push(route); });
  }
  await page.route("**/map/events**", (route) => route.fulfill({
    json: {
      type: "FeatureCollection", features: [], truncated: false, feature_limit: 2000,
      response_generated_at: "2026-10-20T00:00:00+00:00",
    },
  }));
}

test("requests published records once the style is ready, without waiting for basemap tiles", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  // The map's own status line; the side panels have status messages too.
  const status = page.locator(".map-status").getByRole("status").filter({ hasText: /map features|basemap|Loading/ });
  await expect(status).toContainText("0 published map features", { timeout: 15_000 });
  await expect(status).toContainText("Basemap tiles still loading");
  await expect(status).not.toContainText("Waiting for map style configuration");
});

test("explains a basemap style that cannot be loaded", async ({ page }) => {
  await mockRuntime(page, "broken");
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: /basemap/ }))
    .toContainText("The basemap style could not be loaded", { timeout: 15_000 });
});

test("retries while a sleeping API wakes up, then shows the data", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  let calls = 0;
  // Registered after mockRuntime, so this handler takes precedence.
  await page.route("**/map/events**", (route) => {
    calls += 1;
    if (calls === 1) return route.fulfill({ status: 502, json: { detail: "Backend API is temporarily unavailable." } });
    return route.fulfill({ json: {
      type: "FeatureCollection", features: [], truncated: false, feature_limit: 2000,
      response_generated_at: "2026-10-21T00:00:00+00:00",
    } });
  });
  await page.goto("/");
  const status = page.locator(".map-status").getByRole("status").filter({ hasText: /API|map features|Loading/ });
  await expect(status).toContainText("The API is waking up", { timeout: 15_000 });
  await expect(status).toContainText("0 published map features", { timeout: 15_000 });
  expect(calls).toBe(2);
});

test("does not retry client errors", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  let calls = 0;
  await page.route("**/map/events**", (route) => { calls += 1; return route.fulfill({ status: 404, json: { detail: "Not found." } }); });
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: /Map data unavailable/ }))
    .toContainText("API returned HTTP 404", { timeout: 15_000 });
  await page.waitForTimeout(4_000);
  expect(calls).toBe(1);
});

test("shows satellite heat detections with a legend and status", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  await expect(page.getByLabel("Map legend")).toContainText("New activity");
  await expect(page.getByRole("status").filter({ hasText: /Satellite heat detections in view/ }))
    .toContainText("last 24 h: 2 · newest 2026-10-21 01:42 UTC", { timeout: 15_000 });
});

test("insights panel highlights unusual activity and zooms the map to a cluster", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Satellite insights" });
  await expect(panel).toContainText("countries above normal", { timeout: 15_000 });
  await expect(panel.getByRole("listitem").filter({ hasText: "Sudan" }).first()).toContainText("5.7× the 7-day daily average");
  await page.evaluate(() => {
    window.addEventListener("mcho:fly-to", (event) => {
      (window as unknown as { lastFlyTo: unknown }).lastFlyTo = (event as CustomEvent).detail;
    });
  });
  await panel.getByRole("button", { name: /Sudan · 12 detections/ }).click();
  expect(await page.evaluate(() => (window as unknown as { lastFlyTo: unknown }).lastFlyTo))
    .toEqual({ longitude: 32.55, latitude: 15.57, zoom: 10 });
  await expect(panel.locator("tr.elevated")).toContainText("Sudan");
});

test("explains when the satellite feed is not configured", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await mockThermal(page, false);
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Satellite insights" }))
    .toContainText("not configured on the server yet", { timeout: 15_000 });
  await expect(page.getByRole("status").filter({ hasText: /Satellite heat detections:/ }))
    .toContainText("NASA FIRMS feed is not configured");
});

test("country and time filters drive the map, insights and trend, and are kept in the URL", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  const requests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/thermal/")) requests.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: /Satellite heat detections in view/ })).toBeVisible({ timeout: 15_000 });

  await page.getByLabel("Time window").selectOption("72");
  await page.getByLabel("Country").selectOption("SDN");
  await expect(page).toHaveURL(/country=SDN/);
  await expect(page).toHaveURL(/hours=72/);
  await expect(page.getByRole("heading", { name: "Sudan", exact: true })).toBeVisible();

  const trend = page.getByRole("region", { name: "Sudan 3-week trend" });
  await expect(trend).toBeVisible({ timeout: 15_000 });
  await expect(trend).toContainText("Seasonal context");
  await expect(trend.getByRole("img", { name: /Daily satellite heat detections in Sudan/ })).toBeVisible();
  await expect.poll(() => requests.some((u) => u.includes("/thermal/detections") && u.includes("hours=72") && u.includes("country=SDN"))).toBe(true);
  await expect.poll(() => requests.some((u) => u.includes("/thermal/insights") && u.includes("country=SDN"))).toBe(true);

  await trend.getByRole("button", { name: "Back to all countries" }).click();
  await expect(page).not.toHaveURL(/country=/);
  await expect(page.getByRole("region", { name: /3-week trend/ })).toHaveCount(0);
});

test("opens a shared link with its country and time window", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/?country=IRQ&hours=6");
  await expect(page.getByLabel("Country")).toHaveValue("IRQ", { timeout: 15_000 });
  await expect(page.getByLabel("Time window")).toHaveValue("6");
  await expect(page.getByRole("region", { name: "Iraq 3-week trend" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("region", { name: "Iraq 3-week trend" })).not.toContainText("Seasonal context");
});

test("hides the published-events section while there are no events", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: /published map features/ })).toContainText("0 published map features", { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Published events" })).toHaveCount(0);
});

test("about page explains the data and links back to the map", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How MCHO reads satellite heat");
  await expect(page.getByRole("heading", { name: "What it can't tell you" })).toBeVisible();
  await expect(page.getByRole("link", { name: "← Back to the live map" })).toHaveAttribute("href", "/");
});

test("shows recent Sentinel-2 imagery for a new-activity cluster", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  const scene = (id: string, date: string, cloud: number) => ({
    id, acquired_at: `${date}T08:57:42+00:00`, cloud_cover_percent: cloud, tile: "MGRS-34PHS",
    preview_url: `https://sentinel-cogs.mcho.test/${id}/preview.jpg`, bbox: [23, 9, 25, 11], marker: { x: 0.4, y: 0.6 },
    browser_url: `https://browser.dataspace.copernicus.eu/?lat=15.57&lng=32.55&fromTime=${date}T00:00:00.000Z`,
  });
  await page.route("**/sentinel2/scenes**", (route) => route.fulfill({ json: {
    latitude: 15.57, longitude: 32.55, days: 30, clearest_recent_id: "S2_clear",
    scenes: [scene("S2_cloudy", "2026-10-19", 68), scene("S2_clear", "2026-10-14", 3)],
    caveats: "Sentinel-2 is a different satellite from the heat detections.", source: { name: "Earth Search" },
  } }));
  // 1x1 transparent PNG for the preview images.
  await page.route("https://sentinel-cogs.mcho.test/**", (route) => route.fulfill({
    contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64"),
  }));
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Satellite insights" });
  const toggle = panel.getByRole("button", { name: "Satellite image" }).first();
  await expect(toggle).toBeVisible({ timeout: 15_000 });
  await toggle.click();

  const imagery = panel.getByLabel("Sentinel-2 imagery near Sudan cluster");
  await expect(imagery.getByRole("img")).toHaveAttribute("alt", /2026-10-14 08:57 UTC, 3% cloud/);
  await expect(imagery.locator(".imagery-marker")).toHaveAttribute("style", /left: 40%; top: 60%/);
  await expect(imagery.getByRole("link", { name: /full 10 m resolution/ })).toHaveAttribute("href", /fromTime=2026-10-14/);
  await imagery.getByRole("button", { name: /19 Oct/ }).click();
  await expect(imagery.getByRole("img")).toHaveAttribute("alt", /2026-10-19 08:57 UTC, 68% cloud/);

  await panel.getByRole("button", { name: "Hide satellite image" }).click();
  await expect(panel.getByLabel("Sentinel-2 imagery near Sudan cluster")).toHaveCount(0);
});

test("compares with the same days last year in the trend and country table", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/?country=SDN");
  const trend = page.getByRole("region", { name: "Sudan 3-week trend" });
  await expect(trend).toContainText("Same days last year: 350 detections in the last 7 full days vs 420", { timeout: 15_000 });
  await expect(trend).toContainText("(-17%)");
  await expect(trend).toContainText("Same day last year (total)");
  expect(await trend.locator("rect.trend-last-year").count()).toBeGreaterThan(5);
  await expect(page.getByRole("region", { name: "Satellite insights" }).locator("tr", { hasText: "Sudan" })).toContainText("0.83×");
});

test("lists moving fronts and zooms the map to the latest position", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  await expect(page.getByLabel("Map legend")).toContainText("Moving front, 7 days");
  const fronts = page.getByRole("region", { name: "Moving fronts" });
  const sudan = fronts.getByRole("button", { name: /Sudan · 3 days · 312 detections · active/ });
  await expect(sudan).toBeVisible({ timeout: 15_000 });
  await expect(sudan).toContainText("moved 17 km E (~9 km/day)");
  await expect(fronts.getByRole("button", { name: /Iraq · 2 days/ })).toContainText("stayed in about the same area");
  await page.evaluate(() => window.addEventListener("mcho:fly-to", (e) => {
    (window as unknown as { lastFlyTo: unknown }).lastFlyTo = (e as CustomEvent).detail;
  }));
  await sudan.click();
  expect(await page.evaluate(() => (window as unknown as { lastFlyTo: unknown }).lastFlyTo)).toEqual({ longitude: 30.16, latitude: 12.0, zoom: 9 });
});

test("shows shipping chokepoints and ports from IMF PortWatch, following the country filter", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  const shipping = page.getByRole("region", { name: "Shipping" });
  const bab = shipping.getByRole("article", { name: "Bab el-Mandeb Strait" });
  await expect(bab).toContainText("30.4 /day", { timeout: 15_000 });
  await expect(bab).toContainText("-58% vs last year");
  await expect(bab).toContainText("Same days last year: 72.1/day · tankers 5/day");
  await expect(bab.getByRole("img", { name: /daily transits over 90 days/ })).toBeVisible();
  await expect(shipping).toContainText("latest day 2026-10-18");
  await expect(shipping).toContainText("Source: International Monetary Fund, PortWatch");
  await expect(shipping.locator("tbody tr")).toHaveCount(2);
  await expect(page.getByLabel("Map legend")).toContainText("Shipping chokepoint / port");

  await page.getByLabel("Country").selectOption("SDN");
  await expect(shipping).toContainText("PortWatch covers no ports in Sudan");
  await page.goto("/?country=IRQ");
  await expect(shipping).toContainText("Ports in Iraq");
});

test("lists UN satellite damage assessments, hiding superseded ones from the map", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  const damage = page.getByRole("region", { name: "Damage assessments" });
  const gaza = damage.getByRole("article", { name: /11 October 2025/ });
  await expect(gaza).toContainText("123,464 destroyed · 17,116 severely damaged", { timeout: 15_000 });
  await expect(gaza).toContainText("Imagery 2025-10-11 · published 2025-10-31 · CE20231007PSE");
  await expect(damage.getByRole("article")).toHaveCount(1);
  await damage.getByRole("button", { name: "Show 1 older, overlapping or unmapped assessment" }).click();
  await expect(damage.locator("tbody tr")).toContainText("Covered by newer: UNOSAT Gaza Strip");
  await expect(damage).toContainText("Source: United Nations Satellite Centre (UNOSAT)");
  await expect(page.getByLabel("Map legend")).toContainText("UN-assessed building damage");
  await page.evaluate(() => window.addEventListener("mcho:fly-to", (e) => {
    (window as unknown as { lastFlyTo: unknown }).lastFlyTo = (e as CustomEvent).detail;
  }));
  await gaza.getByRole("button", { name: "Show on map" }).click();
  expect(await page.evaluate(() => (window as unknown as { lastFlyTo: unknown }).lastFlyTo)).toEqual({ longitude: 34.5, latitude: 31.5, zoom: 10 });

  await page.getByLabel("Country").selectOption("SDN");
  await expect(damage).toContainText("No UNOSAT conflict damage assessments for Sudan on HDX.");
});

test("shows UCDP verified events, deaths and the satellite heat cross-check", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  const conflict = page.getByRole("region", { name: "Verified conflict events" });
  await expect(conflict).toContainText("4,330", { timeout: 15_000 });
  await expect(conflict).toContainText("deaths (best estimate; range 3,900–5,100)");
  await expect(conflict).toContainText("Not downloaded: Jul 2026. Those months are missing, not zero.");
  await expect(conflict).toContainText("Jul 2026: not downloaded");
  await expect(conflict).toContainText("120 of 400 precisely located events had satellite heat nearby within a day (30%)");
  const withHeat = conflict.getByRole("region", { name: "Events with satellite heat" }).or(conflict.getByLabel("Events with satellite heat"));
  await expect(withHeat.getByRole("article").first()).toContainText("Satellite heat 2.4 km away (3 detections within 5 km, ±1 day)");
  await expect(withHeat.getByRole("article").first()).toContainText("Deaths: 30 (25–40) · civilians 12");
  await expect(conflict).toContainText("5 UCDP events within 25 km in the last 180 days (61 deaths, latest 2026-09-28");
  await expect(conflict).toContainText("Cite: Hegre et al. (2020)");
  await expect(page.getByLabel("Map legend")).toContainText("Verified violent event (UCDP)");
});

test("hero shows live headline figures; basemap and legend controls work", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/");
  const figures = page.getByLabel("Headline figures, the whole MENA region");
  await expect(figures).toContainText("4,330", { timeout: 15_000 });
  await expect(figures).toContainText("123,464");
  await expect(figures).toContainText("730 events · Jul–Sept · UCDP");

  const satellite = page.getByRole("group", { name: "Basemap" }).getByRole("button", { name: "Satellite" });
  const plain = page.getByRole("group", { name: "Basemap" }).getByRole("button", { name: "Map" });
  await expect(satellite).toHaveAttribute("aria-pressed", "true");
  await plain.click();
  await expect(plain).toHaveAttribute("aria-pressed", "true");
  await expect(satellite).toHaveAttribute("aria-pressed", "false");

  const legendToggle = page.getByLabel("Map legend").getByRole("button", { name: /Legend/ });
  await legendToggle.click();
  await expect(legendToggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByLabel("Map legend").getByText("New activity")).toBeHidden();

  await page.getByRole("navigation", { name: "Site" }).getByRole("link", { name: "Verified violence" }).click();
  await expect(page).toHaveURL(/#violence$/);
});

test("retries a busy server (429) and keeps the heading true to the data shown", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  let insightsCalls = 0;
  // Registered after the default mocks, so it is consulted first.
  await page.route("**/thermal/insights**", async (route) => {
    insightsCalls += 1;
    const country = new URL(route.request().url()).searchParams.get("country");
    if (insightsCalls === 1) return route.fulfill({ status: 429, body: "busy" });
    if (country === "IRQ") return route.fulfill({ status: 404, json: { detail: "not found" } });
    return route.fallback();
  });
  await page.goto("/");
  const insights = page.getByRole("region", { name: "Satellite insights" });
  await expect(insights).toContainText("14", { timeout: 20_000 });
  expect(insightsCalls).toBeGreaterThanOrEqual(2);
  await expect(insights).not.toContainText("HTTP 429");

  await page.getByLabel("Country").selectOption("IRQ");
  await expect(insights).toContainText("Still showing the whole region, last 24 h.", { timeout: 15_000 });
  await expect(insights).toContainText("Satellite insights unavailable: API returned HTTP 404");
  await expect(insights.getByRole("heading", { name: "New activity clusters", exact: true })).toBeVisible();
});

test("hero heat figure follows the selected country, not the region total", async ({ page }) => {
  await mockRuntime(page, "slow-tiles");
  await page.goto("/?country=SDN");
  const heat = page.getByLabel("Headline figures, Sudan").locator(".hero-stat").first();
  await expect(heat).toContainText("12 at new locations", { timeout: 15_000 });
  await expect(heat.locator(".hero-stat-value")).toHaveText("12");  // Sudan's row, not the region's 14
  await expect(page.getByRole("region", { name: "Satellite insights" })).toContainText("Totals below cover the whole region");
});
