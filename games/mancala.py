"""Balance Mancala (S2 day 5), adapted as a text game.

Each round coloured pots (red, blue, green; more of each in big games) fill
with counters. Every player secretly picks one pot; a pot's counters are split
equally among everyone who picked it. A player's score is their LOWEST colour
total, so players must balance their colours and avoid crowding the same pot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

COLORS = ("red", "blue", "green")
ROUNDS = 8


class PickAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pot: str


def pot_color(pot: str) -> str:
    """Pot ids are a colour ("red") or a colour and a number ("red-2")."""
    return pot.split("-")[0]


def split_pots(pots: dict[str, int], picks: dict[str, str]) -> dict[str, dict[str, int]]:
    """Counters each player gets per colour this round (equal split, rounded down)."""
    gains = {p: {c: 0 for c in COLORS} for p in picks}
    for pot, amount in pots.items():
        takers = [p for p, chosen in picks.items() if chosen == pot]
        if takers:
            share = amount // len(takers)
            for p in takers:
                gains[p][pot_color(pot)] += share
    return gains


def pot_ids(players: int) -> list[str]:
    """3 pots up to 6 players; 2 of each colour above (6 pots for 12)."""
    per_color = 1 if players <= 6 else 2
    if per_color == 1:
        return list(COLORS)
    return [f"{c}-{i}" for c in COLORS for i in range(1, per_color + 1)]


class BalanceMancala(Game):
    name = "Balance Mancala"
    min_players = 3
    max_players = 12

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        n = len(self.players)
        self.pots = pot_ids(n)
        top = 2 * n * len(COLORS) // len(self.pots)
        self.rounds = [{pot: rng.randint(2, top) for pot in self.pots} for _ in range(ROUNDS)]
        self.totals: dict[str, dict[str, int]] = {p: {c: 0 for c in COLORS} for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0

    @property
    def rules(self) -> str:
        return (
            "GAME: Balance Mancala.\n"
            f"- {ROUNDS} rounds. Each round {len(self.pots)} pots ({', '.join(self.pots)}) are filled "
            "with counters; the amounts are shown before you choose.\n"
            "- Each round: conversation, then everyone secretly picks ONE pot. A pot's counters are "
            "split equally among everyone who picked it (rounded down; leftovers are lost). Counters "
            "count towards the pot's colour.\n"
            "- Your score is your LOWEST colour total (red, blue, green). Ties are broken by your total "
            "over all colours.\n"
            "Example: pots red 9, blue 4, green 6. A and B pick red (4 each), C picks blue (4), nobody "
            "picks green (lost). If at the end A has red 20, blue 6, green 9, A's score is 6."
        )

    def score(self, player: str) -> tuple[int, int]:
        t = self.totals[player]
        return min(t.values()), sum(t.values())

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "rounds": ROUNDS})
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            pots = self.rounds[self.round - 1]
            t.log.emit("pots", {"round": self.round, "pots": pots})
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            picks = {p: actions[p].pot for p in self.players}
            gains = split_pots(pots, picks)
            for p, g in gains.items():
                for c in COLORS:
                    self.totals[p][c] += g[c]
            result = {"round": self.round, "pots": pots, "picks": picks}
            self.results.append(result)
            t.log.emit("mancala_result", {**result, "totals": {p: dict(v) for p, v in self.totals.items()}})
        t.log.set_context(round=None)
        keys = {p: self.score(p) for p in self.players}
        return [sorted(p for p in self.players if keys[p] == k) for k in sorted(set(keys.values()), reverse=True)]

    def private_view(self, player: str) -> dict[str, Any]:
        return {}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "pots_now": self.rounds[self.round - 1] if self.round else None,
            "totals": {p: dict(v) for p, v in self.totals.items()},
            "scores": {p: self.score(p)[0] for p in self.players},
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return PickAction

    def action_help(self, player: str) -> str:
        return f'{{"pot": one of {self.pots}}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"pot": pot} for pot in self.pots]
