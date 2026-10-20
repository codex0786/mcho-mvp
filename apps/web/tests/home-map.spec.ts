import { expect, test, type Page } from "@playwright/test";

const STYLE_URL = "https://style.mcho.test/style.json";

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
    // Tiles never arrive, so MapLibre's "load" event never fires.
    await page.route("https://tiles.mcho.test/**", () => undefined);
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
