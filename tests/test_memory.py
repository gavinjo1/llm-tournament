"""Memory across days: end-of-day diaries, key facts, and the "full" setting."""

import asyncio

import pytest

from agents.bots import RandomBot
from agents.prompts import build_messages, render_fact
from engine.agent import Agent, Observation
from engine.tournament import Tournament, TournamentConfig
from games.schedule import DEFAULT_SCHEDULE
from tests.helpers import events_of, run, seat_of
from tests.test_show_format import seven_bots


class TalkBot(RandomBot):
    """Says a day-stamped public line in every chat, writes a diary naming the day,
    and records the prompt it would have been given."""

    def __init__(self, seed=0):
        super().__init__(seed)
        self.prompts: list[tuple[int, str, str]] = []

    async def act(self, obs):
        self.prompts.append((obs.day, obs.kind, build_messages(obs, [])[1]["content"]))
        if obs.kind == "chat":
            return {"public_message": f"chat-day-{obs.day}"}
        if obs.kind == "diary":
            others = [p for p in obs.public["alive"] if p != obs.you]
            return {"summary": f"diary-day-{obs.day}", "players": {others[0]: "watch this one"}}
        return await super().act(obs)


def play_show(agents, seed=0, **config):
    t = Tournament(agents, seed=seed, config=TournamentConfig(format="show", start_pieces=1, **config))
    return t, asyncio.run(t.run())


# --------------------------------------------------------- diary step


@pytest.mark.parametrize("seed", range(5))
def test_every_living_player_writes_a_private_diary_each_evening(seed):
    t, _ = play_show(seven_bots(seed), seed)
    diaries = events_of(t, "diary")
    days = sorted({e["day"] for e in events_of(t, "day_start")})
    for day in days[:-1]:  # no diary after the final
        writers = [e["actor"] for e in diaries if e["day"] == day]
        assert writers and len(writers) == len(set(writers))
    for e in diaries:
        assert e["visible_to"] == [e["actor"]]
    assert all(e["day"] != days[-1] for e in diaries)


@pytest.mark.parametrize("memory", ["full", "facts"])
def test_no_diary_without_diary_memory(memory):
    t, _ = play_show(seven_bots(1), 1, memory=memory)
    assert not events_of(t, "diary")


def test_classic_format_writes_diaries_between_days_only():
    t, _ = run([RandomBot(i) for i in range(5)], DEFAULT_SCHEDULE, seed=3)
    diary_days = {e["day"] for e in events_of(t, "diary")}
    assert diary_days and max(diary_days) < len(DEFAULT_SCHEDULE)


def test_diary_rejects_notes_on_unknown_players_and_long_text():
    t = Tournament([RandomBot(i) for i in range(3)], seed=0, config=TournamentConfig(format="show", start_pieces=1))
    me = t.alive[0]
    t._parse_diary(me, {"summary": "ok", "players": {t.alive[1]: "fine"}})
    with pytest.raises(ValueError):
        t._parse_diary(me, {"players": {"Player Z": "who?"}})
    with pytest.raises(ValueError):
        t._parse_diary(me, {"players": {me: "myself"}})
    with pytest.raises(ValueError):
        t._parse_diary(me, {"summary": "word " * 151})
    with pytest.raises(ValueError):
        t._parse_diary(me, {"players": {t.alive[1]: "word " * 51}})


def test_rules_tell_players_how_memory_works():
    t = Tournament([RandomBot(i) for i in range(3)], seed=0, config=TournamentConfig(format="show", start_pieces=1))
    assert "private diary" in t.observe(t.alive[0], "chat").rules
    t = Tournament([RandomBot(i) for i in range(3)], seed=0,
                   config=TournamentConfig(format="show", start_pieces=1, memory="full"))
    assert "Memory:" not in t.observe(t.alive[0], "chat").rules


# ---------------------------------------------- what later prompts show


def later_prompts(bot, day_min=2):
    return [text for day, kind, text in bot.prompts if day >= day_min and kind == "chat"]


def survivor(bots):
    """The bot that was asked to speak on the latest day."""
    return max(bots, key=lambda b: max(day for day, kind, _ in b.prompts if kind == "chat"))


def test_diary_memory_replaces_earlier_conversations_with_facts_and_diary():
    talkers = [TalkBot(i) for i in range(7)]
    t, _ = play_show(talkers, 2)
    bot = survivor(talkers)
    me = seat_of(t, bot)
    texts = later_prompts(bot)
    assert texts
    assert all("chat-day-1" not in text for text in texts)  # yesterday's talk is gone
    day2 = [text for day, kind, text in bot.prompts if day == 2 and kind == "chat"]
    assert any("chat-day-2" in text for text in day2)  # today's talk is shown
    assert all("Your diary, end of Day 1: diary-day-1" in text for text in day2)
    assert all("Placement:" in text for text in day2)  # key facts of day 1
    assert me in t.agents


def test_diaries_are_private_in_prompts():
    talkers = [TalkBot(i) for i in range(7)]
    t, _ = play_show(talkers, 4)
    for bot in talkers:
        me = seat_of(t, bot)
        own = {e["seq"] for e in events_of(t, "diary") if e["actor"] == me}
        seen = {e["seq"] for e in t.log.visible_to_player(me) if e["type"] == "diary"}
        assert seen == own


def test_full_memory_keeps_earlier_conversations():
    talkers = [TalkBot(i) for i in range(7)]
    play_show(talkers, 2, memory="full")
    assert any("chat-day-1" in text for text in later_prompts(survivor(talkers)))


def test_facts_memory_shows_facts_but_no_diary():
    talkers = [TalkBot(i) for i in range(7)]
    play_show(talkers, 2, memory="facts")
    texts = later_prompts(survivor(talkers))
    assert texts and all("chat-day-1" not in t and "Your diary" not in t for t in texts)
    assert all("Placement:" in t for t in texts)


def test_diary_prompts_stay_small():
    """Earlier days no longer pile up: day-3 prompts are far shorter than with full memory."""
    sizes = {}
    for memory in ("full", "diary"):
        talkers = [TalkBot(i) for i in range(7)]
        play_show(talkers, 2, memory=memory)
        late = [len(text) for day, kind, text in survivor(talkers).prompts if day == 3 and kind == "chat"]
        sizes[memory] = max(late) if late else 0
    if sizes["full"]:
        assert sizes["diary"] < sizes["full"]


# ------------------------------------------------------------ fact lines


def fact(type, data, actor=None, day=1):
    return render_fact({"seq": 0, "day": day, "round": None, "type": type, "actor": actor, "data": data}, "Player A")


def test_fact_lines_show_what_players_did():
    assert fact("prison", {"prisoners": ["Player C", "Player D"], "automatic": ["Player C"],
                           "candidates": ["Player B", "Player D"], "deciders": ["Player A"],
                           "votes": {"Player A": ["Player D"]}, "pieces": {}}) == (
        'Sent to prison: Player C, Player D. Fewest Pieces: Player C. Chosen by Player A, '
        'votes {"Player A": ["Player D"]}.'
    )
    assert "Player B doubted Player C's bid 4 x 5: the bid was true; Player B lost a die." == fact(
        "doubt", {"doubter": "Player B", "bid": {"player": "Player C", "quantity": 4, "face": 5},
                  "dice": {}, "count": 5, "bid_was_true": True, "loser": "Player B", "dice_count": {}})
    line = fact("monster_result", {"round": 2, "winner_party": "Player B", "allocation": {"Player B": 6},
                                   "parties": {"Player B": {"members": ["Player A", "Player B"], "power": 9}},
                                   "plays": {}})
    assert "led by Player B" in line and '{"Player B": 6}' in line
    assert fact("elimination", {"player": "Player E", "pieces": 0, "reason": "lost the prison match"}) == (
        "Player E was eliminated (lost the prison match)."
    )


def test_generic_fact_lines_drop_hidden_hands_and_stay_short():
    line = fact("dice_result", {"round": 1, "dice": {"Player A": [1, 2, 3]}, "winner": "Player A",
                                "points": {"Player A": 4}, "note": "x" * 500})
    assert "[1, 2, 3]" not in line and len(line) <= 240


def test_unknown_memory_events_are_not_shown_from_earlier_days():
    history = [
        {"seq": 0, "day": 1, "round": 1, "type": "bid", "actor": "Player B", "data": {"quantity": 3, "face": 2}},
        {"seq": 1, "day": 1, "round": None, "type": "public_message", "actor": "Player B", "data": {"text": "trust me"}},
        {"seq": 2, "day": 1, "round": None, "type": "diary", "actor": "Player A",
         "data": {"summary": "B said trust me", "players": {"Player B": "pushy"}}},
    ]
    obs = Observation(kind="chat", you="Player A", day=2, game=None, round=None, rules="R",
                      private={"pieces": 1}, public={"alive": ["Player A", "Player B"]},
                      history=history, communication="private", memory="diary")
    user = build_messages(obs, [])[1]["content"]
    assert "trust me" not in user.replace("B said trust me", "")
    assert "bids" not in user and "quantity" not in user
    assert "Your diary, end of Day 1: B said trust me" in user and "Player B: pushy" in user
