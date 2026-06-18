# Frontend, Auth, And Deployment Completion TODO

This checklist tracks the work to turn the prototype `web/` app into a production-capable web UI deployed on OCI. Keep this file updated as implementation progresses.

Legend: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked or deferred with reason.

## 0. Branching And Delivery

- [x] Create feature branch `feat/free-auth-rich-web-ui` in `poke-battles`.
- [ ] Commit regularly after coherent, verified slices.
- [ ] Push branch to `origin`.
- [ ] Create GitHub PR for `poke-battles` branch.
- [ ] If OCI infra changes are needed, create a separate branch/PR in `oci-infra` and avoid mixing app code with infra code.

## 1. Free Authentication Strategy

- [x] Decide against Clerk/Supabase because the app must stay free all the way.
- [x] Select direct FastAPI OAuth with Google/GitHub providers and server-side sessions.
- [ ] Add backend auth settings for OAuth client IDs/secrets, redirect base URL, session cookie, and session secret.
- [ ] Add `UserSession` persistence model for HTTP-only cookie sessions.
- [ ] Add auth service helpers for OAuth state, session token hashing, current user lookup, and logout.
- [ ] Add GitHub OAuth login/callback flow.
- [ ] Add Google OAuth login/callback flow.
- [ ] Add `GET /auth/me` and `POST /auth/logout` endpoints.
- [ ] Upsert `User` rows from OAuth profile data.
- [ ] Protect owner-scoped and resource-creating endpoints.
- [ ] Add API tests for anonymous, logged-in, logout, and protected route behavior.

## 2. Backend API Contract Fixes

- [ ] Replace `POST /teams?owner_id=...` with authenticated team creation using current user ID.
- [ ] Keep team listing scoped to current user by default; decide whether public teams need a separate endpoint.
- [ ] Add owner checks for team delete.
- [ ] Add `GET /models` backed by `models.yaml`, returning safe metadata only.
- [ ] Add `GET /formats` backed by `pokecore.formats`.
- [ ] Add `GET /battles` for dashboard/history.
- [ ] Add `GET /simulations` for dashboard/history.
- [ ] Fix battle IDs to use collision-safe UUIDs.
- [ ] Persist `running`, `failed`, `started_at`, `finished_at`, and `duration_s` accurately.
- [ ] Store replay summary metadata on completion.
- [ ] Expose raw replay log safely if needed by the UI.
- [ ] Validate simulation mode-specific requirements.
- [ ] Add tests for list/meta endpoints and lifecycle fields.

## 3. Backend Battle/Event Quality

- [ ] Enrich event parsing with structured `side`, `slot`, `pokemon`, `species_id`, `hp_percent`, and `status` where available.
- [ ] Keep raw Showdown protocol available for debugging.
- [ ] Ensure live WebSocket subscribers receive useful JSON events.
- [ ] Add replay support for structured events.
- [ ] Decide whether custom teams are MVP; if yes, wire `team1_id`/`team2_id` into actual battle execution.
- [ ] Decide whether simulations require custom team execution for MVP; if yes, wire `team_a_id`/`team_b_id` into execution.

## 4. Frontend Foundation

- [ ] Configure app base path for production under `/poke-battles/`.
- [ ] Configure API base as `/poke-battles/api` in production and `/api` in local dev.
- [ ] Configure WebSocket base as `/poke-battles/ws` in production and `/ws` in local dev.
- [ ] Fix Vite dev proxy to strip `/api` like production.
- [ ] Replace `window.location.href` route changes with React Router navigation.
- [ ] Replace hardcoded raw anchors with `Link`/`NavLink`.
- [ ] Add robust API client: empty body handling, typed errors, auth awareness, query helpers.
- [ ] Add shared UI primitives: buttons, cards, badges, text inputs, selects, tables, empty states, errors, loading states.
- [ ] Add responsive layout/navigation.
- [ ] Add route-level 404.
- [ ] Add accessibility basics: labels, focus states, aria-live for status/errors, table scopes.

## 5. Frontend Authentication UI

- [ ] Add sign-in page with GitHub and Google buttons.
- [ ] Add authenticated shell with user avatar/name and logout.
- [ ] Add unauthenticated shell for public pages.
- [ ] Fetch `GET /auth/me` on app boot.
- [ ] Redirect protected actions to sign-in.
- [ ] Show auth error states clearly.

## 6. Frontend Pages

- [ ] Dashboard: remove accidental battle creation side effect.
- [ ] Dashboard: show health, recent battles, recent simulations, team count, and leaderboard preview.
- [ ] Teams: create, list, preview parsed paste, delete with confirmation, handle auth ownership.
- [ ] Battle create: model select, format select, optional team select, validated usernames.
- [ ] Battle detail: polling cleanup, WebSocket reconnect/close/error states, replay link.
- [ ] Simulations: mode-specific forms, model multiselect, team selectors where supported, result tables.
- [ ] Leaderboard: format selector, loading/error/empty states, rating formatting.
- [ ] Replays: lookup by ID, event timeline, raw log tab if backend exposes raw log.

## 7. Rich Battle Viewer

- [ ] Use a custom first-party spectator viewer as the main UX.
- [ ] Keep Showdown client as fallback/debug view, not as the only UI.
- [ ] Render battlefield, player/model panels, active Pokémon slots, HP bars, status badges, turn banner, and event narration.
- [ ] Use Showdown sprite assets or URLs when available; do not create/maintain a custom sprite database.
- [ ] Gracefully fall back to initials/type badges when sprite URL cannot be resolved.
- [ ] Reuse viewer for live battles and replays.

## 8. Deployment And CI

- [ ] Add frontend build to CI: `npm ci` and `npm run build` in `web/`.
- [ ] Update Docker build workflow to build/push `poke-battles-web` for `linux/arm64`.
- [ ] Ensure API Docker image includes `models.yaml`.
- [ ] Avoid multiple uvicorn workers until queue/WebSocket state is externalized.
- [ ] Keep Postgres URL sync-compatible with current SQLAlchemy setup.
- [ ] Add OCI infra plan: `poke-battles-web` service and Caddy route for `/poke-battles/*` while preserving `/poke-battles/api/*`, `/poke-battles/ws/*`, and `/poke-battles/health`.
- [ ] Account for existing uncommitted OCI infra changes before editing that repo.

## 9. Verification

- [ ] Run Python lint/typecheck/tests or document failures.
- [ ] Run frontend TypeScript build.
- [ ] Run Docker build smoke checks where feasible.
- [ ] Manually verify local API health, auth stubs/config behavior, dashboard load, team flow, battle create/detail, replay view.
- [ ] Update this checklist before final PR.
