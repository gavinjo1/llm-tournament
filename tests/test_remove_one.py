from games.base import rank_by_score
from games.remove_one import round_winner


def test_lowest_unique_card_wins():
    assert round_winner({"A": 1, "B": 2, "C": 3}) == "A"


def test_duplicated_low_card_is_skipped():
    assert round_winner({"A": 1, "B": 1, "C": 2, "D": 3}) == "C"


def test_no_unique_card_means_no_winner():
    assert round_winner({"A": 2, "B": 2, "C": 5, "D": 5}) is None


def test_high_unique_card_can_win():
    assert round_winner({"A": 1, "B": 1, "C": 2, "D": 2, "E": 6}) == "E"


def test_rank_by_score_groups_ties():
    assert rank_by_score({"A": 2, "B": 0, "C": 2, "D": 1}) == [["A", "C"], ["D"], ["B"]]
