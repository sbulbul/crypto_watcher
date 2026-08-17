import { When, Then } from "@cucumber/cucumber";
import { CustomWorld, DEFAULT_TIMEOUT_MS } from "./world";

// A small leftover scan limit (e.g. from a previous run) can make a scan
// complete in only a few seconds — comparable to Playwright's own
// browser-launch/navigation overhead, which raced and lost against the
// "scanning" text disappearing before this suite's own assertion checked
// for it. Explicitly setting the largest limit keeps the scan running long
// enough to be reliably observable regardless of leftover state.
When(
  "I set the scan limit to {string}",
  async function (this: CustomWorld, limit: string) {
    await this.page.getByLabel("Scan limit").fill(limit);
  }
);

When(
  "I click {string}",
  async function (this: CustomWorld, label: string) {
    await this.page.getByRole("button", { name: label }).click();
  }
);

// Verified via manual Playwright inspection: the progress panel's text
// content is dynamic (client JS rewrites it through "Preparing crypto
// universe" then "Scanning N of M" as polling progresses — see
// templates/index.html's renderProgress()), so asserting on a fixed string
// is unreliable. The panel gaining the "active" class is the stable signal
// that a scan is genuinely running, regardless of which phase it's in.
Then("I should see the scan in progress", async function (this: CustomWorld) {
  await this.page
    .locator("#progressPanel.active")
    .waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS });
});

// This scenario deliberately starts a real scan (research.md — checks
// "started," not "completed") — it runs in a server-side background thread
// independent of this browser session, so it would otherwise keep running
// well after the scenario ends. Stop it explicitly rather than leaving a
// long scan running unattended in the background.
When("I stop the scan", async function (this: CustomWorld) {
  await this.page.request.post(`${this.baseUrl}/stop_scan`);
});
