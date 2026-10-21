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

async function mockRuntime(page: Page, style: "slow-tiles" | "broken") {
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
