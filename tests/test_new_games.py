import random

import pytest

from agents.bots import RandomBot
from engine.tournament import TournamentConfig
from games.equation_group import split_pot
from games.equation_pyramid import EquationPyramid, all_values, evaluate
from games.halloween import HalloweenMonster
from games.mancala import split_pots
from games.sniper_holdem import CATEGORIES, best_hand, rank5
from games.triple_dice import combo, round_ranks
from games.virus import ROLE_SETS, VirusGame
from tests.helpers import events_of

import asyncio

from engine.tournament import Tournament


def play_one(game_cls, n, seed):
    """Play a single game directly, outside any tournament structure."""
    t = Tournament([RandomBot(seed + i) for i in range(n)], [game_cls], seed=seed,
                   config=TournamentConfig(start_pieces=1))
    t.game = game_cls(list(t.alive), t.rng)
    ranking = asyncio.run(t.game.play(t))
    return t, t.game, ranking


# ---------------------------------------------------------------- Virus


def test_virus_roles_match_player_count():
    for n, roles in ROLE_SETS.items():
        game = VirusGame([f"P{i}" for i in range(n)], random.Random(0))
        assert sorted(game.role.values()) == sorted(roles)


@pytest.mark.parametrize("seed", range(15))
def test_virus_game_outcome_is_consistent(seed):
    t, game, ranking = play_one(VirusGame, 7, seed)
    result = events_of(t, "virus_result")[0]["data"]
    roles = result["roles"]
    infected = set(result["infected"])
    assert all(roles[p] != "Terrorist" for p in infected)
    expected = "terrorists" if len(infected) >= 2 else "citizens"
    assert result["winner"] == expected
    rewards = game.main_rewards(ranking)
    for p, r in rewards.items():
        on_terror_side = roles[p] == "Terrorist" or p in infected
        assert r == (4 if (on_terror_side == (expected == "terrorists")) else 0)


def test_virus_roles_are_private():
    t, _, _ = play_one(VirusGame, 7, 1)
    for e in events_of(t, "role_info"):
        assert e["visible_to"] == [e["actor"]]
    assert events_of(t, "roles")[0]["visible_to"] == "god"


# ------------------------------------------------------------ Halloween


@pytest.mark.parametrize("seed", range(15))
def test_halloween_points_only_go_to_the_winning_party(seed):
    t, _, _ = play_one(HalloweenMonster, 5, seed)
    for e in events_of(t, "monster_result"):
        d = e["data"]
        if d["winner_party"] is None:
            assert d["allocation"] == {}
            continue
        members = d["parties"][d["winner_party"]]["members"]
        assert set(d["allocation"]) <= set(members)
        monster = next(m for m in events_of(t, "monster") if m["data"]["round"] == d["round"])["data"]
        assert sum(d["allocation"].values()) == monster["points"]
        assert d["parties"][d["winner_party"]]["power"] >= monster["strength"]


# --------------------------------------------------------- Mancala etc.


def test_mancala_split_rounds_down_and_crowding_hurts():
    gains = split_pots({"red": 9, "blue": 4, "green": 6}, {"A": "red", "B": "red", "C": "blue"})
    assert gains["A"]["red"] == gains["B"]["red"] == 4
    assert gains["C"]["blue"] == 4 and gains["C"]["red"] == 0


def test_group_equation_pot_split():
    stakes = {"A": 2, "B": 2, "C": 2, "D": 2}
    results = {"A": ("high", 1.0), "B": ("high", 2.0), "C": ("low", 1.0), "D": ("low", 3.0)}
    assert split_pot(8, stakes, results) == {"A": 4, "B": 0, "C": 4, "D": 0}
    # only one side declared: it takes everything; tied winners split by stake
    assert split_pot(9, {"A": 1, "B": 2}, {"A": ("low", 0.0), "B": ("low", 0.0)}) == {"A": 3, "B": 6}


# ---------------------------------------------------------- Sniper Hold'em


@pytest.mark.parametrize("cards, category", [
    (["AS", "KS", "QS", "JS", "TS"], "straight flush"),
    (["9H", "9D", "9S", "9C", "2H"], "four of a kind"),
    (["9H", "9D", "9S", "2C", "2H"], "full house"),
    (["2H", "7H", "9H", "JH", "KH"], "flush"),
    (["AS", "2D", "3H", "4C", "5S"], "straight"),
    (["9H", "9D", "9S", "3C", "2H"], "three of a kind"),
    (["9H", "9D", "3S", "3C", "2H"], "two pair"),
    (["9H", "9D", "4S", "3C", "2H"], "pair"),
    (["AH", "9D", "4S", "3C", "2H"], "high card"),
])
def test_hand_categories(cards, category):
    assert CATEGORIES[rank5(cards)[0]] == category


def test_hand_comparisons():
    assert rank5(["AS", "AD", "3H", "4C", "5S"]) > rank5(["KS", "KD", "QH", "JC", "9S"])
    assert rank5(["6S", "2D", "3H", "4C", "5S"]) > rank5(["AS", "2D", "3H", "4C", "5H"])  # 6-high > wheel
    assert best_hand(["AS", "AD", "AH", "KC", "KS", "2D"])[0] == 6  # full house from 6 cards


@pytest.mark.parametrize("seed", range(10))
def test_holdem_sniped_hands_never_win(seed):
    from games.sniper_holdem import SniperHoldem

    t, _, _ = play_one(SniperHoldem, 4, seed)
    for e in events_of(t, "holdem_result"):
        d = e["data"]
        for w in d["winners"]:
            assert w not in d["disqualified"] and w not in d["folded"]
        for p in d["disqualified"]:
            assert any(d["snipes"].get(q) == d["showdown"][p]["best"] for q in d["snipes"] if q != p)
        assert sum(e["data"]["chips"].values()) <= 4 * 20


# ------------------------------------------------------------ Triple Dice


def test_triple_dice_combos_and_ranks():
    assert combo([4, 4, 4])[0] == 3 and combo([3, 5, 4])[0] == 2 and combo([2, 2, 5])[0] == 1
    assert combo([1, 3, 6])[0] == 0
    ranks = round_ranks({"A": [4, 4, 4], "B": [2, 3, 6], "C": [5, 6, 4], "D": [2, 3, 6]})
    assert ranks == {"A": 1, "C": 2, "B": 3, "D": 3}


# --------------------------------------------------------- Equation Pyramid


def test_pyramid_evaluation_left_to_right():
    tiles = {"A": ("+", 5), "D": ("*", 3), "H": ("-", 2)}
    assert evaluate(tiles, ["A", "D", "H"]) == 13
    assert evaluate(tiles, ["H", "A", "D"]) == 21  # starts from H's number 2: (2 + 5) * 3


@pytest.mark.parametrize("seed", range(20))
def test_pyramid_targets_are_reachable(seed):
    game = EquationPyramid(["A", "B"], random.Random(seed))
    reachable = all_values(game.tiles)
    assert all(t in reachable for t in game.targets)
    assert len(set(game.targets)) == len(game.targets)
