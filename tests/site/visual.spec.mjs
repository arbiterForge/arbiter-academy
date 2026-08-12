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

test("Academy Home keeps the verify-first installer usable", async ({ page }, testInfo) => {
  await page.goto("/index.html", { waitUntil: "networkidle" });
  await stabilize(page);
  const install = page.locator('[data-action-id="home-install"]');
  await install.scrollIntoViewIfNeeded();
  await expect(install).toBeInViewport();
  await expect(install.locator(".command-copy").first()).toBeVisible();
  const command = install.locator(".command-variant pre").first();
  await expect
    .poll(() => command.evaluate((node) => node.scrollWidth <= node.clientWidth))
    .toBe(true);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await expect(page).toHaveScreenshot(`home-install-${testInfo.project.name}.png`, {
    animations: "disabled",
    caret: "hide",
    fullPage: false,
    scale: "css",
  });
});

for (const [lesson, name] of [
  ["F01-fork-clone-doctor", "f01"],
  ["F02-orient-to-state", "f02"],
  ["F03-work-the-board", "f03"],
  ["F04-fix-with-evidence", "f04"],
  ["P01-feature-through-plan", "p01"],
  ["P02-commit-review-pr", "p02"],
  ["P03-record-an-adr", "p03"],
  ["P04-review-a-dependency", "p04"],
  ["P05-checkpoint-remediation", "p05"],
]) {
  test(`${lesson} keeps its first copyable action usable`, async ({ page }, testInfo) => {
    await page.goto(`/labs/${lesson}/index.html`, { waitUntil: "networkidle" });
    await stabilize(page);
    const copy = page.locator(".command-copy").first();
    await copy.scrollIntoViewIfNeeded();
    await expect(copy).toBeVisible();
    await expect(copy).toBeInViewport();
    const visualTarget = ["p04", "p05"].includes(name)
      ? page
          .locator(".lesson-action")
          .filter({ has: copy })
          .locator(".command-variant")
          .first()
      : page;
    await expect(visualTarget).toHaveScreenshot(`${name}-${testInfo.project.name}.png`, {
      animations: "disabled",
      caret: "hide",
      fullPage: false,
      scale: "css",
    });
  });
}

for (const colorScheme of ["dark", "light"]) {
  test(`F04 proof milestones remain legible in ${colorScheme} mode`, async ({ page }) => {
    await page.goto("/labs/F04-fix-with-evidence/index.html", { waitUntil: "networkidle" });
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    await page.evaluate(async () => document.fonts.ready);

    for (const actionId of [
      "F04-prepare",
      "F04-start-fix",
      "F04-request-repair",
      "F04-check",
    ]) {
      const action = page.locator(`[data-action-id="${actionId}"]`);
      await action.scrollIntoViewIfNeeded();
      await expect(action).toBeInViewport();
      await expect(action.locator(".command-copy").first()).toBeVisible();
      if (page.viewportSize()?.width <= 384) {
        const command = action.locator(".command-variant code").first();
        await expect
          .poll(() => command.evaluate((node) => node.scrollWidth <= node.clientWidth))
          .toBe(true);
      }
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
        .toBe(true);
    }
    await expect(page.locator(".lesson-milestone")).toHaveCount(4);
  });
}

for (const [locator, name] of [
  ['h3:has-text("The proof map")', "f04-proof-map"],
  ['[data-action-id="F04-request-repair"]', "f04-repair-boundary"],
]) {
  test(`F04 ${name} remains visually explicit`, async ({ page }, testInfo) => {
    await page.goto("/labs/F04-fix-with-evidence/index.html", { waitUntil: "networkidle" });
    await stabilize(page);
    const target = page.locator(locator);
    await target.scrollIntoViewIfNeeded();
    await expect(target).toBeInViewport();
    if (name === "f04-proof-map" && page.viewportSize()?.width <= 384) {
      const table = page.locator(".academy-content table").first();
      await expect
        .poll(() => table.evaluate((node) => node.scrollWidth <= node.clientWidth))
        .toBe(true);
    }
    await expect(page).toHaveScreenshot(`${name}-${testInfo.project.name}.png`, {
      animations: "disabled",
      caret: "hide",
      fullPage: false,
      scale: "css",
    });
  });
}
