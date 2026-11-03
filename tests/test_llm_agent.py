import asyncio
import json
import re

import pytest

from agents.bots import GenerousBot, RandomBot
from agents.llm import Completion, LLMAgent, extract_json
from agents.prompts import build_messages
from engine.agent import Observation
from games.remove_one import RemoveOne
from games.schedule import DEFAULT_SCHEDULE
from tests.helpers import events_of, run, seat_of

# ---------------------------------------------------------- extract_json


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"action": {"card": 3}}', {"action": {"card": 3}}),
        ('```json\n{"action": {"card": 3}}\n```', {"action": {"card": 3}}),
        ('Sure! Here is my move: {"action": {"card": 3}} Good luck.', {"action": {"card": 3}}),
        ('I think {not json} then {"public_message": "hi"}', {"public_message": "hi"}),
    ],
)
def test_extract_json(text, expected):
    assert extract_json(text) == expected


def test_extract_json_returns_text_when_no_object():
    assert extract_json("I play card 3") == "I play card 3"


# --------------------------------------------------------------- prompts


def make_obs(**overrides):
    base = dict(
        kind="action",
        you="Player A",
        day=2,
        game="Remove One",
        round=3,
        rules="RULES TEXT",
        private={"pieces": 3, "hand": [1, 4, 6]},
        public={"alive": ["Player A", "Player B"], "pieces": {"Player A": 3, "Player B": 2}},
        history=[],
        communication="private",
        legal_actions=[{"card": 1}, {"card": 4}, {"card": 6}],
        action_help='Play one card: {"card": <number>}',
    )
    return Observation(**{**base, **overrides})


def prompt_text(obs, notes=()):
    system, user = build_messages(obs, list(notes))
    return system["content"], user["content"]


def test_prompt_contains_rules_private_info_and_legal_actions():
    system, user = prompt_text(make_obs())
    assert "You are Player A" in system and "RULES TEXT" in system
    assert '"hand": [1, 4, 6]' in user
    assert 'Legal actions: [{"card": 1}, {"card": 4}, {"card": 6}]' in user


def test_long_legal_action_lists_are_not_listed():
    obs = make_obs(legal_actions=[{"guess": g} for g in range(1, 101)], action_help="Guess 1-100")
    _, user = prompt_text(obs)
    assert "Legal actions" not in user and "Guess 1-100" in user


def test_previous_error_is_shown():
    _, user = prompt_text(make_obs(last_error="You only have 3 Pieces"))
    assert "rejected" in user and "You only have 3 Pieces" in user


def test_chat_prompt_hides_private_messages_when_disabled():
    _, user = prompt_text(make_obs(kind="chat", communication="public"))
    assert "private_messages" not in user


def test_earlier_days_are_compressed():
    history = [
        {"seq": 0, "day": 1, "round": 1, "type": "round_result", "actor": None, "data": {"winner": "Player B"}},
        {"seq": 1, "day": 1, "round": 1, "type": "public_message", "actor": "Player B", "data": {"text": "trust me"}},
        {"seq": 2, "day": 2, "round": 1, "type": "round_result", "actor": None, "data": {"winner": "Player A"}},
    ]
    _, user = prompt_text(make_obs(history=history))
    assert "trust me" in user
    assert user.count("round_result") == 1  # only today's


def test_notes_are_included():
    _, user = prompt_text(make_obs(), notes=["Day 1 R2 (chat): B lied to me"])
    assert "B lied to me" in user


# ------------------------------------------------------------ LLM agent


class FakeLLM:
    """Plays legally when the prompt lists legal actions, otherwise writes junk.
    Talks in every chat phase. Replies inside code fences to test extraction."""

    def __init__(self):
        self.calls = 0

    async def __call__(self, *, model, messages, temperature, max_tokens):
        self.calls += 1
        user = messages[-1]["content"]
        if "Chat phase" in user:
            reply = {"private_reasoning": "Stay friendly.", "public_message": "Hello all."}
        elif match := re.search(r"Legal actions: (\[.*\])", user):
            reply = {"private_reasoning": "First option.", "action": json.loads(match.group(1))[0]}
        else:
            return Completion(text="I am not sure what to do.", prompt_tokens=100, completion_tokens=10)
        return Completion(text=f"```json\n{json.dumps(reply)}\n```", prompt_tokens=100, completion_tokens=20, cost=0.001)


def test_llm_agent_plays_a_full_tournament():
    fake = FakeLLM()
    llm = LLMAgent("fake/model", completion=fake)
    t, result = run([llm, RandomBot(1), RandomBot(2), GenerousBot(3), RandomBot(4)], DEFAULT_SCHEDULE, seed=4)
    me = seat_of(t, llm)

    assert result["winner"] is not None
    assert [m for m in events_of(t, "public_message") if m["actor"] == me]
    usage = events_of(t, "agent_usage")[0]["data"][me]
    assert usage["calls"] == fake.calls == len(llm.trace)
    assert usage["prompt_tokens"] == 100 * fake.calls
    assert usage["cost"] > 0
    # junk replies are logged raw, retried, and finally defaulted
    junk = [e for e in events_of(t, "invalid_output") if e["actor"] == me]
    assert junk and junk[0]["data"]["raw"] == "I am not sure what to do."
    assert llm.notes and "Stay friendly." in llm.notes[0]
    assert all(entry["player"] == me for entry in llm.trace)


def test_api_failure_stops_the_run_instead_of_playing_random_moves():
    async def broken(**kwargs):
        raise ConnectionError("API down")

    llm = LLMAgent("fake/model", completion=broken)
    t, result = run([llm, RandomBot(1), RandomBot(2)], [RemoveOne], seed=0)
    me = seat_of(t, llm)
    assert result["aborted"] and me in result["aborted"] and "API down" in result["aborted"]
    assert result["winner"] is None
    assert events_of(t, "run_aborted") and events_of(t, "tournament_end")[0]["data"]["aborted"]
    assert not events_of(t, "elimination")
    assert not events_of(t, "default_action")  # no random moves stood in for the outage
    assert llm.usage["calls"] == llm.usage["errors"] == 1  # stopped at the first failure
    assert t.log.events[-1]["type"] == "tournament_end"


def test_api_failure_cancels_other_pending_calls():
    calls = {"slow": 0}

    async def broken(**kwargs):
        raise ConnectionError("API down")

    async def slow(**kwargs):
        calls["slow"] += 1
        await asyncio.sleep(5)
        return Completion(text="{}")

    t, result = run([LLMAgent("fake/broken", completion=broken), LLMAgent("fake/slow", completion=slow),
                     RandomBot(2)], [RemoveOne], seed=0)
    assert result["aborted"]
    assert calls["slow"] == 1  # its call was cancelled, not awaited, and no more were made
    assert t.log.events[-1]["type"] == "tournament_end"


def test_prompts_never_leak_hidden_information():
    fake = FakeLLM()
    llm = LLMAgent("fake/model", completion=fake)
    t, _ = run([llm, GenerousBot(1), GenerousBot(2), RandomBot(3), RandomBot(4)], DEFAULT_SCHEDULE, seed=2)
    me = seat_of(t, llm)
    others_dm_lines = {
        f"{e['actor']} -> {e['data']['to']} (private)"
        for e in events_of(t, "private_message")
        if me not in e["visible_to"]
    }
    assert others_dm_lines  # the GenerousBots messaged each other, so this is a real check
    hidden_types = ("roll:", "deal:", "bids:", "action:", "reasoning:", "invalid_output:")
    for entry in llm.trace:
        text = entry["messages"][-1]["content"]
        history = text.split("## What has happened")[1].split("## Your turn")[0]
        for line in others_dm_lines:
            assert line not in history
        for hidden in hidden_types:
            assert hidden not in history


def test_reasoning_effort_is_sent_and_recorded():
    seen = []

    async def capture(**kwargs):
        seen.append(kwargs)
        return Completion(text="{}")

    llm = LLMAgent("fake/model", reasoning_effort="none", completion=capture)
    t, _ = run([llm, RandomBot(1), RandomBot(2)], [RemoveOne], seed=0)
    assert seen and all(call["reasoning_effort"] == "none" for call in seen)
    assert all(entry["settings"]["reasoning_effort"] == "none" for entry in llm.trace)
    usage = events_of(t, "agent_usage")[0]["data"][seat_of(t, llm)]
    assert usage["settings"] == {
        "model": "fake/model", "temperature": 0.7, "max_tokens": 800, "reasoning_effort": "none",
    }


def test_reasoning_effort_not_sent_by_default():
    seen = []

    async def capture(**kwargs):
        seen.append(kwargs)
        return Completion(text="{}")

    run([LLMAgent("fake/model", completion=capture), RandomBot(1), RandomBot(2)], [RemoveOne], seed=0)
    assert seen and all("reasoning_effort" not in call for call in seen)
