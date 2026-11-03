"""The prison decision: the player(s) with the most Pieces choose who joins the
poorest player in prison.

Not a match: a decision step after the main match, run like a game so that the
leaders' conversation and votes go through the normal machinery (validation,
retries, logging).
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament


class SendAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    send: list[str]


class PrisonChoice(Game):
    name = "Prison Choice"
    min_players = 1
    max_players = 26

    def __init__(self, choosers: list[str], candidates: list[str], seats: int, already: list[str], rng) -> None:
        super().__init__(choosers, rng)
        self.candidates = list(candidates)
        self.seats = seats
        self.already = list(already)

    @property
    def rules(self) -> str:
        who = "You hold" if len(self.players) == 1 else f"You and {len(self.players) - 1} other player(s) share"
        already = (
            f" {', '.join(self.already)} already go{'es' if len(self.already) == 1 else ''} to prison "
            "(fewest Pieces)."
            if self.already else ""
        )
        return (
            "DECISION: Prison choice.\n"
            f"- {who} the most Pieces, so you decide who goes to prison.{already}\n"
            f"- Choose {self.seats} player(s) from: {', '.join(self.candidates)}. You cannot choose "
            "yourself.\n"
            + ("- The deciders may talk privately first, then each votes. Most votes go to prison; ties "
               "are broken by a random draw.\n" if len(self.players) > 1 else "")
            + "- Your choice, and each decider's vote, is announced to everyone. The chosen players "
            "will know who sent them."
        )

    async def play(self, t: Tournament) -> Ranking:  # the engine drives this step directly
        raise NotImplementedError

    def private_view(self, player: str) -> dict[str, Any]:
        return {}

    def public_view(self) -> dict[str, Any]:
        return {"deciders": list(self.players), "candidates": list(self.candidates), "seats": self.seats,
                "already_in_prison": list(self.already)}

    def action_schema(self, player: str) -> type[BaseModel]:
        return SendAction

    def action_help(self, player: str) -> str:
        return f'Send {self.seats} player(s) to prison: {{"send": [<{self.seats} name(s) from {self.options(player)}>]}}'

    def options(self, player: str) -> list[str]:
        return [c for c in self.candidates if c != player]

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"send": list(c)} for c in itertools.combinations(self.options(player), self.seats)]

    def check_action(self, player: str, action: BaseModel) -> str | None:
        send = action.send
        if len(send) != self.seats or len(set(send)) != len(send):
            return f"Choose exactly {self.seats} different player(s)."
        if player in send:
            return "You cannot send yourself to prison."
        if set(send) - set(self.candidates):
            return f"You can only choose from {self.options(player)}."
        return None
