"""Day 3 — Doubt & Bet, a liar's dice adaptation (spec §3). Also final game 3.

Everyone rolls hidden dice. Players take turns raising a claim about how many
dice on the whole table show a face, or doubt the last claim. Whoever is wrong
loses a die. The last player with dice wins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

FACES = range(1, 7)


class DiceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = None
    face: int | None = None
    doubt: bool = False


class LiarsDice(Game):
    name = "Doubt & Bet"
    min_players = 2
    max_players = 12

    def __init__(self, players, rng, dice_per_player: int | None = None, first: str | None = None) -> None:
        super().__init__(players, rng)
        n = len(self.players)
        self.dice_per_player = dice_per_player or (4 if n <= 5 else 3 if n <= 8 else 2)
        self.first = first
        self.dice_count: dict[str, int] = {p: self.dice_per_player for p in self.players}
        self.dice: dict[str, list[int]] = {p: [] for p in self.players}
        self.bids: list[dict[str, Any]] = []  # this round's bids
        self.out_order: list[str] = []
        self.round = 0
        self.turn: str | None = None

    @property
    def rules(self) -> str:
        return (
            f"GAME: {self.name} (liar's dice).\n"
            f"- Every player starts with {self.dice_per_player} dice. There are no wild faces.\n"
            "- Each round starts with a chat phase. Then everyone rolls secretly and sees "
            "only their own dice.\n"
            "- Players take turns in seat order. On your turn either BID or DOUBT.\n"
            "- A bid claims \"there are at least Q dice showing face F on the whole table\". "
            "A new bid must have a higher Q, or the same Q and a higher F.\n"
            "- Doubt challenges the previous bid: all dice are revealed. If the bid was "
            "true, the doubter loses 1 die. If it was false, the bidder loses 1 die.\n"
            "- The loser of a round starts the next one. A player with 0 dice is out.\n"
            "- The last player with dice wins. Others rank by when they went out "
            "(later is better).\n"
            "Example: 3 players with 4 dice each, 12 dice on the table. A bids 3 x 5 "
            "(\"at least three 5s\"). B raises to 3 x 6 (same quantity, higher face; 4 x 2 "
            "would also be allowed). C doubts. All dice are revealed and there are four "
            "6s, so B's bid was true: C, the doubter, loses a die and starts the next round."
        )

    def active(self) -> list[str]:
        return [p for p in self.players if self.dice_count[p] > 0]

    def total_dice(self) -> int:
        return sum(self.dice_count.values())

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit(
            "game_start",
            {"game": self.name, "players": self.players, "dice_per_player": self.dice_per_player},
        )
        starter = self.first or self.rng.choice(self.players)
        while len(self.active()) > 1:
            self.round += 1
            t.log.set_context(round=self.round)
            await t.chat_phase()
            loser = await self._play_round(t, starter)
            if self.dice_count[loser] == 0:
                self.out_order.append(loser)
                t.log.emit("out_of_dice", {"player": loser})
                starter = self._next(loser)
            else:
                starter = loser
        winner = self.active()[0]
        return [[winner]] + [[p] for p in reversed(self.out_order)]

    async def _play_round(self, t: Tournament, starter: str) -> str:
        """Play one round of bidding; return the player who lost a die."""
        self.bids = []
        for p in self.active():
            self.dice[p] = sorted(self.rng.choice(FACES) for _ in range(self.dice_count[p]))
        t.log.emit("roll", {"dice": {p: list(d) for p, d in self.dice.items() if d}}, visible_to="god")

        self.turn = starter
        while True:
            action = (await t.collect_actions([self.turn]))[self.turn]
            if action.doubt:
                bid = self.bids[-1]
                count = sum(d.count(bid["face"]) for d in self.dice.values())
                loser = self.turn if count >= bid["quantity"] else bid["player"]
                self.dice_count[loser] -= 1
                t.log.emit(
                    "doubt",
                    {
                        "doubter": self.turn,
                        "bid": bid,
                        "dice": {p: list(d) for p, d in self.dice.items() if d},
                        "count": count,
                        "bid_was_true": count >= bid["quantity"],
                        "loser": loser,
                        "dice_count": dict(self.dice_count),
                    },
                    actor=self.turn,
                )
                self.turn = None
                for p in self.players:
                    self.dice[p] = []
                return loser
            bid = {"player": self.turn, "quantity": action.quantity, "face": action.face}
            self.bids.append(bid)
            t.log.emit("bid", {"quantity": action.quantity, "face": action.face}, actor=self.turn)
            self.turn = self._next(self.turn)

    def _next(self, player: str) -> str:
        """Next player in seat order who still has dice."""
        i = self.players.index(player)
        for step in range(1, len(self.players) + 1):
            candidate = self.players[(i + step) % len(self.players)]
            if self.dice_count[candidate] > 0:
                return candidate
        raise RuntimeError("no active players")

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_dice": list(self.dice[player])}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "turn": self.turn,
            "seat_order": list(self.players),
            "dice_count": dict(self.dice_count),
            "total_dice": self.total_dice(),
            "bids_this_round": list(self.bids),
            "out": list(self.out_order),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return DiceAction

    def action_help(self, player: str) -> str:
        last = self.bids[-1] if self.bids else None
        bid = (
            f'Bid with {{"quantity": Q, "face": F}} (Q up to {self.total_dice()}, F 1-6)'
            + (f', higher than {last["quantity"]} x {last["face"]}' if last else "")
        )
        if last:
            return bid + ', or doubt the last bid with {"doubt": true}'
        return bid

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        last = self.bids[-1] if self.bids else None
        actions: list[dict[str, Any]] = [
            {"quantity": q, "face": f}
            for q in range(1, self.total_dice() + 1)
            for f in FACES
            if last is None or (q, f) > (last["quantity"], last["face"])
        ]
        if last is not None:
            actions.append({"doubt": True})
        return actions
