import { expect, test } from "@playwright/test";

for (const path of ["/", "/demo", "/analyst"]) {
  test(`${path} sends security headers`, async ({ request }) => {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    const headers = response.headers();
    const csp = headers["content-security-policy"] ?? "";
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("worker-src 'self' blob:");
    expect(csp).not.toContain("unsafe-eval");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  });
}

for (const path of ["/", "/demo", "/analyst"]) {
  test(`${path} renders without Content-Security-Policy violations`, async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && /Content Security Policy/i.test(message.text())) {
        violations.push(message.text());
      }
    });
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/MENA Conflict |Analyst workspace|Source review/).first()).toBeVisible();
    expect(violations).toEqual([]);
  });
}
