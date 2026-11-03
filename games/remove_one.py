"""Day 1 — Remove One (spec §3).

Each player holds cards 1-6, each playable once. Over 6 rounds everyone plays
a card at the same time; the lowest number played by exactly one player wins
the round and 1 victory point.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

CARDS = range(1, 7)
ROUNDS = 6


class CardAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: int


class RemoveOne(Game):
    name = "Remove One"
    min_players = 2
    max_players = 6
    rules = (
        "GAME: Remove One.\n"
        f"- You hold cards {CARDS.start}-{CARDS.stop - 1}. Each card can be played once.\n"
        f"- There are {ROUNDS} rounds. Each round there is a chat phase, then every "
        "player secretly plays one unused card.\n"
        "- All cards are revealed, with who played them. The LOWEST number played by "
        "exactly ONE player wins the round and 1 victory point. If no number is "
        "unique, nobody scores.\n"
        "- Placement is by victory points, highest first.\n"
        "Example: A plays 1, B plays 1, C plays 2, D plays 4, E plays 2. Cards 1 and 2 "
        "were played twice, so the lowest unique card is 4: D wins the round. A, B, C "
        "and E have now used up those cards."
    )

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.hands: dict[str, set[int]] = {p: set(CARDS) for p in self.players}
        self.victory_points: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "rounds": ROUNDS})
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            plays = {p: actions[p].card for p in self.players}
            for p, card in plays.items():
                self.hands[p].remove(card)
            winner = round_winner(plays)
            if winner is not None:
                self.victory_points[winner] += 1
            result = {"round": self.round, "plays": plays, "winner": winner}
            self.results.append(result)
            t.log.emit("round_result", {**result, "victory_points": dict(self.victory_points)})
        return rank_by_score(self.victory_points)

    def private_view(self, player: str) -> dict[str, Any]:
        return {"hand": sorted(self.hands[player])}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "victory_points": dict(self.victory_points),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return CardAction

    def action_help(self, player: str) -> str:
        return f'Play one card from your hand {sorted(self.hands[player])}: {{"card": <number>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"card": c} for c in sorted(self.hands[player])]


def round_winner(plays: dict[str, int]) -> str | None:
    """The player who played the lowest unique card, or None."""
    counts = Counter(plays.values())
    unique = [card for card, n in counts.items() if n == 1]
    if not unique:
        return None
    lowest = min(unique)
    return next(p for p, card in plays.items() if card == lowest)
