# Agent Instructions — poke-battles

LLM-powered Pokémon Showdown agents. Monorepo with 4 Python packages
(`pokecore`, `pokeengine`, `pokeellm`, `pokeapi`), a CLI
(`pokecli/`), and a Vite/React web UI (`web/`). Deployed via
`~/src/oci-infra` — see that repo's `AGENTS.md` for the deploy stack.

## Layout

| Path | Purpose |
|---|---|
| `packages/core/src/pokecore/` | Type chart, paste parser, formats, Glicko-2 |
| `packages/engine/src/pokeengine/` | poke-env wrapper, Showdown protocol, runner |
| `packages/llm/src/pokellm/` | LLM agent, prompts, tools, memory |
| `packages/api/src/pokeapi/` | FastAPI + SQLAlchemy + WS + orchestrator |
| `web/src/` | Vite/React UI |
| `web/Dockerfile` | nginx-served static bundle, baked with `VITE_ENABLE_DEBUG=true` |
| `packages/api/Dockerfile` | Multi-stage: clones Showdown, runs `node build`, bakes the dex into the image |
| `showdown/Dockerfile` | Smogon upstream, built `linux/amd64` under QEMU (SIGILLs are possible — see comment at `build.yml:160`) |
| `showdown-client/Dockerfile` | Static-served Showdown web client |
| `Makefile` | `make ci` runs the full local validation suite |

## Local validation

```sh
make ci            # ruff lint + mypy --strict + pytest with coverage
make test          # pytest only
make lint          # ruff check
make format        # ruff format (apply changes)
make typecheck     # mypy --strict
```

The `validate` job in `.github/workflows/build.yml` runs the same
suite and gates all builds. A single failing test blocks the deploy.

## Checking Build Status

**Use the `gh` CLI to inspect pipeline runs and job logs.** It
authenticates with the repo's `GITHUB_TOKEN`, which sidesteps the 60
req/hr unauthenticated rate limit on `api.github.com` and is the only
way to fetch job logs (unauthenticated requests return 403). Polling
`curl https://api.github.com/...` in a loop burns the quota in a couple
of minutes — each `runs`/`jobs` call plus any nested `Link`-header
follow-up costs 1–3 requests — and then you're locked out for an hour.

```sh
gh run list --workflow build.yml --limit 5
gh run view <run-id> --json status,conclusion,headSha,createdAt
gh run watch <run-id>                # blocks until the run completes
gh api repos/:owner/:repo/actions/runs/<run-id>/jobs --jq '.jobs[] | "\(.name) \(.conclusion)"'
gh run view <run-id> --log-failed    # only the failing steps
```

If `gh` is unavailable, `curl` with a `GITHUB_TOKEN` set in the
environment (`curl -H "Authorization: token $GITHUB_TOKEN" ...`) is
the next-best option. Save the token in `~/.config/gh/hosts.yml` or
export it before long polling loops.

## Notable gotchas

- **`packages/engine/server/` is gitignored.** It contains the
  Showdown server code and its `dist/data/*.js` build output
  (including `pokedex.js`). The API image bakes the dex via the
  `showdown-data` build stage in `packages/api/Dockerfile` — don't
  try to `COPY` it from the build context, it isn't there. If
  `pokecore.pokedex.load_pokedex()` returns `()` at runtime, the dex
  is missing from the image.
- **`ghcr.io` is private** even though the repo is public. The
  manifest/tags API returns 401 without auth. The `gh` CLI is
  authenticated; bare `curl` is not.
- **GHCR edge cache can briefly serve a stale `:latest` digest** right
  after a push. The deploy's `docker compose pull` can miss the new
  image in this window; if `docker images` on the server shows a
  digest that's older than the latest CI build, force-recreate:
  `ssh oci "cd ~/oci-infra && docker compose pull <svc> && docker compose up -d --force-recreate --no-deps <svc>"`.
- **`index.html` is not content-hashed** and the web nginx serves it
  with no `Cache-Control`. After a web deploy, hard-reload (Ctrl/Cmd
  +Shift+R) to see the new bundle. The permanent fix is to add
  `Cache-Control: no-cache` to `index.html` in `web/nginx.conf`.

## RL training (`packages/rl`)

Train a MaskablePPO agent that plays Showdown via `poke-env`. The gym
env (`packages/rl/src/pokerl/env.py`) drives battles through a background
thread feeding an observation queue; the agent acts via `RLPlayer`.

```sh
uv run python -m pokerl.train \
  --timesteps 200000 --format gen9randombattle --opponent random \
  --save-dir models/rl/random-v2 --server-host localhost --server-port 8000
```

CLI flags: `--timesteps --format --opponent {random,heuristic,self-play}
--lr --batch-size --save-dir --server-host --server-port --net-arch
--verbose`. Internally it evaluates every 10k steps and saves a
checkpoint every 50k; the best eval model is written to `<save-dir>/best/best_model.zip`.

Measure a trained model's win rate against random play with
`~/diag_eval.py` (OCI): `uv run python ~/diag_eval.py --model
<zip> --episodes 60` (or `--random` for the random baseline).

### Reward signal (critical)

The terminal reward must come from `self._current_battle.won`, NOT a
hardcoded value. The original `step()` returned a constant `loss_reward`
on the `_battle_over` path, which silently trained the agent on a broken
−1.0 signal (it never learned). The fix (`env.py:_terminal_result`)
reads the true battle outcome and returns `±win_reward` with a `won` key
in the info dict. If training shows `ep_rew_mean` stuck near the
loss value or the agent never wins, check this first.

### OCI runbook

- Use the ssh key at `~/src/tests/ssh-key-2026-04-17.key`; server
  `ubuntu@143.47.38.215`; Showdown runs in Docker on host port 8000.
- `uv` lives at `~/.local/bin/uv` and the root-owned `.venv` requires
  `export PATH="$HOME/.local/bin:$PATH"` and `uv run` (a non-interactive
  shell won't find `uv`).
- Before launching training/eval, **kill any stale pokerl/diag
  processes** (see gotcha below) or the new run will fail to log in.

### Notable gotchas (RL)

- **Stale processes hijack the Showdown username.** Every env logs in as
  `RLAgent-0` / `Opponent-0`. If a previous training or `diag_eval` run
  didn't exit (SB3 + poke-env often hangs at shutdown instead of
  terminating), it keeps the name and the next run dies with
  `|nametaken|RLAgent-0|Someone is already using the name`, which then
  surfaces as the misleading `Event bound to a different event loop` /
  `Expected RLAgent-0 to be logged in` errors. This is NOT a code bug —
  `kill -9` the leftover `pokerl.train` / `diag_eval` PIDs first. A hung
  training process is harmless once the final checkpoint and
  `best_model.zip` are written; kill it to free the name.
- **`[Unavailable choice] Can't switch: The active Pokémon is trapped`**
  is a normal Showdown message (the agent tried a trapped switch) and is
  benign — the battle continues.
- **SB3 eval emits a `Monitor` wrapper UserWarning.** Cosmetic; wrap the
  eval env with `Monitor` if you want it gone.
- **Dead-connection watchdog (`env.py:_watchdog_loop`).** poke-env 0.15
  does NOT always raise when the Showdown websocket drops mid-battle — the
  battle coroutine just hangs and the env blocks forever in `reset()`/
  `step()`. The watchdog (`WATCHDOG_TIMEOUT=90s`) detects >90s without an
  observation while a battle is active, force-kills the players via
  `ps_client.stop_listening()`, and sets `_connection_dead` so the next
  `reset()` recreates them. If a training run freezes with no evals and a
  tail of `ConnectionClosedError` but no progress, it's this — the watchdog
  should now auto-recover; if it doesn't, the 90s threshold may need lowering.

### Curriculum wall: `SimpleHeuristicsPlayer` is too hard

The Random → Heuristic → Self-play curriculum **breaks at the heuristic
step**. Empirically (all runs, `gen9randombattle`, `RLPlayer`/MaskablePPO):

| Run | Trained vs | Eval vs heuristic | win_rate |
|---|---|---|---|
| `random-v2` | random | heuristic | 8.3% |
| `random-v3` | heuristic (from scratch) | heuristic | 3.3% |
| `random-v3-ft` | random→heuristic (old reward) | heuristic | 1.7% |
| `random-v3-ft2` | random→heuristic (dense reward `b124922`) | heuristic | 6.7% |

**Root cause:** vs a strong opponent the agent loses ~every battle, so the
terminal ±win_reward is a near-constant offset with no gradient. The dense
reward reshaping (`b124922`: HP ±0.2, KO/faint ±0.5, turn −0.01) DID give a
real training signal — `ep_rew_mean` climbed from −1.07 to −0.83 during
training — but it did NOT translate to winning at evaluation (still ~3-7%
vs heuristic, i.e. at the random-winning baseline's level). The agent learns
to *lose less* but cannot cross the tactical gap to actually beating
`SimpleHeuristicsPlayer`.

**What to try next if beating heuristic is the goal** (in rough order of
expected payoff):
1. **Self-play** — train vs frozen past checkpoints (`_LoadedPolicyOpponent`
   already supports a `.zip` opponent path). Opponents at the agent's own
   level provide a learnable win/loss gradient; this is the originally-planned
   next step and the most likely to break the wall.
2. **Denser / different shaping** — e.g. reward *net HP differential* change
   per turn even more strongly, or add a small shaping bonus specifically for
   good type matchups / switching into favorable matchups.
3. **Bigger net / longer horizon** — bump `--net-arch`, train 1M+ steps, or
   fix teams (`gen9ou`) so the agent learns real team-building rather than
   random-team variance.
4. **Accept the random-only baseline** — `random-v2` beats random 83% and is
   a perfectly good "randombot-beater"; heuristic is simply a different, much
   harder tier.

**Do NOT** sink more time into "fine-tune a random-winning policy vs
heuristic" — it plateaus at the base policy's heuristic strength (~8%).

### Self-play (implemented)

Self-play trains the agent against a **periodically-refreshed frozen snapshot
of its own policy**, giving a learnable win/loss gradient at the agent's own
skill level (vs heuristic the agent loses ~every battle, so there is no
gradient). The opponent snapshot is seeded from `--resume` and refreshed every
`--self-play-update-freq` steps by `SelfPlayCallback`, which swaps the model
**in place** on the existing `_LoadedPolicyOpponent` (no reconnection — see
`bd2ae5e`; recreating the player every battle bound its `logged_in` Event to a
stale asyncio loop and crashed).

```sh
# bootstrap from the random-winning base; self-play refreshes the opponent
uv run python -m pokerl.train \
  --timesteps 300000 --format gen9randombattle --opponent random \
  --resume models/rl/random-v2/best/best_model.zip \
  --self-play-snapshot models/rl/random-v3-sp/selfplay_opponent.zip \
  --self-play-update-freq 50000 \
  --save-dir models/rl/random-v3-sp --server-host localhost --server-port 8000
```

Observed: eval reward vs the frozen snapshot hovers around 0 (agent at parity
with its opponent — healthy co-evolution), and the swap fires correctly at
each update boundary. Throughput is ~10x lower than vs random/heuristic
because both sides run a torch `predict()` per turn; a 300k run takes several
hours. The real payoff is measured by evaluating the final `best_model.zip`
against `SimpleHeuristicsPlayer` (see `diag_eval.py --opponent heuristic`).

