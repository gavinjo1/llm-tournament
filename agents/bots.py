"""Scripted bots: test dummies while building, baselines in experiments.

Bots return plain dicts, exactly like an LLM's parsed JSON, so they go through
the same validation path.
"""

from __future__ import annotations

import random
from typing import Any

from engine.agent import Agent, Observation


def random_action(obs: Observation, rng: random.Random) -> dict[str, Any]:
    """A random legal action; free-form actions use the game's own example move."""
    if obs.legal_actions is None:
        assert obs.sample_action is not None
        return obs.sample_action
    return rng.choice(obs.legal_actions)


class RandomBot(Agent):
    """Silent; plays a random legal action."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    async def act(self, obs: Observation) -> dict[str, Any]:
        if obs.kind == "action":
            return {"action": random_action(obs, self.rng)}
        return {}


class LowestBot(Agent):
    """Silent; always plays the first legal action. Games list actions lowest
    first, so this is the lowest card, the lowest bid, no clue, guess 1."""

    def __init__(self, seed: int = 0) -> None:
        pass

    async def act(self, obs: Observation) -> dict[str, Any]:
        if obs.kind != "action":
            return {}
        if obs.legal_actions is None:
            return {"action": obs.sample_action}
        return {"action": obs.legal_actions[0]}


class LiarBot(Agent):
    """Promises cooperation, announces a card each round, then plays a different one."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self.promised: dict[tuple[int, int | None], int] = {}

    async def act(self, obs: Observation) -> dict[str, Any]:
        key = (obs.day, obs.round)
        if obs.kind == "chat":
            hand = obs.private.get("hand")
            if obs.round is None or not hand:
                return {
                    "private_reasoning": "Sound cooperative so others trust me.",
                    "public_message": "Let's take turns so everyone scores. I promise to follow the plan.",
                }
            card = self.rng.choice(hand)
            self.promised[key] = card
            return {
                "private_reasoning": f"Announce {card}, then play something else.",
                "public_message": f"I will play {card} this round.",
            }
        if obs.kind == "action":
            promised = self.promised.get(key)
            if promised is None or obs.legal_actions is None:
                return {"action": random_action(obs, self.rng)}
            options = [a for a in obs.legal_actions if a.get("card") != promised]
            return {
                "private_reasoning": f"I said {promised}; playing something else.",
                "action": self.rng.choice(options or obs.legal_actions),
            }
        return {}


class GenerousBot(Agent):
    """Offers alliances and gives away Pieces while keeping at least 1."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    async def act(self, obs: Observation) -> dict[str, Any]:
        reachable = obs.public.get("in_this_conversation", obs.public["alive"])
        others = [p for p in reachable if p != obs.you]
        if obs.kind == "action":
            return {"action": random_action(obs, self.rng)}
        if not others or obs.kind == "diary":
            return {}
        if obs.kind == "will":
            return {
                "private_reasoning": "Reward someone on my way out.",
                "transfers": [{"to": self.rng.choice(others), "pieces": obs.private["pieces"]}],
            }
        ally = self.rng.choice(others)
        turn: dict[str, Any] = {
            "private_messages": [{"to": ally, "text": "Ally? I am sending you a Piece."}]
            if obs.communication == "private"
            else [],
        }
        if obs.private["pieces"] >= 2:
            turn["transfers"] = [{"to": ally, "pieces": 1}]
        return turn


BOTS: dict[str, type[Agent]] = {
    "random": RandomBot,
    "lowest": LowestBot,
    "liar": LiarBot,
    "generous": GenerousBot,
}
