import { Given, Then } from "@cucumber/cucumber";
import { CustomWorld, DEFAULT_TIMEOUT_MS } from "./world";

// Every assertion in this suite uses Playwright's Locator.waitFor(), which
// throws (rather than resolving falsy) when the condition isn't met within
// the timeout — so a failed check always fails the scenario, never a silent
// false pass (resolves the G1 gap flagged by /speckit-analyze).

Given(
  "I am on the {string} page",
  async function (this: CustomWorld, path: string) {
    // A down app fails this navigation within DEFAULT_TIMEOUT_MS instead of
    // hanging on Playwright's much longer default timeout (FR-008).
    await this.page.goto(`${this.baseUrl}${path}`, {
      timeout: DEFAULT_TIMEOUT_MS,
    });
  }
);

Then(
  "I should see a heading {string}",
  async function (this: CustomWorld, name: string) {
    // exact: true — Playwright's accessible-name match is a substring match
    // by default, so a regression like "Crypto Hourly Watcherz" would still
    // satisfy a search for "Crypto Hourly Watcher" without it (found via
    // quickstart.md's own deliberate-regression check, SC-004).
    await this.page
      .getByRole("heading", { name, exact: true })
      .waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS });
  }
);
