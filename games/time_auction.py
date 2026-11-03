"""Time Auction (spec §3): game 1 of the final (1v1), and a 4-player day in
the 6-player tournament.

Each player has a bank of time units for the whole game. Each round everyone
secretly bids; the single highest bid wins a token. Bids are spent even if
they lose. Only the winner of each round is revealed, not the amounts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

DAY_BANK, DAY_ROUNDS = 300, 7
FINAL_BANK, FINAL_ROUNDS = 120, 5


class BidAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bid: int


class TimeAuction(Game):
    name = "Time Auction"
    min_players = 2
    max_players = 6

    def __init__(
        self,
        players,
        rng,
        bank: int = DAY_BANK,
        rounds: int = DAY_ROUNDS,
        single_winner: bool = False,
    ) -> None:
        """single_winner: break a tie for first place with a random draw (the final)."""
        super().__init__(players, rng)
        self.start_bank = bank
        self.rounds = rounds
        self.single_winner = single_winner
        self.bank: dict[str, int] = {p: bank for p in self.players}
        self.tokens: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0

    @property
    def rules(self) -> str:
        tie = " A remaining tie for first is decided by a random draw." if self.single_winner else ""
        return (
            "GAME: Time Auction.\n"
            f"- Each player has a bank of {self.start_bank} time units for the whole game.\n"
            f"- {self.rounds} rounds. Each round starts with a chat phase, then every player "
            "secretly bids 0 or more units from their bank.\n"
            "- The single highest bid wins 1 token. If the highest bid is tied, nobody "
            "gets a token.\n"
            "- Bids are spent even if they lose. Only the round winner is revealed, not "
            "the amounts.\n"
            f"- Placement is by tokens, then by larger remaining bank.{tie}\n"
            f"Example: A bids 30 and B bids 25. A wins the token. A's bank goes from "
            f"{self.start_bank} to {self.start_bank - 30}, B's to {self.start_bank - 25}. "
            "Everyone is only told \"A won the round\"."
        )

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit(
            "game_start",
            {"game": self.name, "players": self.players, "rounds": self.rounds, "bank": self.start_bank},
        )
        for self.round in range(1, self.rounds + 1):
            t.log.set_context(round=self.round)
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            bids = {p: actions[p].bid for p in self.players}
            for p, bid in bids.items():
                self.bank[p] -= bid
            winner = round_winner(bids)
            if winner:
                self.tokens[winner] += 1
            result = {"round": self.round, "winner": winner}
            self.results.append(result)
            t.log.emit("bids", {"bids": bids, "bank": dict(self.bank)}, visible_to="god")
            t.log.emit("auction_result", {**result, "tokens": dict(self.tokens)})

        t.log.set_context(round=None)
        ranking = self._ranking()
        if self.single_winner and len(ranking[0]) > 1:
            tied = ranking[0]
            winner = self.rng.choice(tied)
            t.log.emit("tie_break_draw", {"between": tied, "chosen": winner})
            ranking = [[winner], [p for p in tied if p != winner]] + ranking[1:]
        return ranking

    def _ranking(self) -> Ranking:
        key = {p: (self.tokens[p], self.bank[p]) for p in self.players}
        return [
            sorted(p for p in self.players if key[p] == k)
            for k in sorted(set(key.values()), reverse=True)
        ]

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_bank": self.bank[player]}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": self.rounds,
            "tokens": dict(self.tokens),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return BidAction

    def action_help(self, player: str) -> str:
        return f'Bid from your bank of {self.bank[player]}: {{"bid": <0-{self.bank[player]}>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"bid": b} for b in range(self.bank[player] + 1)]


def round_winner(bids: dict[str, int]) -> str | None:
    """The player with the single highest bid, or None if it is tied."""
    top = max(bids.values())
    leaders = [p for p, b in bids.items() if b == top]
    return leaders[0] if len(leaders) == 1 else None
