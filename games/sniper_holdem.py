"""Sniper Hold'em (S2 prison match), adapted.

Texas Hold'em with 2 private cards and 4 shared cards (best 5 of 6). After
betting and the full reveal, every player may "snipe" one hand type: any
OTHER player whose best hand is of that type is disqualified. The best hand
left wins the pot. Most chips at the end ranks first.
"""

from __future__ import annotations

import itertools
from collections import Counter
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

HANDS = 5
START_CHIPS = 20
ANTE = 1
MAX_BET = 5
RANKS = "23456789TJQKA"
SUITS = "SHDC"
CATEGORIES = [
    "high card", "pair", "two pair", "three of a kind", "straight",
    "flush", "full house", "four of a kind", "straight flush",
]


def card_value(card: str) -> int:
    return RANKS.index(card[0]) + 2


def rank5(cards: list[str]) -> tuple:
    """Comparable strength of a 5-card hand: (category index, tiebreakers...)."""
    values = sorted((card_value(c) for c in cards), reverse=True)
    counts = Counter(values)
    flush = len({c[1] for c in cards}) == 1
    unique = sorted(set(values), reverse=True)
    straight_high = None
    if len(unique) == 5 and unique[0] - unique[4] == 4:
        straight_high = unique[0]
    elif unique == [14, 5, 4, 3, 2]:  # A-2-3-4-5
        straight_high = 5
    by_count = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    groups = [v for v, _ in by_count]
    shape = sorted(counts.values(), reverse=True)
    if straight_high and flush:
        return (8, straight_high)
    if shape == [4, 1]:
        return (7, *groups)
    if shape == [3, 2]:
        return (6, *groups)
    if flush:
        return (5, *values)
    if straight_high:
        return (4, straight_high)
    if shape == [3, 1, 1]:
        return (3, *groups)
    if shape == [2, 2, 1]:
        return (2, *groups)
    if shape == [2, 1, 1, 1]:
        return (1, *groups)
    return (0, *values)


def best_hand(cards: list[str]) -> tuple:
    return max(rank5(list(combo)) for combo in itertools.combinations(cards, 5))


class BetAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bet: int | None = None
    fold: bool = False


class SnipeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snipe: str | None = None


class SniperHoldem(Game):
    name = "Sniper Hold'em"
    min_players = 2
    max_players = 4

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.chips: dict[str, int] = {p: START_CHIPS for p in self.players}
        self.hole: dict[str, list[str]] = {p: [] for p in self.players}
        self.board: list[str] = []
        self.shown = 0
        self.in_hand: list[str] = []
        self.hand = 0
        self.stage = "bet"
        self.carry = 0
        self.results: list[dict[str, Any]] = []

    rules = (
        "GAME: Sniper Hold'em.\n"
        f"- Everyone starts with {START_CHIPS} chips (game chips, not Pieces). {HANDS} hands.\n"
        f"- Each hand: everyone with chips antes {ANTE} and gets 2 secret cards. There are 4 shared "
        "cards: 2 are shown now, 2 after betting. Your hand is the best 5 of your 6 cards.\n"
        f"- After a conversation, everyone secretly bets 0-{MAX_BET} chips or folds (a fold loses the "
        "ante and leaves the hand).\n"
        "- After the last 2 shared cards are shown, everyone still in may SNIPE one hand type "
        f"({', '.join(CATEGORIES)}). Any OTHER player whose best hand is of a sniped type is "
        "disqualified.\n"
        "- The best hand left wins the pot (ties split). If nobody is left, the pot carries over "
        "to the next hand.\n"
        "- Most chips at the end ranks first. Cards are written like AS (ace of spades), TD (ten "
        "of diamonds), 7H, 2C.\n"
        "Example: A has a flush, B has a straight. B snipes \"flush\", so A is disqualified and "
        "B's straight wins, even though a flush normally beats a straight."
    )

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "hands": HANDS})
        for self.hand in range(1, HANDS + 1):
            self.in_hand = [p for p in self.players if self.chips[p] > 0]
            if len(self.in_hand) < 2:
                break
            t.log.set_context(round=self.hand)
            deck = [r + s for r in RANKS for s in SUITS]
            self.rng.shuffle(deck)
            for p in self.in_hand:
                self.chips[p] -= ANTE
                self.hole[p] = [deck.pop(), deck.pop()]
            self.board = [deck.pop() for _ in range(4)]
            self.shown = 2
            pot = ANTE * len(self.in_hand) + self.carry
            self.carry = 0
            t.log.emit("deal", {"hole": {p: self.hole[p] for p in self.in_hand}, "board": self.board}, visible_to="god")
            t.log.emit("board", {"shown": self.board[:2]})
            await t.chat_phase()

            self.stage = "bet"
            bets = await t.collect_actions(self.in_hand)
            folded = [p for p in self.in_hand if bets[p].fold]
            staying = [p for p in self.in_hand if not bets[p].fold]
            for p in staying:
                self.chips[p] -= bets[p].bet or 0
                pot += bets[p].bet or 0
            self.shown = 4
            t.log.emit("board", {"shown": list(self.board), "folded": folded,
                                 "bets": {p: bets[p].bet or 0 for p in staying}})

            snipes: dict[str, str | None] = {}
            if len(staying) > 1:
                self.in_hand = staying
                self.stage = "snipe"
                snipe_actions = await t.collect_actions(staying)
                snipes = {p: snipe_actions[p].snipe for p in staying}
            strength = {p: best_hand(self.hole[p] + self.board) for p in staying}
            category = {p: CATEGORIES[strength[p][0]] for p in staying}
            disqualified = sorted(
                p for p in staying if any(snipes.get(q) == category[p] for q in staying if q != p)
            )
            alive = [p for p in staying if p not in disqualified]
            winners: list[str] = []
            if alive:
                best = max(strength[p] for p in alive)
                winners = sorted(p for p in alive if strength[p] == best)
                for i, p in enumerate(winners):
                    self.chips[p] += pot // len(winners) + (1 if i < pot % len(winners) else 0)
            else:
                self.carry = pot
            result = {
                "hand": self.hand, "pot": pot, "board": list(self.board), "folded": folded,
                "showdown": {p: {"cards": self.hole[p], "best": category[p]} for p in staying},
                "snipes": snipes, "disqualified": disqualified, "winners": winners,
            }
            self.results.append(result)
            t.log.emit("holdem_result", {**result, "chips": dict(self.chips)})
            self.stage = "bet"
        t.log.set_context(round=None)
        return rank_by_score(self.chips)

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_cards": list(self.hole[player]), "my_chips": self.chips[player]}

    def public_view(self) -> dict[str, Any]:
        return {"hand": self.hand, "hands": HANDS, "stage": self.stage, "shared_cards": self.board[: self.shown],
                "chips": dict(self.chips), "in_hand": list(self.in_hand), "results": list(self.results)}

    def action_schema(self, player: str) -> type[BaseModel]:
        return SnipeAction if self.stage == "snipe" else BetAction

    def action_help(self, player: str) -> str:
        if self.stage == "snipe":
            return f'Snipe a hand type or not: {{"snipe": one of {CATEGORIES} or null}}'
        top = min(MAX_BET, self.chips[player])
        return f'{{"bet": <0-{top}>}} to stay in, or {{"fold": true}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        if self.stage == "snipe":
            return [{"snipe": None}] + [{"snipe": c} for c in CATEGORIES]
        top = min(MAX_BET, self.chips[player])
        return [{"bet": b} for b in range(top + 1)] + [{"fold": True}]
