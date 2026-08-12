import { expect, test } from "@playwright/test";

async function stabilize(page) {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.evaluate(async () => document.fonts.ready);
  await expect(page.locator(".skip-link")).toHaveAttribute("href", "#main-content");
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
}

async function expectPageScreenshot(page, testInfo, route, name) {
  await page.goto(route, { waitUntil: "networkidle" });
  await stabilize(page);
  await expect(page).toHaveScreenshot(`${name}-${testInfo.project.name}.png`, {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
    scale: "css",
  });
}

test("Academy Home remains visually stable", async ({ page }, testInfo) => {
  await expectPageScreenshot(page, testInfo, "/index.html", "home");
});

for (const [lesson, name] of [
  ["F01-fork-clone-doctor", "f01"],
  ["F02-orient-to-state", "f02"],
]) {
  test(`${lesson} keeps its first copyable action usable`, async ({ page }, testInfo) => {
    await page.goto(`/labs/${lesson}/index.html`, { waitUntil: "networkidle" });
    await stabilize(page);
    const copy = page.locator(".command-copy").first();
    await copy.scrollIntoViewIfNeeded();
    await expect(copy).toBeVisible();
    await expect(copy).toBeInViewport();
    await expect(page).toHaveScreenshot(`${name}-${testInfo.project.name}.png`, {
      animations: "disabled",
      caret: "hide",
      fullPage: false,
      scale: "css",
    });
  });
}
