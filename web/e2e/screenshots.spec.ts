import { test, expect, type Page, type Route } from "@playwright/test";
import path from "node:path";
import {
  USER,
  FORMATS,
  MODELS,
  TEAMS,
  TEAM_PASTE,
  TEAM_PREVIEW,
  SPRITE_STATUS,
  LEADERBOARD,
  HEALTH,
  BATTLE_DOUBLES_FINISHED,
  BATTLE_SINGLES_RUNNING,
  BATTLE_DOUBLES_EVENTS,
  REPLAY,
  PRACTICE_ACTION,
  PRACTICE_ACTION_TEAM_PREVIEW,
  PRACTICE_ACTION_FORCED_SWITCH,
  SIMULATIONS,
  BATTLES_HISTORY,
} from "./fixtures";

const SHOTS = process.env.SHOT_DIR || "/tmp/opencode/shots";
const DEMO_BATTLE_ID = BATTLE_DOUBLES_FINISHED.id;
const LIVE_BATTLE_ID = BATTLE_SINGLES_RUNNING.id;
const PRACTICE_ID = "practice-live-2026-03-09-zzz";
const PRACTICE_TEAM_PREVIEW_ID = "practice-tp-2026-03-09-aaa";
const PRACTICE_FORCED_SWITCH_ID = "practice-fs-2026-03-09-bbb";

async function mockApi(page: Page, opts: { signedIn: boolean }) {
  // Single catch-all: dispatch by URL path. Avoids Playwright route-pattern
  // ordering pitfalls (e.g. /api/battles/** greedily eating /api/practice/...).
  await page.route(/\/api\/.*/, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    // Strip any base path (e.g. /poke-battles) so the same mock matches
    // both the dev server (no subpath) and a deployed site (Vite BASE_URL).
    const apiIdx = url.pathname.indexOf("/api/");
    const path = apiIdx >= 0 ? url.pathname.slice(apiIdx) : url.pathname;
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
    if (path === "/api/pokedex") return json(200, { count: 0, pokemon: [] });
    if (path === "/api/sprites/status") return json(200, SPRITE_STATUS);
    if (path.startsWith("/api/leaderboard")) return json(200, LEADERBOARD);

    // Teams
    if (path === "/api/teams" && method === "GET") return json(200, TEAMS);
    if (path === "/api/teams" && method === "POST") return json(201, TEAMS[0]);
    if (path === "/api/teams/preview" && method === "POST") return json(200, TEAM_PREVIEW);

    // Battles
    const battleById =
      path === `/api/battles/${DEMO_BATTLE_ID}` ? BATTLE_DOUBLES_FINISHED
      : path === `/api/battles/${LIVE_BATTLE_ID}` ? BATTLE_SINGLES_RUNNING
      : path === `/api/battles/${PRACTICE_ID}` ? BATTLE_SINGLES_RUNNING
      : path === `/api/battles/${PRACTICE_TEAM_PREVIEW_ID}` ? BATTLE_SINGLES_RUNNING
      : path === `/api/battles/${PRACTICE_FORCED_SWITCH_ID}` ? BATTLE_SINGLES_RUNNING
      : null;
    if (battleById) return json(200, battleById);
    if (path === "/api/battles" && method === "POST") return json(201, BATTLE_DOUBLES_FINISHED);
    if (path === "/api/battles" && method === "GET") return json(200, BATTLES_HISTORY);

    // Practice
    if (path === `/api/practice/battles/${PRACTICE_ID}/action`) {
      return json(200, { action: PRACTICE_ACTION });
    }
    if (path === `/api/practice/battles/${PRACTICE_TEAM_PREVIEW_ID}/action`) {
      return json(200, { action: PRACTICE_ACTION_TEAM_PREVIEW });
    }
    if (path === `/api/practice/battles/${PRACTICE_FORCED_SWITCH_ID}/action`) {
      return json(200, { action: PRACTICE_ACTION_FORCED_SWITCH });
    }
    if (path === "/api/practice/battles" && method === "POST") return json(201, BATTLE_SINGLES_RUNNING);

    // Simulations
    if (path === "/api/simulations" && method === "GET") return json(200, SIMULATIONS);
    if (path === "/api/simulations" && method === "POST") return json(201, SIMULATIONS[0]);
    if (path.startsWith("/api/simulations/")) return json(200, SIMULATIONS[0]);

    // Replays
    if (path === `/api/replays/${DEMO_BATTLE_ID}`) return json(200, REPLAY);
    if (path === `/api/replays/${PRACTICE_ID}`) return json(200, REPLAY);
    if (path === `/api/replays/${PRACTICE_TEAM_PREVIEW_ID}`) return json(200, REPLAY);
    if (path === `/api/replays/${PRACTICE_FORCED_SWITCH_ID}`) return json(200, REPLAY);

    // Default: 200 with empty object so the page doesn't crash, and log it.
    // eslint-disable-next-line no-console
    console.warn("unmocked api path", method, path);
    return json(200, {});
  });
}

async function settleSprites(page: Page, timeoutMs = 6000) {
  // Wait until every pokemon sprite (battle view + mon icon) has finished
  // loading (success or hard failure). "Loading" is not settled — the
  // browser hasn't fired load/error yet. The fallback chain may swap the
  // src a few times, so we re-check every 200ms.
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const settled = await page.evaluate(() => {
      const imgs = Array.from(document.images).filter(
        (img) => img.classList.contains("pokemon-sprite") || img.classList.contains("mon-icon-img"),
      );
      if (imgs.length === 0) return true;
      return imgs.every((img) => img.complete);
    });
    if (settled) break;
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(400);
}

async function stubWebSocket(page: Page) {
  await page.addInitScript(() => {
    const RealWS = window.WebSocket;
    // @ts-expect-error: monkey-patch for tests
    window.WebSocket = function (url: string) {
      const fake: any = {
        url, readyState: 1, onopen: null, onclose: null, onerror: null, onmessage: null,
        close() { if (this.onclose) this.onclose({} as CloseEvent); },
      };
      setTimeout(() => fake.onopen && fake.onopen({} as Event), 0);
      return fake;
    };
    void RealWS;
  });
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

  test("debug /sprites page is reachable when debug build is enabled", async ({ page }) => {
    // The CI web build sets VITE_ENABLE_DEBUG=true, so the /debug/sprites
    // route is baked into the bundle. This test guards against future
    // regressions that would silently ship a production build without
    // the dev tools.
    await mockApi(page, { signedIn: true });
    // Land on the dashboard first so the topbar is rendered before we
    // navigate into the debug page. (Without this the /debug/sprites
    // route mounts before useAuth resolves and the topbar is briefly
    // empty, so the link can't be asserted immediately.)
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Debug" })).toBeVisible();
    await page.getByRole("link", { name: "Debug" }).click();
    await page.waitForURL(/\/debug\/sprites$/);
    // Page must render the species rows for the mocked status payload.
    // The status fetch is async, so wait for the response to land
    // before asserting on the row markup.
    await page.waitForResponse(
      (r) => r.url().endsWith("/api/sprites/status") && r.status() === 200,
    );
    await expect(page.getByRole("heading", { name: "Sprite coverage" })).toBeVisible();
    // Each species row is an <article> with the name in a <strong>.
    // Assert each one renders so a missing row (e.g. a pokeapi bug)
    // is caught even if the heading is fine.
    const expectedSpecies = ["Hatterene", "Slowking-Galar", "Aerodactyl-Mega", "Maushold-Three"];
    for (const name of expectedSpecies) {
      const row = page.locator("article", { has: page.locator("strong", { hasText: name }) });
      await expect(row).toHaveCount(1);
    }
    await shot(page, "11-debug-sprites");
  });

  test("signed-in teams", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/teams");
    await page.waitForLoadState("networkidle");
    await shot(page, "11-teams-signed-in");
  });

  test("teams page — create expanded with paste preview", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/teams");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Create team" }).click();
    await page.locator('textarea').fill(TEAM_PASTE);
    await expect(page.getByTestId("paste-preview-list")).toBeVisible();
    // The preview kicks off 3 URL fetches per mon (gen5ani → ani → dex) on
    // Showdown's CDN; wait for them to settle so the screenshot doesn't
    // catch the orbs mid-load.
    await settleSprites(page, 15_000);
    await shot(page, "12-teams-create-with-preview");
  });

  test("teams page — team card expanded inline", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/teams");
    await page.waitForLoadState("networkidle");
    await page.locator(".team-card").first().click();
    await expect(page.locator(".team-card.expanded .paste-preview-list, .team-card.expanded [data-testid='paste-preview-list']").first()).toBeVisible();
    await settleSprites(page, 15_000);
    await shot(page, "13-teams-card-expanded");
  });

  test("signed-in battle matchmaker", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/battle");
    await page.waitForLoadState("networkidle");
    await shot(page, "14-battle-matchmaker");
  });

  test("signed-in practice matchmaker", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/practice");
    await page.waitForLoadState("networkidle");
    await shot(page, "15-practice-matchmaker");
  });

  test("signed-in simulations", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/simulations");
    await page.waitForLoadState("networkidle");
    await shot(page, "16-simulations-signed-in");
  });

  test("live battle view (sprite + attack focus)", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await stubWebSocket(page);

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
    await shot(page, "17-battle-view-doubles");
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
    await shot(page, "18-replay-loaded");
  });

  test("practice battle view (action panel focus)", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await stubWebSocket(page);

    await page.goto(`/practice/${PRACTICE_ID}`);
    // The intro overlay shows for ~2.2s, then the action card reveals.
    await expect(page.getByRole("button", { name: /Thunderbolt/i })).toBeVisible();
    await settleSprites(page, 4000);
    await shot(page, "19-practice-action-panel");
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
    await stubWebSocket(page);
    await page.goto(`/practice/${PRACTICE_ID}`);
    await expect(page.getByRole("button", { name: /Thunderbolt/i })).toBeVisible();
    await settleSprites(page, 4000);
    await shot(page, "20-practice-action-mobile");
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
    await stubWebSocket(page);
    const replaysResp = page.waitForResponse(
      (r) => r.url().includes(`/api/replays/${DEMO_BATTLE_ID}`),
      { timeout: 15_000 },
    );
    await page.goto(`/battle/${DEMO_BATTLE_ID}`);
    await replaysResp;
    await settleSprites(page, 4000);
    await shot(page, "21-battle-view-mobile");
    await ctx.close();
  });

  test("practice battle view — pre-battle intro", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await stubWebSocket(page);
    await page.goto(`/practice/${PRACTICE_ID}`);
    // Capture before the intro overlay (2.2s) lifts.
    await expect(page.getByTestId("battle-intro")).toBeVisible();
    await settleSprites(page, 1000);
    await shot(page, "22-practice-intro");
  });

  test("practice battle view — team preview phase", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await stubWebSocket(page);
    await page.goto(`/practice/${PRACTICE_TEAM_PREVIEW_ID}`);
    // The first switch option's name appears in the grid.
    await expect(page.getByRole("button", { name: /Incineroar/i })).toBeVisible();
    await settleSprites(page, 4000);
    await shot(page, "23-practice-team-preview");
  });

  test("practice battle view — forced switch phase", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await stubWebSocket(page);
    await page.goto(`/practice/${PRACTICE_FORCED_SWITCH_ID}`);
    // No move buttons — only switches.
    await expect(page.getByRole("button", { name: /Garchomp/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Thunderbolt/i })).toHaveCount(0);
    await settleSprites(page, 4000);
    await shot(page, "24-practice-forced-switch");
  });
});
