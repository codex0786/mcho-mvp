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
    { iso_a3: "SDN", name: "Sudan", active_detections: 12, new_detections: 12, persistent_detections: 0, baseline_daily_average: 2.1, ratio_to_baseline: 5.7, max_frp_mw: 31, elevated: true },
    { iso_a3: "IRQ", name: "Iraq", active_detections: 2, new_detections: 0, persistent_detections: 30, baseline_daily_average: 2.4, ratio_to_baseline: 0.8, max_frp_mw: 12, elevated: false },
  ],
  new_activity_clusters: [{ country: "Sudan", detections: 12, longitude: 32.55, latitude: 15.57, max_frp_mw: 31, first_seen: NOW, last_seen: NOW, satellites: 2 }],
  method: { cell_degrees: 0.02, cluster_degrees: 0.1, baseline_days: 7, persistent_min_days: 4, elevated_rule: "at least 10 non-persistent detections and at least 2x the baseline daily average" },
  caveats: "Satellite heat detections (NASA FIRMS). Each is a heat signature, not a verified event.",
  source: { name: "NASA FIRMS", url: "https://firms.modaps.eosdis.nasa.gov/", attribution: "NASA FIRMS" },
  freshness: FRESHNESS,
};

async function mockThermal(page: Page, configured = true) {
  const freshness = configured ? FRESHNESS : { ...FRESHNESS, configured: false, last_successful_refresh_at: null, last_attempt: null };
  await page.route("**/thermal/detections**", (route) => route.fulfill({
    json: configured ? THERMAL_DETECTIONS : { ...THERMAL_DETECTIONS, features: [], freshness },
  }));
  await page.route("**/thermal/insights**", (route) => route.fulfill({
    json: configured ? THERMAL_INSIGHTS : {
      ...THERMAL_INSIGHTS, latest_detection_at: null, countries: [], new_activity_clusters: [], freshness,
      totals: { active_detections: 0, new_detections: 0, persistent_detections: 0, elevated_countries: 0 },
    },
  }));
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
  const status = page.getByRole("status").filter({ hasText: /map features|basemap|Loading/ });
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
  const status = page.getByRole("status").filter({ hasText: /API|map features|Loading/ });
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
