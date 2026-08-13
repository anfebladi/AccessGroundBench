import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/datasets") return route.fulfill({ json: [{ name: "demo", screen_count: 2, image_count: 4 }] });
    if (path.endsWith("/screens")) return route.fulfill({ json: { screens: ["home", "settings"] } });
    if (path.endsWith("/manifest")) return route.fulfill({ json: { available: true, manifest: { expected_captures: 4, successful_captures: 4, problems: ["high content drift: settings at 10.5%"] } } });
    if (path.endsWith("/targets/home") || path.endsWith("/targets/settings")) return route.fulfill({ json: { targets: [{ text: "Continue", baseline_box: [10, 10, 100, 40] }] } });
    if (path.includes("/labels/")) return route.fulfill({ json: [{ text: "Continue", box: [10, 10, 100, 40] }] });
    if (path === "/api/providers") return route.fulfill({ json: [{ provider: "openai", env_vars: ["OPENAI_API_KEY"], configured: false }] });
    if (path.endsWith("/results")) return route.fulfill({ json: [] });
    if (path.endsWith("/analysis")) return route.fulfill({ json: { available: false } });
    if (path === "/api/collect/screens") return route.fulfill({ json: { all_screens: ["home", "settings"] } });
    if (path.includes("/image/")) return route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64") });
    return route.fulfill({ json: {} });
  });
}

async function waitForFixture(page: Page, tab: string) {
  await page.waitForFunction(() => document.fonts?.status === "loaded");
  await expect(page.locator("#dataset-select")).toHaveValue("demo");
  await expect(page.locator(`#tab-${tab}`)).toBeVisible();
  if (tab === "models") {
    await expect(page.locator("#provider-table tbody tr")).toHaveCount(1);
    await expect(page.locator("#model-list")).toContainText(/No models configured yet|Configured models/);
  }
}

test.describe("legacy UI rendered parity", () => {
  test.beforeEach(async ({ page }) => { await mockApi(page); });

  for (const tab of ["dataset", "models", "evaluate", "collect", "compare", "results", "analyze"]) {
    test(`${tab} view exposes its historical root`, async ({ page }) => {
      await page.goto(`/#${tab}`);
      await expect(page.locator(`#tab-${tab}`)).toBeVisible();
      await waitForFixture(page, tab);
      const maskByTab: Record<string, string[]> = {
        dataset: ["#dataset-warnings", "#screen-list", "#screen-browser", "#tab-dataset > .card"],
        models: ["#smoke-test-result"],
        evaluate: ["#eval-preflight", "#eval-run", "#eval-error"],
        collect: ["#collect-screens", "#collect-preflight-result", "#collect-run"],
        compare: ["#compare-body", "#compare-model-select"],
        results: ["#results-body"],
        analyze: ["#analyze-results", "#analyze-error"],
      };
      const mask = (maskByTab[tab] || []).map((selector) => page.locator(selector));
      const screenshotTarget = tab === "dataset" ? page.locator("#tab-dataset > .view-head") : page.locator(`#tab-${tab}`);
      await expect(screenshotTarget).toHaveScreenshot(`${tab}.png`, { animations: "disabled", caret: "hide", mask, maxDiffPixelRatio: 0.01 });
    });
  }

  test("dataset capture health and stage controls render", async ({ page }) => {
    await page.goto("/#dataset");
    await waitForFixture(page, "dataset");
    await expect(page.locator("#compare-overlay-toggles")).toBeVisible();
  });

  test("command palette routes to a screen", async ({ page }) => {
    await page.goto("/#dataset");
    await page.locator("#palette-trigger").click();
    await page.locator("#palette-input").fill("settings");
    await page.locator("#palette-input").press("Enter");
    await expect(page.locator("#screen-list li.selected")).toContainText("settings");
  });

  test("rail clicks switch the hash route and hide every non-selected view", async ({ page }) => {
    const tabs = ["dataset", "models", "evaluate", "collect", "compare", "results", "analyze"];
    await page.goto("/#dataset");
    await waitForFixture(page, "dataset");

    for (const tab of tabs) {
      await page.locator(`a[data-tab="${tab}"]`).click();
      await expect(page).toHaveURL(new RegExp(`#${tab}$`));
      await expect(page.locator(`a[data-tab="${tab}"]`)).toHaveAttribute("aria-current", "page");
      await expect(page.locator(`#tab-${tab}`)).toBeVisible();
      for (const other of tabs.filter((candidate) => candidate !== tab)) {
        await expect(page.locator(`#tab-${other}`)).toBeHidden();
        await expect(page.locator(`a[data-tab="${other}"]`)).not.toHaveAttribute("aria-current");
      }
    }
  });

  test("shell preserves the legacy chrome", async ({ page }) => {
    await page.goto("/#dataset");
    await waitForFixture(page, "dataset");
    await expect(page).toHaveScreenshot("shell.png", {
      animations: "disabled",
      caret: "hide",
      mask: [page.locator(".rail-chip"), page.locator(".app-body main")],
    });
  });
});
