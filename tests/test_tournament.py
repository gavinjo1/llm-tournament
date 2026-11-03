import asyncio
import json

import pytest

from agents.bots import GenerousBot, LiarBot, LowestBot, RandomBot
from engine.agent import Agent, Observation
from engine.events import GOD, EventLog
from engine.tournament import Tournament, TournamentConfig, placement_rewards
from games.remove_one import RemoveOne


def make_agents(seed=0):
    return [RandomBot(seed), LowestBot(), LiarBot(seed + 1), GenerousBot(seed + 2), RandomBot(seed + 3)]


def run(agents, seed=0, config=None, days=3, log=None):
    t = Tournament(agents, [RemoveOne] * days, seed=seed, config=config, log=log)
    return t, asyncio.run(t.run())


def events_of(t, type):
    return [e for e in t.log.events if e["type"] == type]


# ------------------------------------------------------------- placement


def test_placement_rewards_without_ties():
    ranking = [["A"], ["B"], ["C"], ["D"], ["E"]]
    assert placement_rewards(ranking) == {"A": 3, "B": 1, "C": 0, "D": -1, "E": -2}


def test_tied_players_get_average_rounded_down():
    # 2nd and 3rd tie: (1 + 0) / 2 = 0.5 -> 0
    assert placement_rewards([["A"], ["B", "C"], ["D"], ["E"]])["B"] == 0
    # 4th and 5th tie: (-1 + -2) / 2 = -1.5 -> -2
    assert placement_rewards([["A"], ["B"], ["C"], ["D", "E"]])["D"] == -2
    # everyone tied in a 3-player game: (3 + 0 - 2) / 3 -> 0
    assert placement_rewards([["A", "B", "C"]]) == {"A": 0, "B": 0, "C": 0}


def test_placement_rewards_reject_unknown_player_count():
    with pytest.raises(ValueError):
        placement_rewards([["A"], ["B"]])


# ------------------------------------------------------------ tournament


@pytest.mark.parametrize("seed", range(30))
def test_exactly_one_elimination_per_day(seed):
    t, result = run(make_agents(seed), seed=seed)
    eliminations = events_of(t, "elimination")
    assert [e["day"] for e in eliminations] == [1, 2, 3]
    assert len(result["alive"]) == 2
    assert all(p >= 0 for p in t.pieces.values())


@pytest.mark.parametrize("seed", range(30))
def test_pieces_are_conserved_by_transfers(seed):
    t, _ = run(make_agents(seed), seed=seed)
    # During a day, transfers only move Pieces between living players, so the
    # total changes only by the rewards (plus whatever clamping at 0 adds back).
    for day_start, placement in zip(events_of(t, "day_start"), events_of(t, "placement")):
        before = sum(day_start["data"]["pieces"].values())
        after_unclamped = before + sum(placement["data"]["rewards"].values())
        assert sum(placement["data"]["pieces"].values()) >= after_unclamped


def test_same_seed_gives_identical_log():
    t1, _ = run(make_agents(5), seed=5)
    t2, _ = run(make_agents(5), seed=5)
    assert t1.log.events == t2.log.events


def test_different_seeds_change_seating():
    t1, _ = run(make_agents(), seed=1)
    t2, _ = run(make_agents(), seed=2)
    seat1 = events_of(t1, "seating")[0]["data"]["agents"]
    seat2 = events_of(t2, "seating")[0]["data"]["agents"]
    assert seat1 != seat2


def test_each_round_has_one_card_per_player_and_hands_empty_at_end():
    t, _ = run(make_agents(), days=1)
    results = events_of(t, "round_result")
    assert len(results) == 6
    played = {}
    for r in results:
        assert len(r["data"]["plays"]) == 5
        for p, card in r["data"]["plays"].items():
            played.setdefault(p, []).append(card)
    assert all(sorted(cards) == [1, 2, 3, 4, 5, 6] for cards in played.values())


def test_log_file_is_valid_jsonl(tmp_path):
    path = tmp_path / "run.jsonl"
    with EventLog(path) as log:
        t, _ = run(make_agents(), log=log)
    lines = path.read_text().splitlines()
    assert len(lines) == len(t.log.events)
    assert [json.loads(line) for line in lines] == t.log.events


# ----------------------------------------------------------- visibility


class SpyBot(RandomBot):
    """Records every observation it receives."""

    def __init__(self, seed=0):
        super().__init__(seed)
        self.seen: list[Observation] = []

    async def act(self, obs):
        self.seen.append(obs)
        return await super().act(obs)


def test_players_never_see_god_events_or_others_private_messages():
    spy = SpyBot()
    t, _ = run([spy, GenerousBot(1), GenerousBot(2), LiarBot(3), RandomBot(4)], days=1)
    me = next(p for p, a in t.agents.items() if a is spy)
    for obs in spy.seen:
        for event in obs.history:
            assert event["visible_to"] != GOD
            if isinstance(event["visible_to"], list):
                assert me in event["visible_to"]
    # GenerousBots did send private messages, so the filter was actually exercised
    assert events_of(t, "private_message")


def test_players_see_own_hand_only():
    spy = SpyBot()
    t, _ = run([spy, RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], days=1)
    first = next(o for o in spy.seen if o.kind == "action")
    assert first.private["hand"] == [1, 2, 3, 4, 5, 6]
    assert "hand" not in first.public["game"]


# ------------------------------------------------- invalid output handling


class FaultyBot(Agent):
    """Returns garbage for every request."""

    async def act(self, obs):
        return "this is not json"


class OverspenderBot(Agent):
    """Tries to give away more Pieces than it owns."""

    async def act(self, obs):
        if obs.kind == "chat":
            target = next(p for p in obs.public["alive"] if p != obs.you)
            return {"transfers": [{"to": target, "pieces": 99}]}
        if obs.kind == "action":
            return {"action": obs.legal_actions[0]}
        return {}


def test_invalid_output_is_retried_then_defaulted():
    t, _ = run([FaultyBot(), RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], days=1)
    faulty = next(p for p, a in t.agents.items() if isinstance(a, FaultyBot))
    invalid = [e for e in events_of(t, "invalid_output") if e["actor"] == faulty]
    defaults = [e for e in events_of(t, "default_action") if e["actor"] == faulty]
    assert invalid and defaults
    assert len(invalid) == 3 * len(defaults)  # 1 try + 2 retries each time
    assert all(e["visible_to"] == GOD for e in invalid)
    # it still played a legal card every round
    results = events_of(t, "round_result")
    assert all(faulty in r["data"]["plays"] for r in results)


def test_error_message_is_given_back_on_retry():
    class LearnerBot(OverspenderBot):
        def __init__(self):
            self.errors: list[str] = []

        async def act(self, obs):
            if obs.last_error:
                self.errors.append(obs.last_error)
                return {}
            return await super().act(obs)

    bot = LearnerBot()
    t, _ = run([bot, RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], days=1)
    assert bot.errors and "only have" in bot.errors[0]
    assert not events_of(t, "default_action")


def test_overspending_transfer_is_rejected():
    t, _ = run([OverspenderBot(), RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], days=1)
    assert not [e for e in events_of(t, "transfer") if e["data"]["pieces"] == 99]
    assert events_of(t, "invalid_output")


# ------------------------------------------------- communication settings


def test_no_communication_means_no_chat():
    t, _ = run(make_agents(), config=TournamentConfig(communication="none"))
    for type in ("public_message", "private_message", "transfer"):
        assert not [e for e in events_of(t, type) if not e["data"].get("last_will")]


def test_private_messages_rejected_in_public_mode():
    t, _ = run(
        [GenerousBot(1), GenerousBot(2), RandomBot(3), RandomBot(4), RandomBot(5)],
        config=TournamentConfig(communication="public"),
    )
    assert not events_of(t, "private_message")
    # GenerousBot respects the mode, so it never produced invalid output
    assert not events_of(t, "invalid_output")


# ------------------------------------------------------- elimination


def test_last_will_gives_pieces_to_living_players():
    for seed in range(30):
        t, _ = run([GenerousBot(i) for i in range(5)], seed=seed)
        wills = [e for e in events_of(t, "transfer") if e["data"]["last_will"]]
        for will in wills:
            eliminated = [e["data"]["player"] for e in events_of(t, "elimination") if e["day"] == will["day"]]
            assert will["actor"] in eliminated
            assert will["data"]["to"] not in eliminated
        if wills:
            return
    pytest.fail("No Last Will happened in 30 seeds")


def test_eliminated_player_had_fewest_pieces():
    for seed in range(30):
        t, _ = run(make_agents(seed), seed=seed)
        for placement, elim in zip(events_of(t, "placement"), events_of(t, "elimination")):
            pieces = placement["data"]["pieces"]
            assert pieces[elim["data"]["player"]] == min(pieces.values())
