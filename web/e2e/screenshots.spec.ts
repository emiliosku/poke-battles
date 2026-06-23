import { test, expect, type Page, type Route } from "@playwright/test";
import path from "node:path";
import {
  USER,
  FORMATS,
  MODELS,
  TEAMS,
  LEADERBOARD,
  HEALTH,
  BATTLE_DOUBLES_FINISHED,
  BATTLE_SINGLES_RUNNING,
  BATTLE_DOUBLES_EVENTS,
  REPLAY,
  PRACTICE_ACTION,
  SIMULATIONS,
  BATTLES_HISTORY,
} from "./fixtures";

const SHOTS = process.env.SHOT_DIR || "/tmp/opencode/shots";
const DEMO_BATTLE_ID = BATTLE_DOUBLES_FINISHED.id;
const LIVE_BATTLE_ID = BATTLE_SINGLES_RUNNING.id;
const PRACTICE_ID = "practice-live-2026-03-09-zzz";

async function mockApi(page: Page, opts: { signedIn: boolean }) {
  // Single catch-all: dispatch by URL path. Avoids Playwright route-pattern
  // ordering pitfalls (e.g. /api/battles/** greedily eating /api/practice/...).
  await page.route(/\/api\/.*/, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    const json = (status: number, body: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    // Auth
    if (path === "/api/auth/me") {
      return json(200, { authenticated: opts.signedIn, user: opts.signedIn ? USER : null });
    }
    if (path === "/api/auth/providers") {
      return json(200, { github: true, google: false });
    }

    // Meta
    if (path === "/api/health") return json(200, HEALTH);
    if (path === "/api/formats") return json(200, FORMATS);
    if (path === "/api/models") return json(200, MODELS);
    if (path.startsWith("/api/leaderboard")) return json(200, LEADERBOARD);

    // Teams
    if (path === "/api/teams" && method === "GET") return json(200, TEAMS);
    if (path === "/api/teams" && method === "POST") return json(201, TEAMS[0]);

    // Battles
    const battleById =
      path === `/api/battles/${DEMO_BATTLE_ID}` ? BATTLE_DOUBLES_FINISHED
      : path === `/api/battles/${LIVE_BATTLE_ID}` ? BATTLE_SINGLES_RUNNING
      : path === `/api/battles/${PRACTICE_ID}` ? BATTLE_SINGLES_RUNNING
      : null;
    if (battleById) return json(200, battleById);
    if (path === "/api/battles" && method === "POST") return json(201, BATTLE_DOUBLES_FINISHED);
    if (path === "/api/battles" && method === "GET") return json(200, BATTLES_HISTORY);

    // Practice
    if (path === `/api/practice/battles/${PRACTICE_ID}/action`) {
      return json(200, { action: PRACTICE_ACTION });
    }
    if (path === "/api/practice/battles" && method === "POST") return json(201, BATTLE_SINGLES_RUNNING);

    // Simulations
    if (path === "/api/simulations" && method === "GET") return json(200, SIMULATIONS);
    if (path === "/api/simulations" && method === "POST") return json(201, SIMULATIONS[0]);
    if (path.startsWith("/api/simulations/")) return json(200, SIMULATIONS[0]);

    // Replays
    if (path === `/api/replays/${DEMO_BATTLE_ID}`) return json(200, REPLAY);
    if (path === `/api/replays/${PRACTICE_ID}`) return json(200, REPLAY);

    // Default: 200 with empty object so the page doesn't crash, and log it.
    // eslint-disable-next-line no-console
    console.warn("unmocked api path", method, path);
    return json(200, {});
  });
}

async function settleSprites(page: Page, timeoutMs = 6000) {
  // Wait until every pokemon-sprite <img> has finished loading (success or
  // hard failure). "Loading" is not settled — naturalWidth is 0 and the
  // browser hasn't fired load/error yet. The fallback chain may swap the
  // src a few times, so we re-check every 200ms.
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const settled = await page.evaluate(() => {
      const imgs = Array.from(document.images).filter((img) =>
        img.classList.contains("pokemon-sprite"),
      );
      if (imgs.length === 0) return true;
      return imgs.every((img) => img.complete);
    });
    if (settled) break;
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(400);
}

async function shot(page: Page, name: string) {
  const out = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: out, fullPage: true });
  return out;
}

test.beforeAll(() => {
  // No-op; mkdir handled by caller.
});

test.describe("poke-battles UI: every screen", () => {
  test("signed-out routes", async ({ page }) => {
    await mockApi(page, { signedIn: false });

    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await shot(page, "01-dashboard-signed-out");

    await page.goto("/signin");
    await page.waitForLoadState("networkidle");
    await shot(page, "02-signin");

    await page.goto("/teams");
    await page.waitForLoadState("networkidle");
    await shot(page, "03-teams-signed-out");

    await page.goto("/battle");
    await page.waitForLoadState("networkidle");
    await shot(page, "04-battle-signed-out");

    await page.goto("/practice");
    await page.waitForLoadState("networkidle");
    await shot(page, "05-practice-signed-out");

    await page.goto("/simulations");
    await page.waitForLoadState("networkidle");
    await shot(page, "06-simulations-signed-out");

    await page.goto("/leaderboard");
    await page.waitForLoadState("networkidle");
    await shot(page, "07-leaderboard");

    await page.goto("/replays");
    await page.waitForLoadState("networkidle");
    await shot(page, "08-replays-empty");

    await page.goto("/this-does-not-exist");
    await page.waitForLoadState("networkidle");
    await shot(page, "09-not-found");
  });

  test("signed-in dashboard", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await shot(page, "10-dashboard-signed-in");
  });

  test("signed-in teams", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/teams");
    await page.waitForLoadState("networkidle");
    await shot(page, "11-teams-signed-in");
  });

  test("signed-in battle matchmaker", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/battle");
    await page.waitForLoadState("networkidle");
    await shot(page, "12-battle-matchmaker");
  });

  test("signed-in practice matchmaker", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/practice");
    await page.waitForLoadState("networkidle");
    await shot(page, "13-practice-matchmaker");
  });

  test("signed-in simulations", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/simulations");
    await page.waitForLoadState("networkidle");
    await shot(page, "14-simulations-signed-in");
  });

  test("live battle view (sprite + attack focus)", async ({ page }) => {
    await mockApi(page, { signedIn: true });

    // Stub the websocket so the page doesn't try to open one
    // (it would fail anyway against a missing backend; we want deterministic
    // state for the screenshot).
    await page.addInitScript(() => {
      const RealWS = window.WebSocket;
      // @ts-expect-error: monkey-patch for tests
      window.WebSocket = function (url: string) {
        const fake: any = {
          url,
          readyState: 1,
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
          close() {
            if (this.onclose) this.onclose({} as CloseEvent);
          },
        };
        setTimeout(() => fake.onopen && fake.onopen({} as Event), 0);
        return fake;
      };
      // Carry over constants
      (window.WebSocket as any).CONNECTING = 0;
      (window.WebSocket as any).OPEN = 1;
      (window.WebSocket as any).CLOSING = 2;
      (window.WebSocket as any).CLOSED = 3;
      void RealWS;
    });

    // Wait for the replays request BEFORE navigation so we don't miss it.
    const replaysResp = page.waitForResponse(
      (r) => r.url().includes(`/api/replays/${DEMO_BATTLE_ID}`),
      { timeout: 15_000 },
    );
    await page.goto(`/battle/${DEMO_BATTLE_ID}`);
    await replaysResp;
    // The sprite fallback chain makes up to 3 cross-origin requests per mon;
    // on a cold browser context the first connection pays a TLS/setup tax.
    await settleSprites(page, 15_000);
    await shot(page, "15-battle-view-doubles");
  });

  test("replay page (loaded)", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/replays");
    await page.waitForLoadState("networkidle");
    const replaysResp = page.waitForResponse(
      (r) => r.url().includes(`/api/replays/${DEMO_BATTLE_ID}`),
      { timeout: 15_000 },
    );
    // Type the battle id and load
    const input = page.locator('input[placeholder="Battle ID"]');
    await input.fill(DEMO_BATTLE_ID);
    await page.getByRole("button", { name: /Load replay/i }).click();
    await replaysResp;
    await settleSprites(page, 4000);
    await shot(page, "16-replay-loaded");
  });

  test("practice battle view (action panel focus)", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.addInitScript(() => {
      const RealWS = window.WebSocket;
      // @ts-expect-error: monkey-patch for tests
      window.WebSocket = function (url: string) {
        const fake: any = {
          url,
          readyState: 1,
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
          close() {
            if (this.onclose) this.onclose({} as CloseEvent);
          },
        };
        setTimeout(() => fake.onopen && fake.onopen({} as Event), 0);
        return fake;
      };
      void RealWS;
    });

    await page.goto(`/practice/${PRACTICE_ID}`);
    // The page polls every 3s, so networkidle never resolves. Just wait for
    // the action buttons to appear (we know the mock returns them).
    await expect(page.getByRole("button", { name: /Thunderbolt/i })).toBeVisible();
    await settleSprites(page, 3000);
    await shot(page, "17-practice-action-panel");
  });

  test("practice battle view (mobile viewport)", async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 412, height: 915 },
      deviceScaleFactor: 2.625,
      isMobile: true,
      hasTouch: true,
    });
    const page = await ctx.newPage();
    await mockApi(page, { signedIn: true });
    await page.addInitScript(() => {
      const RealWS = window.WebSocket;
      // @ts-expect-error: monkey-patch for tests
      window.WebSocket = function (url: string) {
        const fake: any = { url, readyState: 1, onopen: null, onclose: null, onerror: null, onmessage: null, close() {} };
        setTimeout(() => fake.onopen && fake.onopen({} as Event), 0);
        return fake;
      };
      void RealWS;
    });
    await page.goto(`/practice/${PRACTICE_ID}`);
    await expect(page.getByRole("button", { name: /Thunderbolt/i })).toBeVisible();
    await settleSprites(page, 3000);
    await shot(page, "18-practice-action-mobile");
    await ctx.close();
  });

  test("battle view (mobile viewport)", async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 412, height: 915 },
      deviceScaleFactor: 2.625,
      isMobile: true,
      hasTouch: true,
    });
    const page = await ctx.newPage();
    await mockApi(page, { signedIn: true });
    await page.addInitScript(() => {
      const RealWS = window.WebSocket;
      // @ts-expect-error: monkey-patch for tests
      window.WebSocket = function (url: string) {
        const fake: any = { url, readyState: 1, onopen: null, onclose: null, onerror: null, onmessage: null, close() {} };
        setTimeout(() => fake.onopen && fake.onopen({} as Event), 0);
        return fake;
      };
      void RealWS;
    });
    const replaysResp = page.waitForResponse(
      (r) => r.url().includes(`/api/replays/${DEMO_BATTLE_ID}`),
      { timeout: 15_000 },
    );
    await page.goto(`/battle/${DEMO_BATTLE_ID}`);
    await replaysResp;
    await settleSprites(page, 4000);
    await shot(page, "19-battle-view-mobile");
    await ctx.close();
  });
});
