import asyncio

from engine.tournament import Tournament


def run(agents, schedule, seed=0, config=None, log=None):
    t = Tournament(agents, schedule, seed=seed, config=config, log=log)
    return t, asyncio.run(t.run())


def events_of(t, type):
    return [e for e in t.log.events if e["type"] == type]


def seat_of(t, agent):
    return next(p for p, a in t.agents.items() if a is agent)
