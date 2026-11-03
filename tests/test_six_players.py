import pytest

from agents.bots import GenerousBot, LiarBot, LowestBot, RandomBot
from engine.events import GOD
from games.schedule import SCHEDULES
from games.time_auction import DAY_BANK, TimeAuction, round_winner
from tests.helpers import events_of, run


def test_single_highest_bid_wins():
    assert round_winner({"A": 30, "B": 25, "C": 0, "D": 29}) == "A"


def test_tied_highest_bid_gives_no_token():
    assert round_winner({"A": 30, "B": 30, "C": 50, "D": 50}) is None


@pytest.mark.parametrize("seed", range(20))
def test_four_player_time_auction_day(seed):
    t, _ = run([RandomBot(seed + i) for i in range(4)], [TimeAuction], seed=seed)
    assert len(events_of(t, "auction_result")) == 7
    spent = {}
    for e in events_of(t, "bids"):
        assert e["visible_to"] == GOD
        for p, bid in e["data"]["bids"].items():
            spent[p] = spent.get(p, 0) + bid
            assert e["data"]["bank"][p] == DAY_BANK - spent[p] >= 0
    assert len(events_of(t, "elimination")) == 1
    # ties in the day game are allowed (shared placement), not broken by a draw
    assert not events_of(t, "tie_break_draw") or len(events_of(t, "placement")[0]["data"]["ranking"]) < 4


def six_bots(seed):
    return [
        RandomBot(seed),
        LowestBot(),
        LiarBot(seed + 1),
        GenerousBot(seed + 2),
        RandomBot(seed + 3),
        RandomBot(seed + 4),
    ]


@pytest.mark.parametrize("seed", range(20))
def test_six_player_tournament_produces_one_champion(seed):
    t, result = run(six_bots(seed), SCHEDULES[6], seed=seed)
    days = [e["data"]["game"] for e in events_of(t, "day_start")]
    assert days == ["Team Treasury", "Remove One", "Secret Number", "Time Auction", "Doubt & Bet", "Final"]
    assert [e["day"] for e in events_of(t, "elimination")] == [2, 3, 4, 5, 6]
    assert result["winner"] is not None and len(result["alive"]) == 1


def test_five_player_schedule():
    assert [g.__name__ for g in SCHEDULES[5]] == [
        "TeamTreasury", "RemoveOne", "SecretNumber", "LiarsDice", "Final",
    ]
