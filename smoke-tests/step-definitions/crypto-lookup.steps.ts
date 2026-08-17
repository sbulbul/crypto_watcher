import { When, Then } from "@cucumber/cucumber";
import { CustomWorld, DEFAULT_TIMEOUT_MS } from "./world";

When(
  "I look up ticker {string}",
  async function (this: CustomWorld, ticker: string) {
    await this.page.getByLabel("Ticker symbol").fill(ticker);
    await this.page.getByRole("button", { name: "Look Up" }).click();
  }
);

Then(
  "I should see a result or a warning",
  async function (this: CustomWorld) {
    const result = this.page.locator("#resultState");
    const warning = this.page.locator("#warningState");

    // Promise.any (not .race): only fails if NEITHER container becomes
    // visible within the timeout — a warning appearing first is a legitimate
    // pass per the app's own constitution (a warning is correct behavior,
    // not a bug), and this must not race-reject just because one of the two
    // times out before the other resolves.
    await Promise.any([
      result.waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS }),
      warning.waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS }),
    ]);
  }
);
