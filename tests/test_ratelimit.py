import asyncio

import pytest

from agents.llm import Completion, LLMAgent
from agents.ratelimit import RateLimiter
from agents.bots import RandomBot
from games.remove_one import RemoveOne
from tests.helpers import run


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_allows_up_to_the_limit_without_waiting():
    clock = FakeClock()
    limiter = RateLimiter(3, clock=clock, sleep=clock.sleep)

    async def go():
        for _ in range(3):
            await limiter.acquire()

    asyncio.run(go())
    assert clock.slept == []


def test_waits_until_the_oldest_call_leaves_the_window():
    clock = FakeClock()
    limiter = RateLimiter(2, clock=clock, sleep=clock.sleep)

    async def go():
        await limiter.acquire()          # t=0
        clock.now = 10
        await limiter.acquire()          # t=10
        clock.now = 20
        await limiter.acquire()          # must wait until t=60

    asyncio.run(go())
    assert clock.slept == [40]
    assert clock.now == 60


def test_never_more_than_limit_in_any_minute():
    clock = FakeClock()
    limiter = RateLimiter(5, clock=clock, sleep=clock.sleep)
    times = []

    async def go():
        for _ in range(23):
            await limiter.acquire()
            times.append(clock.now)
            clock.now += 1

    asyncio.run(go())
    for t in times:
        assert sum(1 for x in times if t <= x < t + 60) <= 5


def test_rejects_zero():
    with pytest.raises(ValueError):
        RateLimiter(0)


def test_seats_sharing_a_limiter_share_the_quota():
    acquired = []

    class CountingLimiter(RateLimiter):
        async def acquire(self):
            acquired.append(1)
            await super().acquire()

    async def ok(**kwargs):
        return Completion(text="{}")

    shared = CountingLimiter(1000)
    agents = [LLMAgent("fake/m", completion=ok, limiter=shared) for _ in range(2)] + [RandomBot(1)]
    run(agents, [RemoveOne], seed=0)
    assert len(acquired) == sum(a.usage["calls"] for a in agents[:2]) > 0
