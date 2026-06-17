"""pokecli — small CLI client for the poke-battles API.

Usage:
    pokecli health
    pokecli teams list
    pokecli teams add "My team" --paste @team.txt
    pokecli teams show 1
    pokecli battles create random random
    pokecli battles show battle-12345
    pokecli battles watch battle-12345
    pokecli sims run round-robin --team 1 --models random,random,random --n 20
    pokecli sims show sim-1
    pokecli leaderboard

Env:
    POKECLI_API  — base URL (default http://127.0.0.1:8000)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

DEFAULT_API = "http://127.0.0.1:8000"


def _api() -> str:
    return os.environ.get("POKECLI_API", DEFAULT_API)


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=_api(), timeout=timeout)


def cmd_health(_args: argparse.Namespace) -> int:
    with _client(timeout=5.0) as c:
        r = c.get("/health")
        r.raise_for_status()
        _print(r.json())
    return 0


def cmd_teams_list(args: argparse.Namespace) -> int:
    with _client() as c:
        r = c.get("/teams", params={"owner_id": args.owner} if args.owner else None)
        r.raise_for_status()
        teams = r.json()
        if args.json:
            _print(teams)
        else:
            for t in teams:
                print(
                    f"#{t['id']:>3}  {t['name']:<32}  format={t['format'] or '-':<22}  mons={t['pokemon_count']}"
                )
    return 0


def cmd_teams_add(args: argparse.Namespace) -> int:
    if args.paste.startswith("@"):
        with open(args.paste[1:], encoding="utf-8") as f:
            paste = f.read()
    else:
        paste = args.paste
    payload = {"name": args.name, "paste": paste, "format": args.format, "is_public": args.public}
    with _client() as c:
        r = c.post(f"/teams?owner_id={args.owner}", json=payload)
        r.raise_for_status()
        _print(r.json())
    return 0


def cmd_teams_show(args: argparse.Namespace) -> int:
    with _client() as c:
        r = c.get(f"/teams/{args.team_id}")
        r.raise_for_status()
        _print(r.json())
    return 0


def cmd_teams_delete(args: argparse.Namespace) -> int:
    with _client() as c:
        r = c.delete(f"/teams/{args.team_id}")
        r.raise_for_status()
    print(f"Deleted team {args.team_id}")
    return 0


def cmd_battles_create(args: argparse.Namespace) -> int:
    body = {
        "format": args.format,
        "player1": {"model_name": args.model1, "username": args.user1 or f"p1-{int(time.time())}"},
        "player2": {"model_name": args.model2, "username": args.user2 or f"p2-{int(time.time())}"},
    }
    if args.team1:
        body["team1_id"] = args.team1
    if args.team2:
        body["team2_id"] = args.team2
    with _client() as c:
        r = c.post("/battles", json=body)
        r.raise_for_status()
        data = r.json()
        _print(data)
    if not args.no_watch and data.get("id"):
        return cmd_battles_show(
            argparse.Namespace(
                battle_id=data["id"],
                wait=True,
                json=True,
                timeout=300.0,
            )
        )
    return 0


def cmd_battles_show(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.timeout
    with _client() as c:
        while True:
            r = c.get(f"/battles/{args.battle_id}")
            r.raise_for_status()
            data = r.json()
            if data.get("status") in {"finished", "done", "failed"} or not args.wait:
                if args.json:
                    _print(data)
                else:
                    print(
                        f"battle {data['id']}  status={data['status']}  "
                        f"turns={data.get('turns')}  winner={data.get('winner')}  "
                        f"duration={data.get('duration_s', 0):.1f}s"
                    )
                return 0 if data.get("status") == "finished" else 1
            if time.monotonic() > deadline:
                print("timeout")
                return 2
            time.sleep(2)


def cmd_battles_watch(args: argparse.Namespace) -> int:
    try:
        import websockets
    except ImportError:
        print("websockets not installed", file=sys.stderr)
        return 2
    url = _api().replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{url}/ws/battles/{args.battle_id}"

    async def run() -> None:
        async with websockets.connect(ws_url) as ws:
            print(f"connected to {ws_url}", file=sys.stderr)
            while True:
                msg = await ws.recv()
                if msg == "pong":
                    continue
                try:
                    obj = json.loads(msg)
                    print(json.dumps(obj, default=str))
                except json.JSONDecodeError:
                    print(msg)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 0
    return 0


def cmd_sims_run(args: argparse.Namespace) -> int:
    body = {
        "mode": args.mode,
        "models": [m.strip() for m in args.models.split(",") if m.strip()],
        "n_battles": args.n,
    }
    if args.team_a:
        body["team_a_id"] = args.team_a
    if args.team_b:
        body["team_b_id"] = args.team_b
    with _client(timeout=10.0) as c:
        r = c.post("/simulations", json=body)
        r.raise_for_status()
        _print(r.json())
    return 0


def cmd_sims_show(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.timeout
    with _client() as c:
        while True:
            r = c.get(f"/simulations/{args.sim_id}")
            r.raise_for_status()
            data = r.json()
            if data.get("status") in {"finished", "done", "failed"} or not args.wait:
                _print(data)
                return 0 if data.get("status") == "finished" else 1
            if time.monotonic() > deadline:
                print("timeout")
                return 2
            time.sleep(3)


def cmd_leaderboard(args: argparse.Namespace) -> int:
    with _client() as c:
        r = c.get("/leaderboard", params={"format": args.format, "limit": args.limit})
        r.raise_for_status()
        rows = r.json()
        if args.json:
            _print(rows)
        else:
            for r_ in rows:
                print(
                    f"{r_['subject']:<32}  {r_['format']:<22}  "
                    f"rating={r_['rating']:.0f}  rd={r_['rd']:.0f}  games={r_['games']}"
                )
    return 0


def cmd_replays_get(args: argparse.Namespace) -> int:
    with _client() as c:
        r = c.get(f"/replays/{args.battle_id}")
        r.raise_for_status()
        _print(r.json())
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    r = httpx.get(f"{_api()}/{args.path}", timeout=10.0)
    _print(r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    return r.status_code // 100


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pokecli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--api", help=f"Base URL (default {_api()})", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="API health check").set_defaults(func=cmd_health)

    teams = sub.add_parser("teams", help="Manage teams")
    teams_sub = teams.add_subparsers(dest="teams_cmd", required=True)
    lst = teams_sub.add_parser("list", help="List teams")
    lst.add_argument("--owner", help="Filter by owner id")
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=cmd_teams_list)
    add = teams_sub.add_parser("add", help="Add a team from a Showdown paste")
    add.add_argument("name")
    add.add_argument("--paste", required=True, help="Paste string or @file")
    add.add_argument("--owner", default="default", help="Owner user id")
    add.add_argument("--format", default=None)
    add.add_argument("--public", action="store_true")
    add.set_defaults(func=cmd_teams_add)
    show = teams_sub.add_parser("show", help="Show a team")
    show.add_argument("team_id", type=int)
    show.set_defaults(func=cmd_teams_show)
    delete = teams_sub.add_parser("delete", help="Delete a team")
    delete.add_argument("team_id", type=int)
    delete.set_defaults(func=cmd_teams_delete)

    battles = sub.add_parser("battles", help="Run + watch battles")
    battles_sub = battles.add_subparsers(dest="battles_cmd", required=True)
    bc = battles_sub.add_parser("create", help="Queue a battle")
    bc.add_argument("model1")
    bc.add_argument("model2")
    bc.add_argument("--format", default="gen9randombattle")
    bc.add_argument("--user1")
    bc.add_argument("--user2")
    bc.add_argument("--team1", type=int)
    bc.add_argument("--team2", type=int)
    bc.add_argument("--no-watch", action="store_true")
    bc.set_defaults(func=cmd_battles_create)
    bs = battles_sub.add_parser("show", help="Get battle status (polls if --wait)")
    bs.add_argument("battle_id")
    bs.add_argument("--wait", action="store_true", help="Poll until finished")
    bs.add_argument("--timeout", type=float, default=300.0)
    bs.add_argument("--json", action="store_true")
    bs.set_defaults(func=cmd_battles_show)
    bw = battles_sub.add_parser("watch", help="Stream live WS events")
    bw.add_argument("battle_id")
    bw.set_defaults(func=cmd_battles_watch)

    sims = sub.add_parser("sims", help="Run + watch simulations")
    sims_sub = sims.add_subparsers(dest="sims_cmd", required=True)
    sr = sims_sub.add_parser("run", help="Queue a simulation")
    sr.add_argument("mode", choices=["round_robin", "team_vs_team"])
    sr.add_argument("--models", default="random,random")
    sr.add_argument("--team-a", type=int)
    sr.add_argument("--team-b", type=int)
    sr.add_argument("--n", type=int, default=20)
    sr.set_defaults(func=cmd_sims_run)
    ss = sims_sub.add_parser("show", help="Get sim status (polls if --wait)")
    ss.add_argument("sim_id")
    ss.add_argument("--wait", action="store_true")
    ss.add_argument("--timeout", type=float, default=900.0)
    ss.set_defaults(func=cmd_sims_show)

    lb = sub.add_parser("leaderboard", help="Top ratings")
    lb.add_argument("--format", default="gen9randombattle")
    lb.add_argument("--limit", type=int, default=25)
    lb.add_argument("--json", action="store_true")
    lb.set_defaults(func=cmd_leaderboard)

    rp = sub.add_parser("replay", help="Get a battle replay")
    rp.add_argument("battle_id")
    rp.set_defaults(func=cmd_replays_get)

    raw = sub.add_parser("api", help="Raw GET against the API")
    raw.add_argument("path")
    raw.set_defaults(func=cmd_api)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.api:
        os.environ["POKECLI_API"] = args.api
    try:
        return args.func(args)
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        return exc.response.status_code
    except httpx.RequestError as exc:
        print(f"connection error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
