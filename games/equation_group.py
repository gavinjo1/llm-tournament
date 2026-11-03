"""Equation High-Low, group version (S1 day 6), adapted.

Every hand, each player with chips antes, gets 4 secret number cards, bets,
then declares HIGH (target 20) or LOW (target 1) with an expression using all
4 cards. Half the pot goes to the best HIGH, half to the best LOW; winners of a
side share it in proportion to what they staked. Most chips ranks first.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score
from games.equation_high_low import TARGETS, evaluate, random_expression

if TYPE_CHECKING:
    from engine.tournament import Tournament

HANDS = 4
START_CHIPS = 10
ANTE = 1
MAX_BET = 3
CARDS = 4


class BetAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bet: int


class DeclareAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["high", "low"]
    expression: str


def split_pot(pot: int, stakes: dict[str, int], results: dict[str, tuple[str, float]]) -> dict[str, int]:
    """Chips won per player. results: player -> (target, distance)."""
    won = {p: 0 for p in stakes}
    sides = {s: {p: d for p, (tgt, d) in results.items() if tgt == s} for s in ("high", "low")}
    active = [s for s in ("high", "low") if sides[s]]
    if not active:
        return won
    shares = {active[0]: pot} if len(active) == 1 else {"high": pot // 2, "low": pot - pot // 2}
    for side, share in shares.items():
        best = min(sides[side].values())
        winners = sorted(p for p, d in sides[side].items() if d == best)
        total_stake = sum(stakes[p] for p in winners)
        paid = 0
        for p in winners:
            amount = share * stakes[p] // total_stake
            won[p] += amount
            paid += amount
        won[winners[0]] += share - paid  # rounding remainder
    return won


class EquationHighLowGroup(Game):
    name = "Equation High-Low (group)"
    min_players = 3
    max_players = 12

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.chips: dict[str, int] = {p: START_CHIPS for p in self.players}
        self.cards: dict[str, list[int]] = {p: [] for p in self.players}
        self.in_hand: list[str] = []
        self.hand = 0
        self.stage = "bet"
        self.results: list[dict[str, Any]] = []

    rules = (
        "GAME: Equation High-Low (group).\n"
        f"- Everyone starts with {START_CHIPS} chips; these are game chips, not Pieces. {HANDS} hands.\n"
        f"- Each hand, every player with chips antes {ANTE} and gets {CARDS} secret cards (1-10). "
        "Conversation follows.\n"
        f"- Then everyone secretly bets 0-{MAX_BET} more chips, and finally declares HIGH (target 20) "
        "or LOW (target 1) with an expression using ALL 4 of their cards once (+ - * / and "
        "parentheses).\n"
        "- Half the pot goes to the HIGH player closest to 20, half to the LOW player closest to 1 "
        "(all of it if only one side was declared). Tied winners share their half in proportion to "
        "the chips they put in this hand (ante + bet).\n"
        "- A player with no chips sits out. Most chips at the end ranks first.\n"
        "Example: 4 players each ante 1 and bet 1: pot 8. A declares HIGH with 19, B HIGH with 22, "
        "C LOW with 2, D LOW with 4. A wins 4 (closest to 20), C wins 4 (closest to 1)."
    )

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "hands": HANDS})
        for self.hand in range(1, HANDS + 1):
            self.in_hand = [p for p in self.players if self.chips[p] > 0]
            if len(self.in_hand) < 2:
                break
            t.log.set_context(round=self.hand)
            for p in self.in_hand:
                self.chips[p] -= ANTE
                self.cards[p] = [self.rng.randint(1, 10) for _ in range(CARDS)]
            t.log.emit("deal", {"cards": {p: list(self.cards[p]) for p in self.in_hand}}, visible_to="god")
            await t.chat_phase()
            self.stage = "bet"
            bets = await t.collect_actions(self.in_hand)
            stakes = {}
            for p in self.in_hand:
                self.chips[p] -= bets[p].bet
                stakes[p] = ANTE + bets[p].bet
            pot = sum(stakes.values())
            self.stage = "declare"
            declares = await t.collect_actions(self.in_hand)
            results, show = {}, {}
            for p in self.in_hand:
                value = evaluate(declares[p].expression, self.cards[p])
                dist = float(abs(value - TARGETS[declares[p].target]))
                results[p] = (declares[p].target, dist)
                show[p] = {"cards": self.cards[p], "target": declares[p].target,
                           "expression": declares[p].expression, "value": str(value), "distance": dist}
            won = split_pot(pot, stakes, results)
            for p, w in won.items():
                self.chips[p] += w
            result = {"hand": self.hand, "pot": pot, "stakes": stakes, "showdown": show, "won": won}
            self.results.append(result)
            t.log.emit("group_hand_result", {**result, "chips": dict(self.chips)})
            self.stage = "bet"
        t.log.set_context(round=None)
        return rank_by_score(self.chips)

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_cards": list(self.cards[player]), "my_chips": self.chips[player]}

    def public_view(self) -> dict[str, Any]:
        return {"hand": self.hand, "hands": HANDS, "stage": self.stage, "chips": dict(self.chips),
                "results": list(self.results)}

    def action_schema(self, player: str) -> type[BaseModel]:
        return DeclareAction if self.stage == "declare" else BetAction

    def _max_bet(self, player: str) -> int:
        return min(MAX_BET, self.chips[player])

    def action_help(self, player: str) -> str:
        if self.stage == "declare":
            return (f'Declare with all your cards {self.cards[player]}: '
                    '{"target": "high" or "low", "expression": "<e.g. (a+b)*c-d>"}')
        return f'Bet extra chips: {{"bet": <0-{self._max_bet(player)}>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]] | None:
        if self.stage == "declare":
            return None
        return [{"bet": b} for b in range(self._max_bet(player) + 1)]

    def check_action(self, player: str, action: BaseModel) -> str | None:
        if self.stage != "declare":
            return super().check_action(player, action)
        try:
            evaluate(action.expression, self.cards[player])
        except ValueError as exc:
            return f"Invalid expression: {exc}"
        return None

    def random_action(self, player: str, rng: random.Random) -> dict[str, Any]:
        if self.stage != "declare":
            return super().random_action(player, rng)
        return {"target": rng.choice(sorted(TARGETS)), "expression": random_expression(self.cards[player], rng)}
