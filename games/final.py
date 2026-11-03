"""Day 4 — Final, best of 3 (spec §3).

Time Auction, then Equation High-Low, then liar's dice with 3 dice each. The
first player to win 2 games is the champion. The player with more Pieces
chooses who moves first in each game. No Pieces are awarded.

While a sub-game runs, the Final delegates views and actions to it.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking
from games.equation_high_low import EquationHighLow
from games.liars_dice import LiarsDice
from games.time_auction import FINAL_BANK, FINAL_ROUNDS, TimeAuction

if TYPE_CHECKING:
    from engine.tournament import Tournament

WINS_NEEDED = 2

SubGame = Callable[[list[str], random.Random, str], Game]
GAMES: list[SubGame] = [
    lambda players, rng, first: TimeAuction(
        players, rng, bank=FINAL_BANK, rounds=FINAL_ROUNDS, single_winner=True
    ),
    lambda players, rng, first: EquationHighLow(players, rng, first=first),
    lambda players, rng, first: LiarsDice(players, rng, dice_per_player=3, first=first),
]


class FirstChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first: str


class Final(Game):
    name = "Final"
    min_players = 2
    max_players = 2
    final = True

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.wins: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.current: Game | None = None
        self.chooser: str | None = None

    @property
    def rules(self) -> str:
        text = (
            "FINAL: best of 3. No Pieces are awarded; the loser is eliminated and the "
            "winner is the champion.\n"
            "- Games in order: Time Auction, Equation High-Low, Doubt & Bet with 3 dice.\n"
            f"- The first player to win {WINS_NEEDED} games is the champion.\n"
            "- The player with more Pieces chooses who moves first in each game."
        )
        if self.current is not None:
            text += "\n\n" + self.current.rules
        return text

    def other(self, player: str) -> str:
        a, b = self.players
        return b if player == a else a

    async def play(self, t: Tournament) -> Ranking:
        a, b = self.players
        if t.pieces[a] != t.pieces[b]:
            self.chooser = a if t.pieces[a] > t.pieces[b] else b
        else:
            self.chooser = self.rng.choice(sorted(self.players))
            t.log.emit("tie_break_draw", {"between": sorted(self.players), "chosen": self.chooser})
        t.log.emit("game_start", {"game": self.name, "players": self.players, "chooser": self.chooser})

        for make_game in GAMES:
            if max(self.wins.values()) >= WINS_NEEDED:
                break
            self.current = None
            t.log.set_context(round=None)
            first = (await t.collect_actions([self.chooser]))[self.chooser].first
            game = make_game([first, self.other(first)], self.rng, first)
            t.log.emit("first_player", {"game": game.name, "first": first}, actor=self.chooser)
            self.current = game
            winner = (await game.play(t))[0][0]
            self.wins[winner] += 1
            self.results.append({"game": game.name, "winner": winner})
            t.log.set_context(round=None)
            t.log.emit("final_game_result", {"game": game.name, "winner": winner, "wins": dict(self.wins)})

        self.current = None
        champion = max(self.players, key=lambda p: self.wins[p])
        return [[champion], [self.other(champion)]]

    def private_view(self, player: str) -> dict[str, Any]:
        return self.current.private_view(player) if self.current else {}

    def public_view(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "wins": dict(self.wins),
            "results": list(self.results),
            "chooser": self.chooser,
        }
        if self.current is not None:
            view["current_game"] = self.current.name
            view["current_state"] = self.current.public_view()
        return view

    def action_schema(self, player: str) -> type[BaseModel]:
        return self.current.action_schema(player) if self.current else FirstChoice

    def action_help(self, player: str) -> str:
        if self.current:
            return self.current.action_help(player)
        return f'Choose who moves first in the next game: {{"first": one of {self.players}}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]] | None:
        if self.current:
            return self.current.legal_actions(player)
        return [{"first": p} for p in self.players]

    def check_action(self, player: str, action: BaseModel) -> str | None:
        if self.current:
            return self.current.check_action(player, action)
        return super().check_action(player, action)

    def random_action(self, player: str, rng: random.Random) -> dict[str, Any]:
        if self.current:
            return self.current.random_action(player, rng)
        return super().random_action(player, rng)
