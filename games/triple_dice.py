"""Triple Dice (S2 prison match), adapted.

Each round every player rolls 3 dice: 2 are shown to everyone, 1 is hidden.
Players secretly predict their own rank for the round. Combinations rank
triple > straight > pair > nothing, then by sum. Points by rank, doubled for a
correct prediction. Most points ranks first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

ROUNDS = 5
COMBOS = ["nothing", "pair", "straight", "triple"]


def combo(dice: list[int]) -> tuple[int, int]:
    """(combination index, sum) — higher is better."""
    d = sorted(dice)
    if d[0] == d[2]:
        kind = 3
    elif d[1] - d[0] == 1 and d[2] - d[1] == 1:
        kind = 2
    elif d[0] == d[1] or d[1] == d[2]:
        kind = 1
    else:
        kind = 0
    return kind, sum(d)


def round_ranks(dice: dict[str, list[int]]) -> dict[str, int]:
    """Rank per player (1 = best); equal combinations share the better rank."""
    strength = {p: combo(d) for p, d in dice.items()}
    return {p: 1 + sum(1 for q in dice if strength[q] > strength[p]) for p in dice}


class PredictAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predict: int


class TripleDice(Game):
    name = "Triple Dice"
    min_players = 2
    max_players = 4

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.dice: dict[str, list[int]] = {p: [] for p in self.players}
        self.points: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0

    rules = (
        "GAME: Triple Dice.\n"
        f"- {ROUNDS} rounds. Each round every player rolls 3 dice: 2 are shown to everyone, the third "
        "only you can see.\n"
        "- Combinations rank: triple > straight (three in a row, e.g. 3-4-5) > pair > nothing; equal "
        "combinations are ranked by the sum of the dice. Equal hands share the better rank.\n"
        "- After a conversation, everyone secretly predicts their own rank this round (1 = best).\n"
        "- Points this round = number of players - rank + 1, DOUBLED if your prediction was right.\n"
        "- Most points at the end ranks first.\n"
        "Example (3 players): A shows 4,4 and hides a 4 (triple), B shows 2,3 and hides a 6 (nothing), "
        "C shows 5,6 and hides a 4 (straight). Ranks: A 1, C 2, B 3. A predicted 1: 3 x 2 = 6 points; "
        "C predicted 1: 2 points; B predicted 3: 1 x 2 = 2 points."
    )

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "rounds": ROUNDS})
        n = len(self.players)
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            for p in self.players:
                self.dice[p] = [self.rng.randint(1, 6) for _ in range(3)]
            t.log.emit("roll", {"dice": {p: list(d) for p, d in self.dice.items()}}, visible_to="god")
            t.log.emit("shown_dice", {"shown": {p: d[:2] for p, d in self.dice.items()}})
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            ranks = round_ranks(self.dice)
            gained = {}
            for p in self.players:
                pts = n - ranks[p] + 1
                if actions[p].predict == ranks[p]:
                    pts *= 2
                gained[p] = pts
                self.points[p] += pts
            result = {
                "round": self.round,
                "dice": {p: list(d) for p, d in self.dice.items()},
                "combos": {p: COMBOS[combo(d)[0]] for p, d in self.dice.items()},
                "ranks": ranks,
                "predictions": {p: actions[p].predict for p in self.players},
                "gained": gained,
            }
            self.results.append(result)
            t.log.emit("dice_result", {**result, "points": dict(self.points)})
        t.log.set_context(round=None)
        return rank_by_score(self.points)

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_dice": list(self.dice[player])}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "shown_dice": {p: d[:2] for p, d in self.dice.items()},
            "points": dict(self.points),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return PredictAction

    def action_help(self, player: str) -> str:
        return f'Predict your rank this round: {{"predict": <1-{len(self.players)}>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"predict": r} for r in range(1, len(self.players) + 1)]
