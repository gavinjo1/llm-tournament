from agents.bots import RandomBot
from engine.agent import Agent
from engine.tournament import TournamentConfig
from games.remove_one import RemoveOne
from tests.helpers import events_of, run, seat_of


class ChattyBot(Agent):
    """Talks in every exchange and records what it saw."""

    def __init__(self):
        self.seen = []

    async def act(self, obs):
        if obs.kind == "chat":
            self.seen.append(obs)
            return {"public_message": f"exchange {obs.exchange[0]}"}
        if obs.kind == "action":
            return {"action": obs.legal_actions[0]}
        return {}


class ReplyOnceBot(Agent):
    """Replies once to the first message it sees, then goes quiet."""

    def __init__(self):
        self.replied = False

    async def act(self, obs):
        if obs.kind == "action":
            return {"action": obs.legal_actions[0]}
        if obs.kind == "chat" and not self.replied:
            heard = [e for e in obs.history if e["type"] == "public_message" and e["actor"] != obs.you]
            if heard:
                self.replied = True
                return {"public_message": f"Replying to {heard[-1]['actor']}"}
        return {}


def conversations(t):
    return list(zip(events_of(t, "conversation_start"), events_of(t, "conversation_end")))


def test_silent_players_end_conversation_after_one_exchange():
    t, _ = run([RandomBot(i) for i in range(5)], [RemoveOne])
    convs = conversations(t)
    assert len(convs) == 1 + 6  # lounge + one per round
    assert all(end["data"]["exchanges"] == 1 for _, end in convs)


def test_chatty_player_runs_conversation_to_the_limit():
    config = TournamentConfig(lounge_exchanges=4, round_exchanges=2)
    t, _ = run([ChattyBot(), RandomBot(1), RandomBot(2)], [RemoveOne], config=config)
    ends = [end["data"]["exchanges"] for _, end in conversations(t)]
    assert ends == [4] + [2] * 6


def test_players_can_reply_within_a_conversation():
    chatty, replier = ChattyBot(), ReplyOnceBot()
    config = TournamentConfig(lounge_exchanges=3)
    t, _ = run([chatty, replier, RandomBot(2)], [RemoveOne], config=config)
    reply = next(e for e in events_of(t, "public_message") if e["actor"] == seat_of(t, replier))
    # the reply came in exchange 2 of the lounge, after hearing exchange 1
    assert reply["round"] is None and reply["exchange"] == 2
    # and the chatty bot saw the reply in exchange 3 of the same conversation
    third = next(o for o in chatty.seen if o.round is None and o.exchange == (3, 3))
    assert any(e["seq"] == reply["seq"] for e in third.history)


def test_messages_are_tagged_with_exchange():
    t, _ = run([ChattyBot(), RandomBot(1), RandomBot(2)], [RemoveOne])
    for message in events_of(t, "public_message"):
        assert message["data"]["text"] == f"exchange {message['exchange']}"
    assert all(e["exchange"] is None for e in events_of(t, "round_result"))
