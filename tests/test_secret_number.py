import asyncio
import random

import pytest

from agents.bots import GenerousBot, LiarBot, RandomBot
from engine.agent import Agent
from engine.events import GOD
from engine.tournament import Tournament
from games.secret_number import MAX_CLUES, SecretNumber
from tests.helpers import events_of, run, seat_of


class ClueBuyerBot(Agent):
    """Buys a clue every round at a fixed point, then guesses 50."""

    async def act(self, obs):
        if obs.kind != "action":
            return {}
        if "guess" in obs.action_help:
            return {"action": {"guess": 50}}
        if {"clue": 50} in obs.legal_actions:
            return {"action": {"clue": 50}}
        return {"action": {"clue": None}}


class OracleBot(Agent):
    """Cheats by reading the game state, to test the exact-guess bonus."""

    t = None

    async def act(self, obs):
        if obs.kind == "action" and obs.public["game"]["stage"] == "guess":
            return {"action": {"guess": self.t.game.numbers[obs.you]}}
        if obs.kind == "action":
            return {"action": {"clue": None}}
        return {}


def test_clues_are_truthful_private_and_cost_one_piece():
    buyer = ClueBuyerBot()
    t, _ = run([buyer, RandomBot(1), RandomBot(2), RandomBot(3)], [SecretNumber], seed=3)
    me = seat_of(t, buyer)
    number = events_of(t, "deal")[0]["data"]["numbers"][me]
    clues = [e for e in events_of(t, "clue_result") if e["actor"] == me]
    assert len(clues) == MAX_CLUES  # started with 3 Pieces, 3 rounds
    for clue in clues:
        assert clue["visible_to"] == [me]
        assert clue["data"]["answer"] == (number > 50)
    costs = [e for e in events_of(t, "pieces_change") if e["actor"] == me and e["data"]["delta"] == -1]
    assert len(costs) == MAX_CLUES


def test_clue_not_allowed_without_pieces():
    game = SecretNumber(["A", "B", "C", "D"], random.Random(0))

    class FakeTournament:
        pieces = {"A": 0, "B": 3, "C": 3, "D": 3}

    game.t = FakeTournament()
    assert game.legal_actions("A") == [{"clue": None}]
    assert len(game.legal_actions("B")) == 100


def test_players_cannot_see_their_own_number():
    spies = []

    class SpyBot(RandomBot):
        async def act(self, obs):
            spies.append(obs)
            return await super().act(obs)

    t, _ = run([SpyBot(0), RandomBot(1), RandomBot(2), RandomBot(3)], [SecretNumber])
    for obs in spies:
        if obs.game == "Secret Number" and "others_numbers" in obs.private:
            assert obs.you not in obs.private["others_numbers"]
            assert len(obs.private["others_numbers"]) == 3
        assert not [e for e in obs.history if e["type"] == "deal"]
    assert events_of(t, "deal")[0]["visible_to"] == GOD


def test_exact_guess_ranks_first_and_earns_bonus():
    oracle = OracleBot()
    t = Tournament([oracle, RandomBot(1), RandomBot(2), RandomBot(3)], [SecretNumber], seed=0)
    oracle.t = t
    asyncio.run(t.run())
    me = seat_of(t, oracle)
    assert events_of(t, "reveal")[0]["data"]["errors"][me] == 0
    assert events_of(t, "placement")[0]["data"]["ranking"][0] == [me]
    bonus = [e for e in events_of(t, "pieces_change") if e["data"]["reason"] == "exact guess bonus"]
    assert [e["actor"] for e in bonus] == [me]


@pytest.mark.parametrize("seed", range(20))
def test_secret_number_with_mixed_bots(seed):
    t, _ = run([RandomBot(seed), LiarBot(seed), GenerousBot(seed), RandomBot(seed + 1)], [SecretNumber], seed=seed)
    reveal = events_of(t, "reveal")[0]["data"]
    assert len(set(reveal["numbers"].values())) == 4
    assert all(1 <= g <= 100 for g in reveal["guesses"].values())
    assert len(events_of(t, "elimination")) == 1
