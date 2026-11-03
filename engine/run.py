"""Run one tournament from the command line.

    python -m engine.run --seed 7 --players random,lowest,liar,generous,random
    python -m engine.run --players anthropic/claude-haiku-5-5,deepseek/deepseek-chat,random,random,random

Each player is a bot name or a LiteLLM model id. Writes the event log, and for
LLM players a trace of every prompt and reply, to --log-dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from agents.bots import BOTS
from agents.llm import LLMAgent
from agents.ratelimit import RateLimiter
from engine.agent import Agent
from engine.events import EventLog
from engine.tournament import Tournament, TournamentConfig
from games.schedule import SCHEDULES
from games.show import MAIN_POOL
from games.suit_survival import HiddenPlayerSuits, SuitSurvival

SHOW_MAX_PLAYERS = max(g.max_players for g in MAIN_POOL)


def main(argv: list[str] | None = None) -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--players",
        default="random,lowest,liar,generous,random",
        help=f"comma-separated; bots: {', '.join(sorted(BOTS))}; anything else is a LiteLLM model id",
    )
    parser.add_argument(
        "--format",
        choices=["classic", "show", "suits", "hidden"],
        default=None,
        help="show: random games, prison matches, start with 1 Piece (default for 7 players); "
        "classic: the fixed 5- or 6-day schedule (default for 5 or 6 players); "
        "suits: one game of Suit Survival, last player standing wins; "
        "hidden: Suit Survival with a secret Hidden Player (Jack of Hearts rules)",
    )
    parser.add_argument("--communication", choices=["none", "public", "private"], default="private")
    parser.add_argument(
        "--memory",
        choices=["diary", "facts", "full"],
        default="diary",
        help="how players see earlier days: diary = key results + their own end-of-day diary "
        "(default); facts = key results only; full = every earlier message (the pilots)",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high"],
        default=None,
        help="for thinking models; 'none' turns reasoning off (default: the provider's default)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=None,
        help="max LLM calls per minute per model (seats using one model share it); e.g. 10 for free tiers",
    )
    parser.add_argument("--log-dir", default="runs")
    args = parser.parse_args(argv)

    names = args.players.split(",")
    fmt = args.format or ("classic" if len(names) in SCHEDULES else "show")
    if fmt == "suits" and len(names) < 2:
        parser.error("Suit Survival needs at least 2 players")
    if fmt == "hidden" and len(names) < 3:
        parser.error("Hidden Player needs at least 3 players")
    if fmt == "classic" and len(names) not in SCHEDULES:
        parser.error(f"the classic format needs {' or '.join(map(str, sorted(SCHEDULES)))} players")
    if fmt == "show" and not 3 <= len(names) <= SHOW_MAX_PLAYERS:
        parser.error(f"the show format needs 3 to {SHOW_MAX_PLAYERS} players")
    limiters: dict[str, RateLimiter] = {}

    def limiter(model: str) -> RateLimiter | None:
        if args.rpm is None:
            return None
        return limiters.setdefault(model, RateLimiter(args.rpm))

    agents: list[Agent] = [
        BOTS[n](seed=args.seed * 100 + i)
        if n in BOTS
        else LLMAgent(
            n,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
            limiter=limiter(n),
        )
        for i, n in enumerate(names)
    ]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = Path(args.log_dir)
    path = log_dir / f"{stamp}_seed{args.seed}.jsonl"
    config = (
        TournamentConfig(format="show", start_pieces=1, communication=args.communication, memory=args.memory)
        if fmt == "show"
        else TournamentConfig(communication=args.communication, memory=args.memory)
    )
    schedule = {"classic": SCHEDULES.get(len(agents)), "show": None, "suits": [SuitSurvival], "hidden": [HiddenPlayerSuits]}[fmt]
    with EventLog(path) as log:
        tournament = Tournament(
            agents, schedule,
            seed=args.seed, config=config, log=log,
            stop_file=stop_file_for(path),
        )
        result = asyncio.run(tournament.run())
        print_summary(log, result)
    print(f"\nLog: {path}")

    trace = sorted(
        (entry for a in agents if isinstance(a, LLMAgent) for entry in a.trace),
        key=lambda entry: entry["time"],
    )
    if trace:
        trace_path = log_dir / f"{stamp}_seed{args.seed}_trace.jsonl"
        with trace_path.open("w", encoding="utf-8") as f:
            for entry in trace:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Trace: {trace_path}")
    if result["aborted"]:
        raise SystemExit(1)


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Load API keys from the project's .env. Variables already set in the shell win."""
    load_dotenv(path, override=False)


def stop_file_for(log_path: Path) -> Path:
    """The file the viewer's Stop button creates for this run."""
    return log_path.with_suffix(".stop")


def print_summary(log: EventLog, result: dict) -> None:
    print("Seats:", ", ".join(f"{p} = {label}" for p, label in result["agents"].items()))
    for event in log.events:
        data = event["data"]
        if event["type"] == "day_start":
            print(f"\nDay {event['day']}: {data['game']}  pieces {data['pieces']}")
        elif event["type"] == "prison_start":
            print(f"  prison ({data['game']}): {', '.join(data['players'])}")
        elif event["type"] == "prison_result":
            print(f"  prison ranking: {data['ranking']}")
        elif event["type"] == "placement":
            print("  ranking:", data["ranking"])
            print("  rewards:", data["rewards"])
        elif event["type"] == "elimination":
            reason = f" - {data['reason']}" if data.get("reason") else ""
            print(f"  eliminated: {data['player']} ({data['pieces']} pieces){reason}")
        elif event["type"] == "transfer" and data["last_will"]:
            print(f"  last will: {event['actor']} -> {data['to']} ({data['pieces']})")
        elif event["type"] == "team_result":
            outcome = "reached" if data["success"] else "missed"
            print(f"  team goal {outcome}: {data['total']}/{data['goal']}, bonus +{data['bonus']} each")
        elif event["type"] == "life_bought":
            print(f"  {event['actor']} bought a life ({data['pieces']} pieces left)")
        elif event["type"] == "life_used":
            print(f"  {data['player']} used their life")
        elif event["type"] == "suit_result":
            outcome = f"out: {', '.join(data['wrong']) or 'nobody'}" + (" (everyone)" if data["everyone_out"] else "")
            print(f"  round {data['round']}: {outcome}")
        elif event["type"] == "hidden_round":
            print(f"  round {data['round']}: out: {', '.join(data['eliminated']) or 'nobody'}")
        elif event["type"] == "game_clear":
            print(f"  GAME CLEAR: Hidden Player {data['hidden_player']} eliminated; winners: {', '.join(data['winners'])}")
        elif event["type"] == "hidden_player_wins":
            print(f"  The Hidden Player ({data['hidden_player']}) wins")
        elif event["type"] == "final_game_result":
            print(f"  {data['game']}: {data['winner']} wins  (series {data['wins']})")
        elif event["type"] == "agent_usage":
            print("\nLLM usage:")
            for player, usage in data.items():
                print(
                    f"  {player}: {usage['calls']} calls, {usage['errors']} API errors, "
                    f"{usage['prompt_tokens']} in / {usage['completion_tokens']} out tokens, "
                    f"${usage['cost']:.4f}"
                )
    invalid = [e for e in log.events if e["type"] == "invalid_output"]
    defaults = [e for e in log.events if e["type"] == "default_action"]
    if invalid:
        print(f"\nInvalid outputs: {len(invalid)}, replaced by default: {len(defaults)}")
    if result["aborted"]:
        print(f"\nRUN ABORTED - do not use this run as data.\nReason: {result['aborted']}")
    elif result["winner"]:
        print(f"\nChampion: {result['winner']}")
    elif result["alive"]:
        print(f"\nWinners: {', '.join(result['alive'])}")
    else:
        print("\nChampion: nobody")


if __name__ == "__main__":
    main()
