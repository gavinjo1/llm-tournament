import random

import pytest

from agents.bots import LowestBot, RandomBot
from games.liars_dice import LiarsDice
from tests.helpers import events_of, run


def test_first_bid_has_no_doubt_option():
    game = LiarsDice(["A", "B", "C"], random.Random(0))
    legal = game.legal_actions("A")
    assert {"doubt": True} not in legal
    assert len(legal) == 12 * 6  # quantities 1-12, faces 1-6


def test_new_bid_must_be_higher():
    game = LiarsDice(["A", "B", "C"], random.Random(0))
    game.bids = [{"player": "A", "quantity": 3, "face": 4}]
    legal = game.legal_actions("B")
    assert {"quantity": 3, "face": 4} not in legal
    assert {"quantity": 3, "face": 3} not in legal
    assert {"quantity": 2, "face": 6} not in legal
    assert {"quantity": 3, "face": 5} in legal
    assert {"quantity": 4, "face": 1} in legal
    assert {"doubt": True} in legal


def test_highest_possible_bid_leaves_only_doubt():
    game = LiarsDice(["A", "B"], random.Random(0), dice_per_player=3)
    game.bids = [{"player": "A", "quantity": 6, "face": 6}]
    assert game.legal_actions("B") == [{"doubt": True}]


@pytest.mark.parametrize("seed", range(30))
def test_doubts_resolve_correctly(seed):
    t, _ = run([RandomBot(seed), RandomBot(seed + 1), LowestBot()], [LiarsDice], seed=seed)
    counts = {p: 4 for p in t.log.events[0]["data"]["players"]}
    for doubt in events_of(t, "doubt"):
        d = doubt["data"]
        actual = sum(dice.count(d["bid"]["face"]) for dice in d["dice"].values())
        assert d["count"] == actual
        expected_loser = d["doubter"] if actual >= d["bid"]["quantity"] else d["bid"]["player"]
        assert d["loser"] == expected_loser
        counts[expected_loser] -= 1
        assert d["dice_count"] == counts
    # game ended with exactly one player holding dice
    assert sum(1 for c in counts.values() if c > 0) == 1
    ranking = events_of(t, "placement")[0]["data"]["ranking"]
    out = [e["data"]["player"] for e in events_of(t, "out_of_dice")]
    assert [g[0] for g in ranking[1:]] == list(reversed(out))


@pytest.mark.parametrize("seed", range(10))
def test_bids_strictly_increase_within_a_round(seed):
    t, _ = run([RandomBot(seed), RandomBot(seed + 1), RandomBot(seed + 2)], [LiarsDice], seed=seed)
    last = None
    for e in t.log.events:
        if e["type"] == "roll":
            last = None
        elif e["type"] == "bid":
            bid = (e["data"]["quantity"], e["data"]["face"])
            assert last is None or bid > last
            last = bid
