"""Final game 2 — Equation High-Low, 1v1 (spec §3).

3 hands. Each hand both players ante 1 chip and get 4 secret number cards.
One betting round, then (if nobody folded) each declares High (target 20) or
Low (target 1) and writes an expression using all 4 cards once. The smaller
distance to one's own target wins the pot.
"""

from __future__ import annotations

import ast
import operator
import random
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

HANDS = 3
START_CHIPS = 10
ANTE = 1
MAX_BET = 3
CARDS_PER_HAND = 4
CARD_VALUES = range(1, 11)
TARGETS = {"high": 20, "low": 1}
MAX_EXPRESSION_LENGTH = 100

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


class BetAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move: Literal["check", "bet", "call", "fold"]
    amount: int | None = None


class DeclareAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["high", "low"]
    expression: str


def evaluate(expression: str, cards: list[int]) -> Fraction:
    """Exact value of an expression that uses every card exactly once.

    Raises ValueError with a message meant for the player.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"expression is longer than {MAX_EXPRESSION_LENGTH} characters")
    text = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise ValueError(f"{expression!r} is not a valid expression") from None

    used: list[int] = []

    def ev(node: ast.AST) -> Fraction:
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("division by zero")
            return OPS[type(node.op)](left, right)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            used.append(node.value)
            return Fraction(node.value)
        raise ValueError("only your card numbers, + - * / and parentheses are allowed")

    value = ev(tree.body)
    if sorted(used) != sorted(cards):
        raise ValueError(
            f"use each of your cards {sorted(cards)} exactly once (you used {sorted(used)})"
        )
    return value


def random_expression(cards: list[int], rng: random.Random) -> str:
    """A valid expression with random order and operators (no division)."""
    numbers = list(cards)
    rng.shuffle(numbers)
    expression = str(numbers[0])
    for n in numbers[1:]:
        expression = f"({expression} {rng.choice('+-*')} {n})"
    return expression


class EquationHighLow(Game):
    name = "Equation High-Low"
    min_players = 2
    max_players = 2
    rules = (
        "GAME: Equation High-Low.\n"
        f"- {HANDS} hands. Each player starts with {START_CHIPS} chips.\n"
        f"- Each hand both players ante {ANTE} chip and get {CARDS_PER_HAND} secret cards "
        f"({CARD_VALUES.start}-{CARD_VALUES.stop - 1}). A chat phase follows.\n"
        f"- Betting: the first player checks or bets 1-{MAX_BET} chips. If they checked, "
        "the second player checks or bets. A bet must be answered with call or fold; "
        "no re-raises. Folding gives the pot to the other player.\n"
        "- If nobody folds, both secretly declare HIGH (target 20) or LOW (target 1) and "
        "write an expression using ALL 4 of their cards exactly once with + - * / and "
        "parentheses.\n"
        "- The player whose value is closer to their OWN declared target wins the pot. "
        "Equal distance: the pot is split.\n"
        "- The first player alternates each hand. A player who cannot ante loses. "
        "Most chips after the last hand wins; a tie is decided by a random draw.\n"
        "Example: your cards are 3, 5, 2, 8. Declaring HIGH with \"(5-3)*8+2\" = 18 is "
        "distance 2 from 20. Declaring LOW with \"(8-5)-(3-2)\" = 2 is distance 1 from 1. "
        "You declare LOW (distance 1); your opponent declares HIGH and reaches 20 "
        "(distance 0), so your opponent wins the pot."
    )

    def __init__(self, players, rng, first: str | None = None) -> None:
        super().__init__(players, rng)
        self.first = first or self.players[0]
        self.chips: dict[str, int] = {p: START_CHIPS for p in self.players}
        self.cards: dict[str, list[int]] = {p: [] for p in self.players}
        self.pot = 0
        self.hand = 0
        self.stage = "bet"  # "bet" | "respond" | "declare"
        self.betting: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []

    def other(self, player: str) -> str:
        a, b = self.players
        return b if player == a else a

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit(
            "game_start", {"game": self.name, "players": self.players, "first": self.first}
        )
        first = self.first
        for self.hand in range(1, HANDS + 1):
            if any(c < ANTE for c in self.chips.values()):
                break
            t.log.set_context(round=self.hand)
            await self._play_hand(t, first)
            first = self.other(first)
        t.log.set_context(round=None)

        a, b = self.players
        if self.chips[a] == self.chips[b]:
            winner = self.rng.choice(sorted(self.players))
            t.log.emit("tie_break_draw", {"between": sorted(self.players), "chosen": winner})
        else:
            winner = a if self.chips[a] > self.chips[b] else b
        return [[winner], [self.other(winner)]]

    async def _play_hand(self, t: Tournament, first: str) -> None:
        for p in self.players:
            self.chips[p] -= ANTE
            self.cards[p] = [self.rng.choice(CARD_VALUES) for _ in range(CARDS_PER_HAND)]
        self.pot = ANTE * 2
        self.betting = []
        t.log.emit("deal", {"cards": {p: list(c) for p, c in self.cards.items()}}, visible_to="god")
        t.log.emit("ante", {"pot": self.pot, "chips": dict(self.chips)})
        await t.chat_phase()

        folded = await self._betting(t, first)
        if folded:
            winner = self.other(folded)
            self.chips[winner] += self.pot
            result = {"hand": self.hand, "folded": folded, "winner": winner, "pot": self.pot}
        else:
            self.stage = "declare"
            actions = await t.collect_actions(self.players)
            showdown = {}
            for p in self.players:
                value = evaluate(actions[p].expression, self.cards[p])
                target = actions[p].target
                showdown[p] = {
                    "cards": list(self.cards[p]),
                    "target": target,
                    "expression": actions[p].expression,
                    "value": str(value),
                    "distance": float(abs(value - TARGETS[target])),
                }
            a, b = self.players
            da, db = showdown[a]["distance"], showdown[b]["distance"]
            winner = a if da < db else b if db < da else None
            if winner:
                self.chips[winner] += self.pot
            else:
                for p in self.players:
                    self.chips[p] += self.pot // 2
            result = {"hand": self.hand, "showdown": showdown, "winner": winner, "pot": self.pot}
        self.pot = 0
        self.results.append(result)
        t.log.emit("hand_result", {**result, "chips": dict(self.chips)})
        self.stage = "bet"

    async def _betting(self, t: Tournament, first: str) -> str | None:
        """Run the betting round. Return the player who folded, or None."""
        order = [first, self.other(first)]
        for player in order:
            self.stage = "bet"
            move = (await t.collect_actions([player]))[player]
            self.betting.append({"player": player, **move.model_dump(exclude_none=True)})
            t.log.emit("bet_move", move.model_dump(exclude_none=True), actor=player)
            if move.move == "bet":
                self.chips[player] -= move.amount
                self.pot += move.amount
                responder = self.other(player)
                self.stage = "respond"
                reply = (await t.collect_actions([responder]))[responder]
                self.betting.append({"player": responder, "move": reply.move})
                t.log.emit("bet_move", {"move": reply.move}, actor=responder)
                if reply.move == "fold":
                    return responder
                self.chips[responder] -= move.amount
                self.pot += move.amount
                return None
        return None

    def _max_bet(self) -> int:
        return min([MAX_BET, *self.chips.values()])

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_cards": list(self.cards[player])}

    def public_view(self) -> dict[str, Any]:
        return {
            "hand": self.hand,
            "hands": HANDS,
            "stage": self.stage,
            "chips": dict(self.chips),
            "pot": self.pot,
            "betting": list(self.betting),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return DeclareAction if self.stage == "declare" else BetAction

    def action_help(self, player: str) -> str:
        if self.stage == "declare":
            return (
                f'Declare and write an expression using all your cards {self.cards[player]}: '
                '{"target": "high" or "low", "expression": "<e.g. (a+b)*c-d>"}'
            )
        if self.stage == "respond":
            return 'Answer the bet: {"move": "call"} or {"move": "fold"}'
        if self._max_bet() == 0:
            return '{"move": "check"}'
        return f'{{"move": "check"}} or {{"move": "bet", "amount": <1-{self._max_bet()}>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]] | None:
        if self.stage == "declare":
            return None
        if self.stage == "respond":
            return [{"move": "call"}, {"move": "fold"}]
        return [{"move": "check"}] + [
            {"move": "bet", "amount": a} for a in range(1, self._max_bet() + 1)
        ]

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
        return {
            "target": rng.choice(sorted(TARGETS)),
            "expression": random_expression(self.cards[player], rng),
        }
