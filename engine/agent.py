"""The interface every player implements: scripted bots now, LLMs later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["chat", "action", "will", "diary"]
Memory = Literal["full", "facts", "diary"]


@dataclass
class Observation:
    """Everything one player is allowed to know when it is asked to respond.

    kind:
      "chat"   -> respond with a ChatTurn (messages and transfers)
      "action" -> respond with {"private_reasoning": ..., "action": {...}}.
                  `action_help` says what is expected. `legal_actions` lists
                  every legal action, or is None when the action is free-form
                  (e.g. writing an equation).
      "will"   -> you were eliminated; respond with a WillTurn (transfers only)
      "diary"  -> the day is over; respond with a DiaryTurn (private notes kept
                  for the rest of the tournament)
    """

    kind: Kind
    you: str
    day: int
    game: str | None
    round: int | None
    rules: str
    private: dict[str, Any]
    public: dict[str, Any]
    history: list[dict[str, Any]]
    communication: Literal["none", "public", "private"]
    legal_actions: list[dict[str, Any]] | None = field(default_factory=list)
    action_help: str = ""
    exchange: tuple[int, int] | None = None
    """For chat: (current exchange, max exchanges) of this conversation."""
    life_price: int | None = None
    """For chat: the price of a life if this player may buy one now, else None."""
    sample_action: dict[str, Any] | None = None
    """For free-form actions: one valid example move. Used by scripted bots only;
    never shown to LLMs, so it cannot steer their choice."""
    last_error: str | None = None
    memory: Memory = "full"
    """How earlier days are shown (TournamentConfig.memory): "full" = every earlier
    message; "facts" = only key public results; "diary" = key results plus the
    player's own end-of-day diary entries."""


class RunHalted(Exception):
    """Stops the tournament; the run is logged as aborted with this reason."""


class AgentFailure(RunHalted):
    """An agent could not respond at all (e.g. its API kept failing).

    Unlike an invalid reply, this stops the tournament: filling the gap with
    random moves would make the run look valid when it is not.
    """


class StopRequested(RunHalted):
    """Someone asked the run to stop (the viewer's Stop button)."""


class Agent(ABC):
    """A player. Returns raw JSON (a dict, or a JSON string) for each request."""

    @property
    def label(self) -> str:
        """Who is behind this seat (bot type or model id). Never shown to players."""
        return type(self).__name__

    def usage_report(self) -> dict[str, Any] | None:
        """Calls, tokens and cost, for agents that use an API."""
        return None

    @abstractmethod
    async def act(self, obs: Observation) -> dict[str, Any] | str: ...
