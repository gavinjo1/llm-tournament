import pytest

from agents.bots import RandomBot
from engine.agent import Agent
from engine.tournament import Tournament, TournamentConfig
from games.remove_one import RemoveOne
from games.schedule import DEFAULT_SCHEDULE
from games.team_treasury import BONUS, TeamTreasury, team_goal
from tests.helpers import events_of, run, seat_of


class ContributorBot(Agent):
    """Puts the maximum into the treasury every round."""

    async def act(self, obs):
        if obs.kind == "action":
            return {"action": obs.legal_actions[-1]}
        return {}


class FreeRiderBot(Agent):
    """Never contributes."""

    async def act(self, obs):
        if obs.kind == "action":
            return {"action": obs.legal_actions[0]}
        return {}


class LifeBuyerBot(Agent):
    """Buys a life whenever it may, and records what it was offered."""

    def __init__(self):
        self.offers = []

    async def act(self, obs):
        if obs.kind == "chat":
            self.offers.append((obs.game, obs.life_price))
            if obs.life_price is not None and obs.private["pieces"] >= obs.life_price:
                return {"buy_life": True}
            return {}
        if obs.kind == "action":
            return {"action": obs.legal_actions[0] if obs.legal_actions else {}}
        return {}


# ---------------------------------------------------------- Team Treasury


def test_goal_scales_with_players():
    assert team_goal(5) == 8 and team_goal(6) == 10 and team_goal(4) == 6


def test_team_goal_reached_pays_everyone_including_free_riders():
    rider = FreeRiderBot()
    t, _ = run([ContributorBot(), ContributorBot(), ContributorBot(), ContributorBot(), rider], [TeamTreasury])
    result = events_of(t, "team_result")[0]["data"]
    assert result["success"] and result["total"] >= team_goal(5)
    me = seat_of(t, rider)
    assert t.pieces[me] == 3 + BONUS  # paid nothing, got the bonus
    for p, n in t.pieces.items():
        if p != me:
            assert n == 3 - 3 + BONUS  # put in everything they had (2 then 1), got the bonus


def test_team_goal_missed_loses_contributions():
    t, _ = run([ContributorBot(), FreeRiderBot(), FreeRiderBot(), FreeRiderBot(), FreeRiderBot()], [TeamTreasury])
    result = events_of(t, "team_result")[0]["data"]
    assert not result["success"] and result["total"] == 3
    assert sorted(t.pieces.values()) == [0, 3, 3, 3, 3]


def test_team_day_has_no_placement_or_elimination():
    t, result = run([RandomBot(i) for i in range(5)], [TeamTreasury])
    assert not events_of(t, "placement") and not events_of(t, "elimination")
    assert len(result["alive"]) == 5
    assert events_of(t, "day_end")


def test_contributions_are_revealed_by_name_each_round():
    t, _ = run([RandomBot(i) for i in range(5)], [TeamTreasury])
    rounds = events_of(t, "contributions")
    assert len(rounds) == 3
    assert all(r["visible_to"] == "all" and len(r["data"]["contributions"]) == 5 for r in rounds)


def test_bonding_day_has_a_longer_first_conversation():
    class Chatty(RandomBot):
        async def act(self, obs):
            return {"public_message": "hi"} if obs.kind == "chat" else await super().act(obs)

    t, _ = run([Chatty(0), RandomBot(1), RandomBot(2)], [TeamTreasury, RemoveOne])
    lounges = [e for e in events_of(t, "conversation_start") if e["round"] is None]
    assert [e["data"]["max_exchanges"] for e in lounges] == [10, 6]


@pytest.mark.parametrize("seed", range(20))
def test_full_five_day_tournament(seed):
    t, result = run([RandomBot(seed + i) for i in range(5)], DEFAULT_SCHEDULE, seed=seed)
    assert len(events_of(t, "day_start")) == 5
    assert [e["day"] for e in events_of(t, "elimination")] == [2, 3, 4, 5]
    assert result["winner"]


# ------------------------------------------------------------------ lives


def tournament(**config):
    return Tournament([RandomBot(i) for i in range(5)], [RemoveOne], seed=0, config=TournamentConfig(**config))


def test_life_saves_holder_and_next_in_line_goes():
    t = tournament()
    a, b, c, d, e = t.alive
    t.pieces.update({a: 1, b: 2, c: 3, d: 4, e: 5})
    t.lives[a] = 1
    assert t._choose_eliminated([[e], [d], [c], [b], [a]]) == b
    assert t.lives[a] == 0
    assert [x["actor"] for x in events_of(t, "life_used")] == [a]


def test_life_is_only_used_when_it_saves_its_owner():
    t = tournament()
    a, b, c, d, e = t.alive
    t.pieces.update({a: 1, b: 2, c: 3, d: 4, e: 5})
    t.lives[c] = 1
    assert t._choose_eliminated([[e], [d], [c], [b], [a]]) == a
    assert t.lives[c] == 1 and not events_of(t, "life_used")


def test_everyone_holding_a_life_uses_them_all_and_first_still_goes():
    t = tournament()
    for p in t.alive:
        t.lives[p] = 1
    t.pieces.update(dict(zip(t.alive, [1, 2, 3, 4, 5])))
    assert t._choose_eliminated([list(reversed(t.alive))]) == t.alive[0]
    assert all(n == 0 for n in t.lives.values())


def test_tie_break_still_applies_with_lives():
    t = tournament()
    a, b, c, d, e = t.alive
    t.pieces.update({a: 1, b: 1, c: 3, d: 4, e: 5})
    # a and b tied on Pieces; b placed lower, so b is first in line
    assert t._choose_eliminated([[e], [d], [c], [a], [b]]) == b


def test_buying_a_life_costs_pieces_and_is_public():
    buyer = LifeBuyerBot()
    t, _ = run([buyer, RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], [RemoveOne],
               config=TournamentConfig(start_pieces=6, life_price=5))
    me = seat_of(t, buyer)
    bought = events_of(t, "life_bought")
    assert [e["actor"] for e in bought] == [me]  # only once: at most one life
    assert bought[0]["visible_to"] == "all" and bought[0]["data"]["pieces"] == 1


def test_cannot_afford_a_life():
    t, _ = run([LifeBuyerBot(), RandomBot(1), RandomBot(2), RandomBot(3), RandomBot(4)], [RemoveOne],
               config=TournamentConfig(life_price=5))
    assert not events_of(t, "life_bought")  # 3 Pieces < price 5, so the bot never tried


def test_overspending_on_a_life_is_rejected():
    class Greedy(Agent):
        async def act(self, obs):
            if obs.kind == "chat" and not obs.last_error:
                other = next(p for p in obs.public["alive"] if p != obs.you)
                return {"buy_life": True, "transfers": [{"to": other, "pieces": 2}]}
            if obs.kind == "action":
                return {"action": obs.legal_actions[0]}
            return {}

    t, _ = run([Greedy(), RandomBot(1), RandomBot(2)], [RemoveOne], config=TournamentConfig(start_pieces=6, life_price=5))
    errors = [e["data"]["error"] for e in events_of(t, "invalid_output")]
    assert errors and "give and spend 7" in errors[0]
    assert not events_of(t, "life_bought")


def test_lives_cannot_be_bought_on_the_final_day():
    buyer = LifeBuyerBot()
    run([buyer, RandomBot(1)], DEFAULT_SCHEDULE[-1:], config=TournamentConfig(start_pieces=20, life_price=5))
    assert buyer.offers and all(price is None for game, price in buyer.offers)


def test_lives_can_be_disabled():
    buyer = LifeBuyerBot()
    t, _ = run([buyer, RandomBot(1), RandomBot(2)], [RemoveOne],
               config=TournamentConfig(start_pieces=20, life_price=None))
    assert all(price is None for _, price in buyer.offers) and not events_of(t, "life_bought")


def test_lives_are_off_by_default():
    buyer = LifeBuyerBot()
    t, _ = run([buyer, RandomBot(1), RandomBot(2)], [RemoveOne], config=TournamentConfig(start_pieces=20))
    assert all(price is None for _, price in buyer.offers) and not events_of(t, "life_bought")
