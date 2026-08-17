import { setWorldConstructor, World, IWorldOptions } from "@cucumber/cucumber";
import { Browser, Page } from "playwright";

// Single shared bound for every wait/navigation in this suite (resolves the
// "no canonical timeout" gap flagged by /speckit-analyze) — every step file
// imports this instead of inventing its own value.
export const DEFAULT_TIMEOUT_MS = 10_000;

export class CustomWorld extends World {
  browser!: Browser;
  page!: Page;
  baseUrl: string;

  constructor(options: IWorldOptions) {
    super(options);
    this.baseUrl = process.env.BASE_URL || "http://127.0.0.1:5051";
  }
}

setWorldConstructor(CustomWorld);
