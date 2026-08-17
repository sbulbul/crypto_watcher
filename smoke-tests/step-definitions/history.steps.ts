import { Then } from "@cucumber/cucumber";
import { CustomWorld, DEFAULT_TIMEOUT_MS } from "./world";

Then(
  "I should see the history list or the empty state",
  async function (this: CustomWorld) {
    const list = this.page.locator(".history-table");
    const emptyState = this.page.getByRole("heading", {
      name: "No saved scans yet",
    });

    // Same either/or reasoning as crypto-lookup.steps.ts: only fails if
    // neither the populated list nor the documented empty state appears.
    await Promise.any([
      list.waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS }),
      emptyState.waitFor({ state: "visible", timeout: DEFAULT_TIMEOUT_MS }),
    ]);
  }
);
