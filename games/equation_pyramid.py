"""Equation Pyramid (S2 prison match), adapted.

Ten tiles sit in a pyramid (rows of 1, 2, 3, 4), each with an operator and a
number. Each round a target is announced. Players secretly pick three tiles
in order: start from the first tile's number, then apply the second and third
tiles' operations, left to right. Right: +1 point, wrong: -1, skip: 0.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

ROUNDS = 5
LABELS = "ABCDEFGHIJ"
ROWS = (1, 2, 3, 4)
OPS = "+-*"


class PickTiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tiles: list[str] | None = None
    skip: bool = False


def evaluate(tiles: dict[str, tuple[str, int]], pick: list[str]) -> int:
    value = tiles[pick[0]][1]
    for label in pick[1:]:
        op, n = tiles[label]
        value = value + n if op == "+" else value - n if op == "-" else value * n
    return value


def all_values(tiles: dict[str, tuple[str, int]]) -> dict[int, int]:
    """How many ordered picks reach each value."""
    counts: dict[int, int] = {}
    for pick in itertools.permutations(LABELS, 3):
        v = evaluate(tiles, list(pick))
        counts[v] = counts.get(v, 0) + 1
    return counts


class EquationPyramid(Game):
    name = "Equation Pyramid"
    min_players = 2
    max_players = 4

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.tiles: dict[str, tuple[str, int]] = {
            label: (rng.choice(OPS), rng.randint(1, 9)) for label in LABELS
        }
        counts = all_values(self.tiles)
        candidates = sorted(v for v, c in counts.items() if 1 <= c <= 4 and 1 <= v <= 60)
        if len(candidates) < ROUNDS:
            candidates = sorted(v for v in counts if 1 <= v <= 99)
        self.targets = rng.sample(candidates, ROUNDS)
        self.points: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0

    rules = (
        "GAME: Equation Pyramid.\n"
        "- Ten tiles A-J sit in a pyramid (rows A | B C | D E F | G H I J). Each tile shows an "
        "operator and a number, e.g. \"*3\".\n"
        "- An answer is three different tiles in order. Start with the FIRST tile's number (its "
        "operator is ignored), then apply the second tile's operation, then the third's, left to "
        "right.\n"
        f"- {ROUNDS} rounds. Each round a target number is announced; after a conversation everyone "
        "secretly submits three tiles, or skips.\n"
        "- A correct answer scores +1, a wrong one -1, a skip 0. Most points at the end ranks first.\n"
        "Example: tiles A = +5, D = *3, H = -2. Answer [A, D, H] = 5 * 3 - 2 = 13. If the target is "
        "13, that scores +1."
    )

    def layout(self) -> list[list[str]]:
        rows, i = [], 0
        for size in ROWS:
            rows.append([f"{LABELS[j]}={self.tiles[LABELS[j]][0]}{self.tiles[LABELS[j]][1]}" for j in range(i, i + size)])
            i += size
        return rows

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "tiles": self.layout()})
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            target = self.targets[self.round - 1]
            t.log.emit("pyramid_target", {"round": self.round, "target": target})
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            answers, gained = {}, {}
            for p in self.players:
                a = actions[p]
                if a.skip or not a.tiles:
                    answers[p], gained[p] = None, 0
                    continue
                value = evaluate(self.tiles, a.tiles)
                answers[p] = {"tiles": a.tiles, "value": value}
                gained[p] = 1 if value == target else -1
                self.points[p] += gained[p]
            result = {"round": self.round, "target": target, "answers": answers, "gained": gained}
            self.results.append(result)
            t.log.emit("pyramid_result", {**result, "points": dict(self.points)})
        t.log.set_context(round=None)
        return rank_by_score(self.points)

    def private_view(self, player: str) -> dict[str, Any]:
        return {}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "pyramid": self.layout(),
            "target": self.targets[self.round - 1] if self.round else None,
            "points": dict(self.points),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return PickTiles

    def action_help(self, player: str) -> str:
        return '{"tiles": ["X", "Y", "Z"]} (three different tiles A-J, in order), or {"skip": true}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"skip": True}] + [{"tiles": list(p)} for p in itertools.permutations(LABELS, 3)]
