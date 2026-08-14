import { expect, test, type Page } from "@playwright/test";
import { deflateSync } from "node:zlib";

/* The dataset is tall Android captures -- every PNG in
   collections/experiment/dataset/images is 1080x2219, 1080x2196 or 1080x2177.
   The shape matters here: an aspect-ratio bug only shows up when the capture's
   natural ratio is far from the viewport's, so the shared mockApi in ui.spec.ts
   (a 1x1 PNG) cannot catch one. Hence the real-shaped PNG built below. */
const NATURAL_WIDTH = 1080;
const NATURAL_HEIGHT = 2219;
const NATURAL_RATIO = NATURAL_WIDTH / NATURAL_HEIGHT;

function chunk(type: string, data: Buffer): Buffer {
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const crcTable: number[] = [];
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crcTable[n] = c >>> 0;
  }
  let crc = 0xffffffff;
  for (const byte of body) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
  return Buffer.concat([len, body, crcBuf]);
}

function tallPng(): Buffer {
  const row = Buffer.concat([
    Buffer.from([0]),
    Buffer.alloc(NATURAL_WIDTH * 3, 0x28),
  ]);
  const raw = Buffer.concat(Array.from({ length: NATURAL_HEIGHT }, () => row));
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(NATURAL_WIDTH, 0);
  ihdr.writeUInt32BE(NATURAL_HEIGHT, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const PNG = tallPng();

async function mockStage(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/datasets")
      return route.fulfill({ json: [{ name: "demo", screen_count: 1, image_count: 2 }] });
    if (path.endsWith("/screens")) return route.fulfill({ json: { screens: ["clock"] } });
    if (path.endsWith("/manifest"))
      return route.fulfill({ json: { available: false } });
    if (path.includes("/targets/"))
      return route.fulfill({ json: { targets: [{ text: "Alarms", baseline_box: [40, 180, 300, 260] }] } });
    if (path.includes("/labels/"))
      return route.fulfill({ json: [{ text: "Alarms", box: [40, 180, 300, 260] }] });
    if (path.includes("/image/"))
      return route.fulfill({ contentType: "image/png", body: PNG });
    // The shell renders before the stage does, and it expects arrays here --
    // an object makes Sidebar throw and the whole view falls back to its error card.
    if (path === "/api/providers") return route.fulfill({ json: [] });
    if (path === "/api/collect/screens")
      return route.fulfill({ json: { all_screens: ["clock"] } });
    if (path.endsWith("/results")) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });
}

async function openStage(page: Page) {
  await mockStage(page);
  await page.goto("/#dataset");
  // The stage renders "No screen selected" until one is picked.
  await page.locator("#screen-list").getByText("clock", { exact: true }).click();
  await expect(page.locator("#canvas-baseline")).toBeVisible();
  // The canvas only carries its natural size once the image has decoded.
  await expect
    .poll(async () =>
      page.locator("#canvas-baseline").evaluate((c) => (c as HTMLCanvasElement).width),
    )
    .toBe(NATURAL_WIDTH);
}

async function renderedRatio(page: Page) {
  return page.locator("#canvas-baseline").evaluate((c) => {
    const r = c.getBoundingClientRect();
    return r.width / r.height;
  });
}

test.describe("comparison stage rendering", () => {
  test("renders the screenshot at its own aspect ratio, fitted to the viewport", async ({ page }) => {
    await openStage(page);
    /* Regression: the pane once set an explicit width and height on the canvas
       while max-width and max-height were still applied, so the two axes clamped
       independently and the capture rendered stretched (0.6 instead of 0.487).
       Sizing must stay class-only so the browser keeps the intrinsic ratio. */
    expect(await renderedRatio(page)).toBeCloseTo(NATURAL_RATIO, 2);
    const fits = await page.locator("#viewport-baseline").evaluate(
      (v) => v.scrollHeight <= v.clientHeight + 1,
    );
    expect(fits).toBe(true);
    // Sizing comes from classes only -- no inline width/height to clamp.
    const inline = await page.locator("#canvas-baseline").evaluate((c) => ({
      width: c.style.width,
      height: c.style.height,
    }));
    expect(inline).toEqual({ width: "", height: "" });
  });

  test("offers no zoom control", async ({ page }) => {
    await openStage(page);
    /* The zoom pill was removed: Fit was always sufficient to read these captures,
       and `Export baseline` covers pixel-level inspection at full resolution. */
    await expect(page.locator("#stage-zoom")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "1:1", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Zoom in" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Zoom out" })).toHaveCount(0);
  });
});
