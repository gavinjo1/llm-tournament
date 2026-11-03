"""Base class for a day's game."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from engine.tournament import Tournament


Ranking = list[list[str]]
"""Placement, best first. Each inner list is a group of tied players."""


class Game(ABC):
    name: ClassVar[str]
    rules: str
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    final: ClassVar[bool] = False
    """A final awards no Pieces: the last-ranked player is simply eliminated."""
    eliminates: ClassVar[bool] = True
    """False for a day without placement rewards or elimination (the bonding day).
    Such a game pays out Pieces itself through t.adjust_pieces()."""
    self_eliminating: ClassVar[bool] = False
    """True for a game that eliminates players itself (t.eliminate) and decides
    the tournament: no rewards or end-of-day elimination follow it."""
    lounge_exchanges: ClassVar[int | None] = None
    """Overrides the config's morning-lounge conversation length for this day."""

    def __init__(self, players: list[str], rng: random.Random) -> None:
        if not self.min_players <= len(players) <= self.max_players:
            raise ValueError(
                f"{self.name} needs {self.min_players}-{self.max_players} players, "
                f"got {len(players)}"
            )
        self.players = list(players)
        self.rng = rng

    @abstractmethod
    async def play(self, t: Tournament) -> Ranking:
        """Run the game. Use t.chat_phase() and t.collect_actions()."""

    @abstractmethod
    def private_view(self, player: str) -> dict[str, Any]:
        """Hidden information only this player may see."""

    @abstractmethod
    def public_view(self) -> dict[str, Any]:
        """Game state every player may see."""

    @abstractmethod
    def action_schema(self, player: str) -> type[BaseModel]:
        """The model this player's action must match right now."""

    @abstractmethod
    def action_help(self, player: str) -> str:
        """One line telling the player what action is expected right now."""

    @abstractmethod
    def legal_actions(self, player: str) -> list[dict[str, Any]] | None:
        """Every action this player may take right now, or None if the action is
        free-form (then check_action and random_action must be overridden)."""

    def main_rewards(self, ranking: Ranking) -> dict[str, int] | None:
        """Show format: Pieces this main match gives, or None for the usual table."""
        return None

    def check_action(self, player: str, action: BaseModel) -> str | None:
        """Return an error message if the action is illegal, else None."""
        legal = self.legal_actions(player)
        if legal is None:
            raise NotImplementedError("free-form actions need their own check_action")
        schema = self.action_schema(player)
        if action.model_dump() not in [schema.model_validate(a).model_dump() for a in legal]:
            return f"Illegal action {action.model_dump(exclude_none=True)}. {self.action_help(player)}"
        return None

    def random_action(self, player: str, rng: random.Random) -> dict[str, Any]:
        """A uniformly random legal action, used when a player's output stays invalid."""
        legal = self.legal_actions(player)
        if legal is None:
            raise NotImplementedError("free-form actions need their own random_action")
        return rng.choice(legal)


def rank_by_score(scores: dict[str, int | float]) -> Ranking:
    """Highest score first; equal scores are tied."""
    ranking: Ranking = []
    for score in sorted(set(scores.values()), reverse=True):
        ranking.append(sorted(p for p, s in scores.items() if s == score))
    return ranking
