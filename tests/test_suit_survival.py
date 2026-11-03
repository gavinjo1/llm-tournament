import asyncio

import pytest

from agents.bots import RandomBot
from engine.agent import Agent
from engine.tournament import Tournament, TournamentConfig
from games.suit_survival import MAX_ROUNDS, SUITS, SuitSurvival
from tests.helpers import events_of


def play(agents, seed=0):
    t = Tournament(agents, [SuitSurvival], seed=seed, config=TournamentConfig())
    return t, asyncio.run(t.run())


class Oracle(Agent):
    """Always right (reads the game state): to test the round cap."""

    t = None

    async def act(self, obs):
        if obs.kind == "action":
            return {"action": {"guess": self.t.game.suits[obs.you]}}
        return {}


class AlwaysWrong(Agent):
    async def act(self, obs):
        if obs.kind == "action":
            right = self.t.game.suits[obs.you]
            return {"action": {"guess": next(s for s in SUITS if s != right)}}
        return {}


class Spy(RandomBot):
    def __init__(self, seed):
        super().__init__(seed)
        self.seen = []

    async def act(self, obs):
        self.seen.append(obs)
        return await super().act(obs)


@pytest.mark.parametrize("seed", range(30))
def test_wrong_guesses_are_eliminated_and_right_ones_survive(seed):
    t, result = play([RandomBot(seed + i) for i in range(7)], seed)
    out = {e["data"]["player"] for e in events_of(t, "elimination")}
    for r in events_of(t, "suit_result"):
        d = r["data"]
        for p, guess in d["guesses"].items():
            assert (guess != d["suits"][p]) == (p in d["wrong"])
        assert set(d["wrong"]) <= out
    assert result["winner"] is None or result["winner"] not in out


def test_players_see_others_suits_but_not_their_own():
    spy = Spy(0)
    t, _ = play([spy] + [RandomBot(i) for i in range(1, 7)], 3)
    me = next(p for p, a in t.agents.items() if a is spy)
    looked = [o for o in spy.seen if o.game == "Suit Survival" and "others_suits" in o.private]
    assert looked
    for obs in looked:
        assert me not in obs.private["others_suits"]
        assert not any(e["type"] == "suits" for e in obs.history)  # the deal is researchers-only


def test_everyone_wrong_in_one_round_means_nobody_wins():
    agents = [AlwaysWrong() for _ in range(4)]
    t = Tournament(agents, [SuitSurvival], seed=0)
    for a in agents:
        a.t = t
    result = asyncio.run(t.run())
    assert result["winner"] is None and result["alive"] == []
    assert events_of(t, "suit_result")[0]["data"]["everyone_out"]
    assert events_of(t, "no_winner")


def test_round_cap_ends_with_no_single_winner():
    agents = [Oracle() for _ in range(3)]
    t = Tournament(agents, [SuitSurvival], seed=0)
    for a in agents:
        a.t = t
    result = asyncio.run(t.run())
    assert len(events_of(t, "suit_result")) == MAX_ROUNDS
    assert result["winner"] is None and len(result["alive"]) == 3
    assert events_of(t, "no_winner")[0]["data"]["survivors"] == sorted(result["alive"])


def test_suits_are_redealt_every_round():
    agents = [Oracle() for _ in range(5)]
    t = Tournament(agents, [SuitSurvival], seed=1)
    for a in agents:
        a.t = t
    asyncio.run(t.run())
    deals = [tuple(sorted(e["data"]["suits"].items())) for e in events_of(t, "suits")]
    assert len(set(deals)) > 1


# ------------------------------------------------------- Hidden Player


from games.suit_survival import HiddenPlayerSuits


class Steered(Agent):
    """Right unless told to be wrong: decides exactly who dies each round."""

    t = None
    wrong_when = staticmethod(lambda game, me: False)

    async def act(self, obs):
        if obs.kind != "action":
            return {}
        game = self.t.game
        right = game.suits[obs.you]
        guess = next(s for s in SUITS if s != right) if self.wrong_when(game, obs.you) else right
        return {"action": {"guess": guess}}


def steered_game(n, wrong_when, seed=0):
    agents = [Steered() for _ in range(n)]
    t = Tournament(agents, [HiddenPlayerSuits], seed=seed)
    for a in agents:
        a.t = t
        a.wrong_when = wrong_when
    return t, asyncio.run(t.run())


def test_exactly_one_hidden_player_and_only_they_know():
    seen = []

    class Watch(RandomBot):
        async def act(self, obs):
            seen.append(obs)
            return await super().act(obs)

    t = Tournament([Watch(i) for i in range(6)], [HiddenPlayerSuits], seed=2)
    asyncio.run(t.run())
    hidden = events_of(t, "hidden_player")[0]["data"]["player"]
    assert events_of(t, "hidden_player")[0]["visible_to"] == "god"
    for obs in seen:
        if "your_role" in obs.private:
            assert obs.private["your_role"] == ("Hidden Player" if obs.you == hidden else "citizen")
        assert not any(e["type"] in ("hidden_player", "guesses", "suits") for e in obs.history)


def test_citizens_win_when_hidden_player_guesses_wrong():
    t, result = steered_game(6, lambda game, me: me == game.hidden and game.round == 2)
    clear = events_of(t, "game_clear")[0]["data"]
    assert len(clear["winners"]) == 5 and clear["hidden_player"] not in clear["winners"]
    assert sorted(result["alive"]) == sorted(clear["winners"]) and result["winner"] is None


def test_hidden_player_wins_when_left_with_one_other():
    # every round the lowest-lettered citizen dies
    def wrong(game, me):
        citizens = sorted(p for p in game.living() if p != game.hidden)
        return me == citizens[0]

    t, result = steered_game(5, wrong)
    hidden = events_of(t, "hidden_player")[0]["data"]["player"]
    assert events_of(t, "hidden_player_wins") and result["winner"] == hidden
    last = events_of(t, "elimination")[-1]["data"]
    assert last["reason"] == "left alone with the Hidden Player"


def test_guesses_stay_secret_only_eliminations_are_public():
    t, _ = steered_game(5, lambda game, me: me == game.hidden)
    assert events_of(t, "guesses")[0]["visible_to"] == "god"
    public = events_of(t, "hidden_round")[0]
    assert public["visible_to"] == "all" and "guesses" not in public["data"]


def test_hidden_player_needs_three():
    import random as _r
    with pytest.raises(ValueError):
        HiddenPlayerSuits(["A", "B"], _r.Random(0))
