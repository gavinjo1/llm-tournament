from agents.bots import RandomBot
from engine.agent import Agent
from engine.events import EventLog
from engine.run import stop_file_for
from engine.tournament import Tournament
from games.schedule import DEFAULT_SCHEDULE
from tests.helpers import events_of
import asyncio


class PressesStopBot(RandomBot):
    """Creates the stop file on day 3, like someone clicking Stop in the viewer."""

    stop_file = None

    async def act(self, obs):
        if obs.day == 3 and self.stop_file is not None:
            self.stop_file.touch()
        return await super().act(obs)


def test_stop_file_stops_the_run_cleanly(tmp_path):
    log_path = tmp_path / "run.jsonl"
    stop = stop_file_for(log_path)
    presser = PressesStopBot(0)
    presser.stop_file = stop
    with EventLog(log_path) as log:
        t = Tournament([presser] + [RandomBot(i) for i in range(1, 5)], DEFAULT_SCHEDULE,
                       seed=0, log=log, stop_file=stop)
        result = asyncio.run(t.run())
    assert result["aborted"] == "Stopped from the viewer."
    assert result["winner"] is None
    assert not stop.exists()  # cleaned up
    assert events_of(t, "run_aborted")[0]["day"] == 3
    assert not [e for e in t.log.events if e["day"] and e["day"] > 3]
    assert t.log.events[-1]["type"] == "tournament_end"


def test_leftover_stop_file_is_ignored(tmp_path):
    stop = stop_file_for(tmp_path / "run.jsonl")
    stop.touch()
    t = Tournament([RandomBot(i) for i in range(5)], DEFAULT_SCHEDULE, seed=0, stop_file=stop)
    result = asyncio.run(t.run())
    assert result["winner"] and not result["aborted"]
