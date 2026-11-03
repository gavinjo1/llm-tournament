import random
from fractions import Fraction

import pytest

from agents.bots import GenerousBot, LiarBot, LowestBot, RandomBot
from engine.agent import Agent
from engine.events import GOD
from games.equation_high_low import EquationHighLow, evaluate, random_expression
from games.schedule import DEFAULT_SCHEDULE
from games.time_auction import FINAL_BANK, FINAL_ROUNDS, TimeAuction
from tests.helpers import events_of, run, seat_of

# ------------------------------------------------------------- evaluate


def test_evaluate_valid_expressions():
    assert evaluate("(1+2)*3-4", [1, 2, 3, 4]) == 5
    assert evaluate("4 × 3 ÷ 2 − 1", [4, 3, 2, 1]) == 5
    assert evaluate("10/4+1-1", [10, 4, 1, 1]) == Fraction(5, 2)


@pytest.mark.parametrize(
    "expression, cards, message",
    [
        ("1+2+3", [1, 2, 3, 4], "exactly once"),
        ("1+2+3+4+4", [1, 2, 3, 4], "exactly once"),
        ("12+3+4", [1, 2, 3, 4], "exactly once"),
        ("1/(2-2)+3", [1, 2, 2, 3], "division by zero"),
        ("-1+2+3+4", [1, 2, 3, 4], "only your card numbers"),
        ("2**3+1+1", [2, 3, 1, 1], "only your card numbers"),
        ("__import__('os')", [1, 2, 3, 4], "only your card numbers"),
        ("1.5+2+3+4", [1, 2, 3, 4], "only your card numbers"),
        ("(1+2", [1, 2, 3, 4], "not a valid expression"),
        ("1+" * 60 + "1", [1, 1, 1, 1], "longer than"),
    ],
)
def test_evaluate_rejects_invalid(expression, cards, message):
    with pytest.raises(ValueError, match=message):
        evaluate(expression, cards)


def test_random_expression_is_always_valid():
    rng = random.Random(0)
    for _ in range(1000):
        cards = [rng.randint(1, 10) for _ in range(4)]
        evaluate(random_expression(cards, rng), cards)


# ------------------------------------------------------- final sub-games


class StandaloneEquation(EquationHighLow):
    final = True


class StandaloneAuction(TimeAuction):
    final = True

    def __init__(self, players, rng):
        super().__init__(players, rng, bank=FINAL_BANK, rounds=FINAL_ROUNDS, single_winner=True)


class BetBot(Agent):
    """Always bets the maximum, always calls; declares cards summed as high."""

    async def act(self, obs):
        if obs.kind != "action":
            return {}
        if obs.legal_actions is None:
            return {"action": {"target": "high", "expression": "+".join(map(str, obs.private["my_cards"]))}}
        bets = [a for a in obs.legal_actions if a.get("move") == "bet"]
        if bets:
            return {"action": bets[-1]}
        return {"action": {"move": "call"} if {"move": "call"} in obs.legal_actions else obs.legal_actions[0]}


class FoldBot(Agent):
    """Checks when possible, folds to any bet."""

    async def act(self, obs):
        if obs.kind != "action":
            return {}
        if {"move": "fold"} in (obs.legal_actions or []):
            return {"action": {"move": "fold"}}
        if obs.legal_actions is None:
            return {"action": {"target": "low", "expression": "+".join(map(str, obs.private["my_cards"]))}}
        return {"action": {"move": "check"}}


def test_folding_to_every_bet_loses_the_antes():
    bettor, folder = BetBot(), FoldBot()
    t, result = run([bettor, folder], [StandaloneEquation], seed=1)
    b, f = seat_of(t, bettor), seat_of(t, folder)
    hands = events_of(t, "hand_result")
    assert len(hands) == 3
    assert all(h["data"]["folded"] == f and h["data"]["winner"] == b for h in hands)
    assert hands[-1]["data"]["chips"] == {b: 13, f: 7}
    assert result["winner"] == b


@pytest.mark.parametrize("seed", range(30))
def test_equation_chips_are_conserved(seed):
    t, _ = run([RandomBot(seed), RandomBot(seed + 1)], [StandaloneEquation], seed=seed)
    for hand in events_of(t, "hand_result"):
        assert sum(hand["data"]["chips"].values()) == 20
        assert all(c >= 0 for c in hand["data"]["chips"].values())
        showdown = hand["data"].get("showdown")
        if showdown and hand["data"]["winner"]:
            loser = next(p for p in showdown if p != hand["data"]["winner"])
            assert showdown[hand["data"]["winner"]]["distance"] < showdown[loser]["distance"]


@pytest.mark.parametrize("seed", range(20))
def test_time_auction_bids_are_hidden_and_within_bank(seed):
    t, _ = run([RandomBot(seed), LowestBot()], [StandaloneAuction], seed=seed)
    spent = {p: 0 for p in t.alive + [e["data"]["player"] for e in events_of(t, "elimination")]}
    for e in events_of(t, "bids"):
        assert e["visible_to"] == GOD
        for p, bid in e["data"]["bids"].items():
            spent[p] += bid
            assert e["data"]["bank"][p] == FINAL_BANK - spent[p] >= 0
    assert all("bids" not in r["data"] for r in events_of(t, "auction_result"))


# ------------------------------------------------------ full tournament


def five_bots(seed):
    return [RandomBot(seed), LowestBot(), LiarBot(seed + 1), GenerousBot(seed + 2), RandomBot(seed + 3)]


@pytest.mark.parametrize("seed", range(40))
def test_full_tournament_produces_one_champion(seed):
    t, result = run(five_bots(seed), DEFAULT_SCHEDULE, seed=seed)
    # day 1 is the team day: no elimination
    assert [e["day"] for e in events_of(t, "elimination")] == [2, 3, 4, 5]
    assert len(result["alive"]) == 1 and result["winner"] == result["alive"][0]
    assert events_of(t, "champion")[0]["data"]["player"] == result["winner"]

    series = events_of(t, "final_game_result")
    assert 2 <= len(series) <= 3
    assert series[-1]["data"]["wins"][result["winner"]] == 2


@pytest.mark.parametrize("seed", range(20))
def test_final_chooser_has_more_pieces(seed):
    t, _ = run(five_bots(seed), DEFAULT_SCHEDULE, seed=seed)
    day4 = next(e for e in events_of(t, "day_start") if e["data"]["game"] == "Final")
    start = next(e for e in events_of(t, "game_start") if e["data"]["game"] == "Final")
    chooser = start["data"]["chooser"]
    # replay the morning-lounge transfers to get Pieces when the Final began
    pieces = dict(day4["data"]["pieces"])
    for e in events_of(t, "transfer"):
        if day4["seq"] < e["seq"] < start["seq"]:
            pieces[e["actor"]] -= e["data"]["pieces"]
            pieces[e["data"]["to"]] += e["data"]["pieces"]
    if len(set(pieces.values())) == 2:
        assert pieces[chooser] == max(pieces.values())
    else:
        assert events_of(t, "tie_break_draw")
    for choice in events_of(t, "first_player"):
        assert choice["actor"] == chooser


def test_full_tournament_is_deterministic():
    t1, _ = run(five_bots(3), DEFAULT_SCHEDULE, seed=3)
    t2, _ = run(five_bots(3), DEFAULT_SCHEDULE, seed=3)
    assert t1.log.events == t2.log.events
