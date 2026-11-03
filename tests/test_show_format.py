import asyncio
import random
import re

import pytest

from agents.bots import GenerousBot, LiarBot, LowestBot, RandomBot
from engine.agent import Agent
from engine.tournament import Tournament, TournamentConfig
from games.show import MAIN_POOL, PRISON_POOL, draw
from tests.helpers import events_of


def show_config(**overrides):
    return TournamentConfig(format="show", start_pieces=1, **overrides)


def seven_bots(seed):
    return [RandomBot(seed), LowestBot(), LiarBot(seed + 1), GenerousBot(seed + 2),
            RandomBot(seed + 3), RandomBot(seed + 4), LowestBot()]


def play(agents, seed=0, **config):
    t = Tournament(agents, seed=seed, config=show_config(**config))
    return t, asyncio.run(t.run())


# ------------------------------------------------------------- structure


@pytest.mark.parametrize("seed", range(25))
def test_show_tournament_runs_to_one_champion(seed):
    t, result = play(seven_bots(seed), seed)
    assert result["winner"] and len(result["alive"]) == 1
    assert not events_of(t, "invalid_output")
    for e in events_of(t, "elimination"):
        assert e["data"].get("reason") in (
            None, "lost the prison match", "0 Pieces after the main match", "0 Pieces at the end of the day"
        )


@pytest.mark.parametrize("seed", range(25))
def test_prison_rules(seed):
    t, _ = play(seven_bots(seed), seed)
    events = t.log.events
    for prison in events_of(t, "prison"):
        d = prison["data"]
        before = next(e for e in reversed(events) if e["type"] == "placement" and e["seq"] < prison["seq"])
        alive = [p for p in d["pieces"]]
        after_main = {p: before["data"]["pieces"][p] for p in alive}
        prisoners = d["prisoners"]
        assert len(prisoners) == 2 and prison["visible_to"] == "all"
        low = min(after_main.values())
        poorest = [p for p in alive if after_main[p] == low]
        if len(poorest) <= 2:
            # the poorest go automatically; anyone else may fill the other seat
            assert sorted(d["automatic"]) == sorted(poorest) and set(poorest) <= set(prisoners)
        else:
            # more tied for fewest than seats: the leaders choose among them
            assert d["automatic"] == [] and set(prisoners) <= set(poorest)
        if len(d["automatic"]) < 2:
            top = max(after_main.values())
            assert d["deciders"] and all(after_main[p] == top for p in d["deciders"])
            assert set(d["votes"]) == set(d["deciders"])
            for decider, picks in d["votes"].items():
                assert decider not in picks  # nobody sends themselves
                assert set(picks) <= set(d["candidates"])
        else:
            assert not d["deciders"]
        result = next(e for e in events if e["type"] == "prison_result" and e["seq"] > prison["seq"])
        out = next(e for e in events if e["type"] == "elimination" and e["seq"] > result["seq"])
        assert out["data"]["player"] == result["data"]["loser"] in prisoners
        assert out["data"]["reason"] == "lost the prison match"


@pytest.mark.parametrize("seed", range(25))
def test_zero_pieces_is_elimination_except_on_day_one(seed):
    t, _ = play(seven_bots(seed), seed)
    for e in events_of(t, "elimination"):
        if e["data"].get("reason", "").startswith("0 Pieces"):
            assert e["day"] > 1


def test_main_match_table():
    t = Tournament(seven_bots(0), seed=0, config=show_config())
    assert t._main_table(7) == [4, 3, 2, 1, 0, -1, -2]
    assert t._main_table(3) == [4, 3, -2]  # losses only in the lower half


def test_everyone_starts_with_one_piece_and_lives_are_off():
    seen = []

    class Spy(RandomBot):
        async def act(self, obs):
            seen.append(obs)
            return await super().act(obs)

    t, _ = play([Spy(0)] + seven_bots(1)[1:], 1)
    assert set(events_of(t, "tournament_start")[0]["data"]["pieces"].values()) == {1}
    assert all(o.life_price is None for o in seen)


def test_zero_pieces_means_elimination():
    class GiveAwayBot(Agent):
        """Gives its only Piece away in the first conversation."""

        async def act(self, obs):
            if obs.kind == "chat" and obs.private["pieces"] > 0:
                other = next(p for p in obs.public["in_this_conversation"] if p != obs.you)
                return {"transfers": [{"to": other, "pieces": obs.private["pieces"]}]}
            if obs.kind == "action":
                return {"action": obs.sample_action if obs.legal_actions is None else obs.legal_actions[0]}
            return {}

    giver = GiveAwayBot()
    t, _ = play([giver] + seven_bots(2)[1:], 2)
    me = next(p for p, a in t.agents.items() if a is giver)
    # day 1 is safe; the giver (0 Pieces) has the fewest Pieces, so goes to prison or
    # is out by day 2 at the latest
    out = next(e for e in events_of(t, "elimination") if e["data"]["player"] == me)
    first_prison = events_of(t, "prison")[0]["data"]["prisoners"]
    assert me in first_prison or out["day"] == 2


# --------------------------------------------------- information rules


def test_players_only_ever_see_the_current_games_rules():
    seen = []

    class Spy(RandomBot):
        async def act(self, obs):
            seen.append(obs)
            return await super().act(obs)

    names = {g.name for g in MAIN_POOL + PRISON_POOL}
    for seed in range(6):
        seen.clear()
        play([Spy(seed)] + seven_bots(seed)[1:], seed)
        for obs in seen:
            headers = re.findall(r"^GAME: ([^.\n(]+)", obs.rules, re.M)
            if obs.game in (None, "Final", "Prison Choice"):
                continue
            assert len(headers) == 1, (obs.game, headers)
            others = names - {obs.game}
            assert not any(f"GAME: {n}" in obs.rules for n in others)


def test_prison_conversations_are_private_to_prisoners():
    asked_in_prison = []

    class Watch(RandomBot):
        async def act(self, obs):
            if obs.public.get("phase") == "prison":
                asked_in_prison.append(obs.you)
            return await super().act(obs)

    t, _ = play([Watch(i) for i in range(7)], 4)
    for prison in events_of(t, "prison_start"):
        prisoners = set(prison["data"]["players"])
        end = next((e for e in t.log.events if e["type"] == "prison_result" and e["seq"] > prison["seq"]), None)
        window = [e for e in t.log.events if prison["seq"] < e["seq"] < end["seq"]]
        for e in window:
            if e["type"] in ("public_message", "private_message", "conversation_start"):
                assert set(e["visible_to"]) <= prisoners
    assert set(asked_in_prison) <= {p for e in events_of(t, "prison_start") for p in e["data"]["players"]}


# ------------------------------------------------------------- the draw


def test_draw_fits_player_count_and_avoids_repeats():
    rng = random.Random(0)
    used: set[str] = set()
    picks = [draw(MAIN_POOL, 7, used, rng) for _ in range(4)]
    assert all(g.min_players <= 7 <= g.max_players for g in picks)
    assert len({g.name for g in picks}) == 4  # four different games while fresh ones remain
    for n in (2, 3, 4):
        assert draw(PRISON_POOL, n, set(), rng).min_players <= n


def test_every_pooled_game_gets_played_across_seeds():
    played = set()
    for seed in range(40):
        t, _ = play(seven_bots(seed), seed)
        played |= {e["data"]["game"] for e in events_of(t, "day_start") + events_of(t, "prison_start")}
    assert {g.name for g in MAIN_POOL + PRISON_POOL} <= played


@pytest.mark.parametrize("seed", range(10))
def test_twelve_player_show_tournament(seed):
    agents = [RandomBot(seed + i) if i % 2 else GenerousBot(seed + i) for i in range(12)]
    t, result = play(agents, seed)
    assert result["winner"] and not events_of(t, "invalid_output")
    assert events_of(t, "day_start")[0]["data"]["players"].__len__() == 12


def test_full_tie_in_a_main_match_changes_no_pieces():
    from engine.tournament import placement_rewards

    t = Tournament(seven_bots(0), seed=0, config=show_config())
    table = t._main_table(7)
    # partial ties round toward zero: (-3 + -5) / 2 = -4, (0 + -1) / 2 -> 0, not -1
    tied = placement_rewards([["A"], ["B"], ["C"], ["D", "E"], ["F"], ["G"]], table, toward_zero=True)
    assert tied["D"] == 0


# ------------------------------------------------ prison ties and phase text


class TieGame:
    """A stand-in prison match that always ends in a full tie."""

    name = "Tie Game"
    min_players, max_players = 2, 4
    final = False

    def __init__(self, players, rng):
        self.players = list(players)

    async def play(self, t):
        return [list(self.players)]


def test_tied_prison_match_eliminates_exactly_one_and_pays_the_survivor(monkeypatch):
    from games import show

    monkeypatch.setattr(show, "PRISON_POOL", [TieGame])
    t = Tournament(seven_bots(3), seed=3, config=show_config())
    for p in t.alive:
        t.pieces[p] = 3
    poor = t.alive[:2]
    for p in poor:
        t.pieces[p] = 0
    t.day = 2
    asyncio.run(t._prison_match(poor, set()))
    result = events_of(t, "prison_result")[-1]["data"]
    survivor = result["winner"]
    assert result["loser"] in poor and survivor in poor and survivor != result["loser"]
    assert t.pieces[survivor] == 1  # the draw's survivor gets the winner's Piece
    t._eliminate_broke("0 Pieces at the end of the day")
    assert survivor in t.alive and result["loser"] not in t.alive


def test_agents_are_told_the_real_prison_rules():
    t = Tournament(seven_bots(0), seed=0, config=show_config())
    for phase in ("main", "prison"):
        t.phase = phase
        t.game = MAIN_POOL[1](list(t.alive), t.rng)
        rules = t.observe(t.alive[0], "chat").rules
        assert "lower half by Pieces goes to prison" not in rules
        assert "random draw (not Pieces) decides who loses" in rules


def test_leader_may_send_anyone_but_not_themselves():
    from games.prison_choice import PrisonChoice

    game = PrisonChoice(["Player A"], ["Player A", "Player B", "Player C"], 1, ["Player D"], random.Random(0))
    assert {"send": ["Player A"]} not in game.legal_actions("Player A")
    assert game.check_action("Player A", game.action_schema("Player A")(send=["Player A"]))
    assert game.check_action("Player A", game.action_schema("Player A")(send=["Player B"])) is None
    assert "already goes to prison (fewest Pieces)" in game.rules and "cannot choose yourself" in game.rules


def test_rich_leader_can_send_a_rich_rival():
    class Sender(RandomBot):
        """Always sends the richest other player."""

        async def act(self, obs):
            if obs.kind == "action" and obs.game == "Prison Choice":
                others = {p: n for p, n in obs.public["pieces"].items() if p != obs.you}
                options = obs.public["game"]["candidates"]
                target = max((p for p in options if p != obs.you), key=lambda p: others.get(p, -1))
                return {"action": {"send": [target]}}
            return await super().act(obs)

    t = Tournament([Sender(i) for i in range(7)], seed=0, config=show_config())
    pieces = [1, 2, 3, 4, 5, 6, 9]
    for p, n in zip(t.alive, pieces):
        t.pieces[p] = n
    t.day = 2
    prisoners = asyncio.run(t._choose_prisoners())
    assert prisoners == sorted([t.alive[0], t.alive[5]])  # the poorest, and the leader's richest rival
