import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/demo");
});

test("clearly labels the prototype as synthetic and renders five illustrative markers", async ({ page }) => {
  await expect(page.getByText("Prototype data — not live conflict information")).toBeVisible();
  await expect(page.getByRole("tab", { name: /Overview/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".mcho-map-point")).toHaveCount(5);
  await expect(page.getByText("No live geospatial data", { exact: false })).toBeVisible();
});

test("navigates across all six modules", async ({ page }) => {
  await page.getByRole("tab", { name: /Event explorer/ }).click();
  await expect(page.getByRole("heading", { name: "Event explorer" })).toBeVisible();

  await page.getByRole("tab", { name: /Satellite observations/ }).click();
  await expect(page.getByRole("heading", { name: "Satellite observations" })).toBeVisible();

  await page.getByRole("tab", { name: /Humanitarian indicators/ }).click();
  await expect(page.getByRole("heading", { name: "Humanitarian indicators" })).toBeVisible();

  await page.getByRole("tab", { name: /Maritime aggregates/ }).click();
  await expect(page.getByRole("heading", { name: "Maritime aggregates" })).toBeVisible();

  await page.getByRole("tab", { name: /Methodology & provenance/ }).click();
  await expect(page.getByRole("heading", { name: "Confidence is not truth" })).toBeVisible();

  await page.getByRole("tab", { name: /Overview/ }).click();
  await expect(page.getByRole("heading", { name: "Regional overview" })).toBeVisible();
});

test("filters event records by status and search term", async ({ page }) => {
  await page.getByRole("tab", { name: /Event explorer/ }).click();
  await page.getByLabel("Filter records by status").selectOption("provisional");
  await expect(page.locator(".mcho-record")).toHaveCount(2);

  await page.getByLabel("Filter records by status").selectOption("all");
  await page.getByPlaceholder("Search example records…").fill("displacement");
  await expect(page.locator(".mcho-record")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Illustrative displacement reporting/ })).toBeVisible();

  await page.getByPlaceholder("Search example records…").fill("no matching synthetic report");
  await expect(page.getByText(/No synthetic records match these filters/)).toBeVisible();
});

test("selects a record from the list and updates its provenance detail", async ({ page }) => {
  await page.getByRole("tab", { name: /Event explorer/ }).click();
  await page.getByPlaceholder("Search example records…").fill("displacement");
  await page.getByRole("button", { name: /Illustrative displacement reporting/ }).click();
  await expect(page.getByRole("heading", { name: "Illustrative displacement reporting", level: 3 })).toBeVisible();
  await expect(page.getByText("https://example.invalid/report-d")).toBeVisible();
  await expect(page.getByText("SYNTHETIC DEMO", { exact: false })).toHaveCount(0);
});

test("map-marker selection changes details and review action remains preview-only", async ({ page }) => {
  const marker = page.locator('[aria-label="Select Illustrative access constraint report"]');
  await marker.click();
  await expect(page.getByRole("heading", { name: "Illustrative access constraint report", level: 3 })).toBeVisible();

  await page.getByRole("button", { name: "Preview review action" }).click();
  await expect(page.getByRole("status")).toContainText("review and publication actions are disabled");

  await marker.focus();
  await marker.press("Enter");
  await expect(page.getByRole("heading", { name: "Illustrative access constraint report", level: 3 })).toBeVisible();
});

test("copies provenance while explicitly preserving synthetic-data context", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Copy demo provenance" }).click();
  await expect(page.getByRole("status")).toContainText("Synthetic provenance copied");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("https://example.invalid/report-a");
  expect(copied).toContain("SYNTHETIC DEMO — NOT A REAL SOURCE");
});

test("keeps the primary navigation and event explorer usable at mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: /Maritime aggregates/ }).click();
  await expect(page.getByRole("heading", { name: "Maritime aggregates" })).toBeVisible();
  await page.getByRole("tab", { name: /Event explorer/ }).click();
  await page.getByPlaceholder("Search example records…").fill("access");
  await expect(page.locator(".mcho-record")).toHaveCount(2);
});
