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
