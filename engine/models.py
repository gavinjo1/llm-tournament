"""Schemas for agent responses.

Agents (LLMs or bots) return plain JSON. These models validate the shape and
the word limits from the spec (§2.3). Checks that depend on the game state,
such as "is this player alive" or "do you own that many Pieces", live in the
tournament engine.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PUBLIC_MESSAGE_WORDS = 80
PRIVATE_MESSAGE_WORDS = 60
MAX_PRIVATE_MESSAGES = 2
DIARY_SUMMARY_WORDS = 150
DIARY_NOTE_WORDS = 50


def _check_words(text: str, limit: int) -> str:
    if len(text.split()) > limit:
        raise ValueError(f"message is longer than {limit} words")
    return text


class Transfer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    pieces: int = Field(ge=1)


class PrivateMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _limit(cls, text: str) -> str:
        return _check_words(text, PRIVATE_MESSAGE_WORDS)


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    private_reasoning: str = ""
    public_message: str | None = None
    private_messages: list[PrivateMessage] = Field(
        default_factory=list, max_length=MAX_PRIVATE_MESSAGES
    )
    transfers: list[Transfer] = Field(default_factory=list)
    buy_life: bool = False

    @field_validator("public_message")
    @classmethod
    def _limit(cls, text: str | None) -> str | None:
        if text is not None and not text.strip():
            return None
        return text if text is None else _check_words(text, PUBLIC_MESSAGE_WORDS)


class WillTurn(BaseModel):
    """An eliminated player's Last Will: transfers only."""

    model_config = ConfigDict(extra="forbid")

    private_reasoning: str = ""
    transfers: list[Transfer] = Field(default_factory=list)


class DiaryTurn(BaseModel):
    """End-of-day private diary: a summary of the day and a note per player.

    It replaces the day's raw conversations in the player's later prompts."""

    model_config = ConfigDict(extra="forbid")

    private_reasoning: str = ""
    summary: str = ""
    players: dict[str, str] = Field(default_factory=dict)

    @field_validator("summary")
    @classmethod
    def _limit_summary(cls, text: str) -> str:
        return _check_words(text, DIARY_SUMMARY_WORDS)

    @field_validator("players")
    @classmethod
    def _limit_notes(cls, notes: dict[str, str]) -> dict[str, str]:
        for player, text in notes.items():
            if len(text.split()) > DIARY_NOTE_WORDS:
                raise ValueError(f"the note on {player} is longer than {DIARY_NOTE_WORDS} words")
        return notes


class ActionEnvelope(BaseModel):
    """Wraps a game action. `action` is validated by the game's own model."""

    model_config = ConfigDict(extra="forbid")

    private_reasoning: str = ""
    action: dict[str, Any]
