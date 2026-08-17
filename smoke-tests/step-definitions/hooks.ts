import { Before, After, setDefaultTimeout } from "@cucumber/cucumber";
import { chromium } from "playwright";
import { CustomWorld, DEFAULT_TIMEOUT_MS } from "./world";

// Cucumber's own default per-step timeout (5s) is shorter than
// DEFAULT_TIMEOUT_MS (10s) — without raising it here, Cucumber would kill a
// step before a Playwright wait inside it ever gets to time out on its own.
setDefaultTimeout(DEFAULT_TIMEOUT_MS + 5_000);

Before(async function (this: CustomWorld) {
  const headed = process.env.HEADED === "1";
  this.browser = await chromium.launch({
    headless: !headed,
    // Only slow down when watching headed — no reason to add latency to a
    // normal (headless) run.
    slowMo: headed ? 300 : 0,
  });
  this.page = await this.browser.newPage();
});

After(async function (this: CustomWorld) {
  await this.page?.close();
  await this.browser?.close();
});
