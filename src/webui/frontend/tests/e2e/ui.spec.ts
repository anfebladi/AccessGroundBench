import { expect, test, type Page } from "@playwright/test";

async function mockApi(page: Page) {
  const resultRows = [
    {
      filename: "demo-atlas-vision.csv",
      model: "Atlas",
      prompt_mode: "vision",
      row_count: 100,
      statuses: { api_error: 0 },
      hits: 96,
      co_present_count: 100,
      accuracy: 0.96,
      baseline_accuracy: 0.98,
    },
    {
      filename: "demo-atlas-tree.csv",
      model: "Atlas",
      prompt_mode: "tree",
      row_count: 100,
      statuses: { off_screen: 2 },
      hits: 88,
      co_present_count: 98,
      accuracy: 0.897,
      baseline_accuracy: 0.95,
    },
  ];
  const compareResult = {
    model: "Atlas",
    mode: "vision",
    models_in_family: ["Atlas"],
    profiles: [
      {
        profile: "font_scale_1_3",
        baseline_accuracy: 98.0,
        profile_accuracy: 97.0,
        delta: -1.0,
        b: 1,
        c: 2,
        reachability: 0.99,
        significance_state: "no_change",
      },
      {
        profile: "high_contrast",
        baseline_accuracy: 99.0,
        profile_accuracy: 99.5,
        delta: 0.5,
        b: 0,
        c: 1,
        reachability: 1,
        significance_state: "underpowered",
        power_flag: "ceiling/floor",
      },
    ],
  };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/datasets") return route.fulfill({ json: [{ name: "demo", screen_count: 2, image_count: 4 }] });
    if (path.endsWith("/screens")) return route.fulfill({ json: { screens: ["home", "settings"] } });
    if (path.endsWith("/manifest")) return route.fulfill({ json: { available: true, manifest: { expected_captures: 4, successful_captures: 4, problems: ["high content drift: settings at 10.5%"] } } });
    if (path.endsWith("/targets/home") || path.endsWith("/targets/settings")) return route.fulfill({ json: { targets: [{ text: "Continue", baseline_box: [10, 10, 100, 40] }] } });
    if (path.includes("/labels/")) return route.fulfill({ json: [{ text: "Continue", box: [10, 10, 100, 40] }] });
    if (path === "/api/providers") return route.fulfill({ json: [{ provider: "openai", env_vars: ["OPENAI_API_KEY"], configured: false }] });
    if (path.includes("/results/compare")) return route.fulfill({ json: compareResult });
    if (path.endsWith("/results")) return route.fulfill({ json: resultRows });
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

  test("workflow navigation switches the hash route and hides every non-selected view", async ({ page }) => {
    const tabs = ["dataset", "models", "evaluate", "collect", "compare", "results", "analyze"];
    const responsive = test.info().project.name === "responsive";
    const desktopRail = page.locator("#rail");
    const mobileRail = page.locator("#mobile-rail");
    await page.goto("/#dataset");
    await waitForFixture(page, "dataset");

    for (const tab of tabs) {
      let activeRail = desktopRail;
      if (responsive) {
        await page.getByRole("button", { name: /workflow menu|^menu$/i }).click();
        const sheet = page.getByRole("dialog");
        await expect(sheet).toBeVisible();
        activeRail = sheet.locator("#mobile-rail");
        const link = activeRail.locator(`a[data-tab="${tab}"]`);
        await expect(link).toBeVisible();
        await link.click();
        await expect(sheet).toBeHidden();
      } else {
        await activeRail.locator(`a[data-tab="${tab}"]`).click();
      }
      await expect(page).toHaveURL(new RegExp(`#${tab}$`));
      // The Sheet unmounts its mobile rail on close; route state is reflected
      // by the persistent (hidden on narrow viewports) desktop rail.
      const selectedRail = desktopRail;
      await expect(selectedRail.locator(`a[data-tab="${tab}"]`)).toHaveAttribute("aria-current", "page");
      await expect(page.locator(`#tab-${tab}`)).toBeVisible();
      for (const other of tabs.filter((candidate) => candidate !== tab)) {
        await expect(page.locator(`#tab-${other}`)).toBeHidden();
        await expect(selectedRail.locator(`a[data-tab="${other}"]`)).not.toHaveAttribute("aria-current");
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

  test("Results renders populated chart, selection card, and table", async ({ page }) => {
    await page.goto("/#results");
    await waitForFixture(page, "results");
    await expect(page.locator("#results-overall-accuracy")).toBeVisible();
    await expect(page.locator("#results-table tbody tr")).toHaveCount(2);
    await expect(page.locator('[data-compare-select="demo-atlas-vision.csv"]')).toHaveAttribute("aria-checked", "false");
    await page.locator('[data-compare-select="demo-atlas-vision.csv"]').click();
    await page.locator('[data-compare-select="demo-atlas-tree.csv"]').click();
    await expect(page.locator("#results-selected-comparison")).toBeVisible();
    await expect(page.locator('[data-compare-select="demo-atlas-vision.csv"]')).toHaveAttribute("aria-checked", "true");
    await expect(page.locator('[data-compare-select="demo-atlas-tree.csv"]')).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("#results-body")).toHaveScreenshot("results-populated.png", {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.01,
    });
  });

  test("Compare renders dark dumbbell chart and underpowered row", async ({ page }) => {
    await page.goto("/#compare");
    await waitForFixture(page, "compare");
    await expect(page.locator("#compare-body .card-dark")).toBeVisible();
    await expect(page.getByRole("img", { name: "Baseline versus profile accuracy", exact: true })).toBeVisible();
    await expect(page.locator("#compare-body")).toContainText("Underpowered");
    await expect(page.locator("#compare-body")).toContainText("99.5%");
    const chart = page.locator("#compare-body .chart-dumbbell-overlay");
    const computedPalette = await chart.locator(".chart-dumbbell-baseline").first().evaluate((element) => {
      const baseline = element as SVGCircleElement;
      const overlay = baseline.parentElement?.parentElement;
      const profile = overlay?.querySelector(".chart-dumbbell-profile") as SVGCircleElement | null;
      const label = overlay?.querySelector(".chart-dumbbell-label") as SVGTextElement | null;
      const connector = overlay?.querySelector(".chart-dumbbell-connector") as SVGLineElement | null;
      return {
        baselineFill: getComputedStyle(baseline).fill,
        profileFill: profile ? getComputedStyle(profile).fill : "",
        labelFill: label ? getComputedStyle(label).fill : "",
        connectorStroke: connector ? getComputedStyle(connector).stroke : "",
        connectorX1: connector?.getAttribute("x1"),
        connectorX2: connector?.getAttribute("x2"),
      };
    });
    expect(computedPalette.baselineFill).toBe("rgb(42, 120, 214)");
    expect(computedPalette.profileFill).toBe("rgb(235, 104, 52)");
    expect(computedPalette.labelFill).toBe("rgb(244, 244, 245)");
    expect(computedPalette.connectorStroke).not.toMatch(/rgb\(0, 0, 0\)|rgba\(0, 0, 0/);
    expect(computedPalette.connectorX1).not.toBe(computedPalette.connectorX2);
    await expect(page.locator("#compare-body")).toHaveScreenshot("compare-populated.png", {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.01,
    });
  });
});
