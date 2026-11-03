"""The tournament engine: days, chat phases, Pieces, elimination (spec §2)."""

from __future__ import annotations

import asyncio
import json
import random
import string
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar

from pydantic import BaseModel

from engine.agent import Agent, AgentFailure, Kind, Memory, Observation, RunHalted, StopRequested
from engine.events import GOD, PUBLIC, EventLog
from engine.models import ActionEnvelope, ChatTurn, DiaryTurn, Transfer, WillTurn
from engine.rules import MEMORY_TEXT, PHASE_TEXT, global_rules, global_rules_show, placement_text
from games.base import Game, Ranking

# Spec §2.4, indexed by number of players in the game.
PLACEMENT_REWARDS: dict[int, list[int]] = {
    6: [3, 1, 0, 0, -1, -2],  # 6-player tournament only; not in the spec yet
    5: [3, 1, 0, -1, -2],
    4: [3, 1, -1, -2],
    3: [3, 0, -2],
}

GameFactory = Callable[[list[str], random.Random], Game]
T = TypeVar("T")


@dataclass
class TournamentConfig:
    format: Literal["classic", "show"] = "classic"
    """classic: one game a day, fewest Pieces out. show: random main match, then a
    prison match that eliminates one player (Devil's Plan season 2)."""
    start_pieces: int = 3
    lounge_exchanges: int = 6
    """Max exchanges in the morning-lounge conversation before each game."""
    round_exchanges: int = 3
    """Max exchanges in the conversation before each game round."""
    communication: Literal["none", "public", "private"] = "private"
    max_retries: int = 2
    life_price: int | None = None
    """Pieces for one life (insurance against one elimination). None disables lives."""
    main_rewards: tuple[int, ...] = (4, 3, 2, 1)
    """Show format: main-match Pieces for the top places (unless the game sets its own).
    The show's Rules Race used +3, +2, +1 ... -1, -3, -5; with 7 players starting on
    1 Piece that ends most tournaments in 3-4 days, so the table is softened to last
    about 5 (bot measurements, spec section 1b)."""
    main_penalties: tuple[int, ...] = (-1, -2)
    """Show format: main-match Pieces for the last places, ending with last place.
    Applied to the lower half only."""
    prison_seats: int = 2
    prison_win_bonus: int = 1
    safe_first_day: bool = True
    """Show rule: nobody is eliminated for 0 Pieces after the first main match."""
    memory: Memory = "diary"
    """How players see earlier days. "diary": every evening each player writes a
    private diary; later prompts show earlier days only as key public results
    plus the player's own diary. "facts": key results only, no diary. "full":
    every earlier message verbatim (the pilots' setting; prompts grow every day)."""


def placement_rewards(
    ranking: Ranking, table: list[int] | None = None, toward_zero: bool = False
) -> dict[str, int]:
    """Pieces per player. Tied players get the average of their places, rounded down
    (or toward zero, so a tie never deepens a loss through rounding)."""
    n = sum(len(group) for group in ranking)
    if table is None:
        if n not in PLACEMENT_REWARDS:
            raise ValueError(f"No placement rewards defined for {n} players")
        table = PLACEMENT_REWARDS[n]
    rewards: dict[str, int] = {}
    place = 0
    for group in ranking:
        shared = table[place : place + len(group)]
        for player in group:
            total = sum(shared)
            rewards[player] = int(total / len(shared)) if toward_zero else total // len(shared)
        place += len(group)
    return rewards


class Tournament:
    def __init__(
        self,
        agents: list[Agent],
        schedule: list[GameFactory] | None = None,
        *,
        seed: int,
        config: TournamentConfig | None = None,
        log: EventLog | None = None,
        stop_file: Path | None = None,
    ) -> None:
        """stop_file: if this file appears, the run stops before the next agent
        request (the viewer's Stop button creates it)."""
        if len(agents) < 2:
            raise ValueError("A tournament needs at least 2 agents")
        self.config = config or TournamentConfig()
        self.seed = seed
        self.rng = random.Random(seed)
        self.log = log or EventLog()
        self.schedule = schedule or []
        if self.config.format == "classic" and not self.schedule:
            raise ValueError("The classic format needs a schedule of games")
        self.stop_file = stop_file
        if stop_file is not None:
            stop_file.unlink(missing_ok=True)  # a leftover from an earlier run

        names = [f"Player {letter}" for letter in string.ascii_uppercase[: len(agents)]]
        seats = list(agents)
        self.rng.shuffle(seats)
        self.agents: dict[str, Agent] = dict(zip(names, seats))
        self.alive: list[str] = list(names)
        self.pieces: dict[str, int] = {n: self.config.start_pieces for n in names}
        self.lives: dict[str, int] = {n: 0 for n in names}
        self._requests: dict[str, int] = {n: 0 for n in names}
        self._exchange: tuple[int, int] | None = None
        self._speakers: list[str] | None = None
        self.phase: str = "main"
        self.day = 0
        self.game: Game | None = None

    # ------------------------------------------------------------------ run

    async def run(self) -> dict[str, Any]:
        self.log.emit(
            "tournament_start",
            {
                "players": list(self.alive),
                "pieces": dict(self.pieces),
                "config": json.loads(json.dumps(asdict(self.config))),  # as stored in the log
            },
        )
        self.log.emit(
            "seating",
            {"seed": self.seed, "agents": {n: a.label for n, a in self.agents.items()}},
            visible_to=GOD,
        )
        aborted: str | None = None
        try:
            if self.config.format == "show":
                await self._run_show()
            else:
                for day, make_game in enumerate(self.schedule, start=1):
                    if len(self.alive) <= 1:
                        break
                    await self._play_day(day, make_game)
                    if day < len(self.schedule) and len(self.alive) > 1:
                        await self._diary()
        except RunHalted as exc:
            aborted = str(exc)
            self.log.set_context(exchange=None)
            self.log.emit("run_aborted", {"reason": aborted})

        self.log.set_context(day=None, round=None, exchange=None)
        if self.stop_file is not None:
            self.stop_file.unlink(missing_ok=True)
        usage = {n: a.usage_report() for n, a in self.agents.items() if a.usage_report() is not None}
        if usage:
            self.log.emit("agent_usage", usage, visible_to=GOD)
        winner = self.alive[0] if len(self.alive) == 1 and not aborted else None
        result = {
            "winner": winner,
            "alive": list(self.alive),
            "pieces": self.public_pieces(),
            "agents": {n: a.label for n, a in self.agents.items()},
            "aborted": aborted,
        }
        self.log.emit("tournament_end", {k: result[k] for k in ("winner", "alive", "pieces", "aborted")})
        return result

    async def _play_day(self, day: int, make_game: GameFactory) -> None:
        self.day = day
        self.log.set_context(day=day, round=None)
        self.game = make_game(list(self.alive), self.rng)
        self.log.emit(
            "day_start",
            {"game": self.game.name, "players": list(self.alive), "pieces": self.public_pieces()},
        )
        await self.chat_phase(self.game.lounge_exchanges or self.config.lounge_exchanges)

        ranking = await self.game.play(self)
        self.log.set_context(round=None)

        if self.game.self_eliminating:
            if len(self.alive) == 1:
                self.log.emit("champion", {"player": self.alive[0]})
            self.game = None
            return

        if not self.game.eliminates:
            self.log.emit("day_end", {"pieces": self.public_pieces(), "lives": self.public_lives()})
            self.game = None
            return

        if self.game.final:
            champion, runner_up = ranking[0][0], ranking[-1][0]
            self.alive.remove(runner_up)
            self.log.emit("elimination", {"player": runner_up, "pieces": self.pieces[runner_up]})
            self.log.emit("champion", {"player": champion})
            self.game = None
            return

        rewards = placement_rewards(ranking)
        for player, reward in rewards.items():
            self.pieces[player] = max(0, self.pieces[player] + reward)
        self.log.emit(
            "placement", {"ranking": ranking, "rewards": rewards, "pieces": self.public_pieces()}
        )

        eliminated = self._choose_eliminated(ranking)
        self.alive.remove(eliminated)
        self.log.emit("elimination", {"player": eliminated, "pieces": self.pieces[eliminated]})
        await self._last_will(eliminated)
        self.pieces[eliminated] = 0
        self.game = None

    # ------------------------------------------------------- show format

    async def _run_show(self) -> None:
        from games import show

        used: set[str] = set()
        day = 0
        while len(self.alive) > 2:
            day += 1
            await self._show_day(day, used)
            if len(self.alive) >= 2:
                await self._diary()
        if len(self.alive) == 2:
            self.phase = "final"
            await self._play_day(day + 1, show.FINAL)

    async def _show_day(self, day: int, used: set[str]) -> None:
        """Main match, prison decision, prison match; 0 Pieces at day end = out."""
        from games import show

        self.day = day
        self.phase = "main"
        self.log.set_context(day=day, round=None)
        main = show.draw(show.MAIN_POOL, len(self.alive), used, self.rng)
        self.game = main(list(self.alive), self.rng)
        self.log.emit(
            "day_start",
            {"game": self.game.name, "phase": "main", "players": list(self.alive), "pieces": self.public_pieces()},
        )
        await self.chat_phase(self.game.lounge_exchanges or self.config.lounge_exchanges)
        ranking = await self.game.play(self)
        self.log.set_context(round=None)
        rewards = self.game.main_rewards(ranking)
        if rewards is None:
            if len(ranking) == 1:  # everyone tied: nobody gains or loses
                rewards = {p: 0 for p in ranking[0]}
            else:
                rewards = placement_rewards(ranking, self._main_table(len(self.game.players)), toward_zero=True)
        for player, reward in rewards.items():
            self.pieces[player] = max(0, self.pieces[player] + reward)
        self.log.emit("placement", {"ranking": ranking, "rewards": rewards, "pieces": self.public_pieces()})
        self.game = None
        exempt = day == 1 and self.config.safe_first_day
        if not exempt:
            self._eliminate_broke("0 Pieces after the main match")

        if len(self.alive) > 2:
            prisoners = await self._choose_prisoners()
            await self._prison_match(prisoners, used)
        self.phase = "main"
        if not exempt:
            self._eliminate_broke("0 Pieces at the end of the day")

    def _main_table(self, n: int) -> list[int]:
        """Main-match Pieces by place: the top rewards first, the penalties on the last places."""
        top, bottom = list(self.config.main_rewards), list(self.config.main_penalties)
        table = [0] * n
        lower = min(len(bottom), n // 2)
        for k in range(1, lower + 1):  # last place gets the last penalty, and so on upwards
            table[n - k] = bottom[-k]
        for i in range(min(len(top), n - lower)):
            table[i] = top[i]
        return table

    async def _choose_prisoners(self) -> list[str]:
        """The player with the fewest Pieces goes to prison automatically; the
        player(s) with the most Pieces choose who fills the other seat(s), from
        anyone else alive (the show's rule).

        If several players share the fewest Pieces they all go when they fit the
        seats; if more of them are tied than there are seats, the leaders choose
        which of them go."""
        seats = self.config.prison_seats
        low = min(self.pieces[p] for p in self.alive)
        poorest = [p for p in self.alive if self.pieces[p] == low]
        choosers: list[str] = []
        votes: dict[str, list[str]] = {}
        if len(poorest) > seats:
            automatic, candidates = [], poorest
        else:
            automatic, candidates = poorest, [p for p in self.alive if p not in poorest]
        need = seats - len(automatic)
        sent = list(automatic)
        if need:
            top = max(self.pieces[p] for p in self.alive)
            # if everyone is tied, every player is a leader and they choose among themselves
            choosers = [p for p in self.alive if self.pieces[p] == top]
            chosen, votes = await self._leader_vote(choosers, candidates, need, automatic)
            sent += chosen
        prisoners = [p for p in self.alive if p in sent]
        self.log.emit(
            "prison",
            {"prisoners": prisoners, "automatic": automatic, "candidates": candidates if need else [],
             "deciders": choosers, "votes": votes, "pieces": self.public_pieces()},
        )
        return prisoners

    async def _leader_vote(
        self, choosers: list[str], candidates: list[str], need: int, already: list[str]
    ) -> tuple[list[str], dict[str, list[str]]]:
        from games.prison_choice import PrisonChoice

        self.phase = "choose"
        self.game = PrisonChoice(choosers, candidates, need, already, self.rng)
        self.log.emit("prison_choice_start", {"deciders": choosers, "candidates": candidates, "seats": need,
                                              "already": already})
        if len(choosers) > 1:
            await self.chat_phase(speakers=choosers)
        actions = await self.collect_actions(choosers)
        self.game = None
        votes = {p: sorted(actions[p].send) for p in choosers}
        count: dict[str, int] = {}
        for picks in votes.values():
            for c in picks:
                count[c] = count.get(c, 0) + 1
        order = sorted(candidates, key=lambda c: -count.get(c, 0))
        cutoff = count.get(order[need - 1], 0)
        sure = [c for c in order if count.get(c, 0) > cutoff]
        tied = sorted(c for c in order if count.get(c, 0) == cutoff)
        drawn = self.rng.sample(tied, need - len(sure)) if need - len(sure) < len(tied) else tied
        if need - len(sure) < len(tied):
            self.log.emit("tie_break_draw", {"between": tied, "chosen": sorted(drawn)})
        return sure + drawn, votes

    async def _prison_match(self, prisoners: list[str], used: set[str]) -> None:
        from games import show

        self.phase = "prison"
        prison = show.draw(show.PRISON_POOL, len(prisoners), used, self.rng)
        self.game = prison(prisoners, self.rng)
        self.log.emit("prison_start", {"game": self.game.name, "players": prisoners})
        ranking = await self.game.play(self)
        self.log.set_context(round=None)
        self.game = None
        last = ranking[-1]
        loser = last[0] if len(last) == 1 else self.rng.choice(sorted(last))
        if len(last) > 1:
            self.log.emit("tie_break_draw", {"between": sorted(last), "chosen": loser})
        # A tie for first is settled the same way: whoever survives the draw is the
        # winner and gets the bonus, so a drawn match never leaves its survivor at
        # 0 Pieces to be eliminated at the end of the day as well.
        top = [p for p in ranking[0] if p != loser]
        winner = (top[0] if len(top) == 1 else self.rng.choice(sorted(top))) if top else None
        if len(top) > 1:
            self.log.emit("tie_break_draw", {"between": sorted(top), "chosen": winner, "for": "winner"})
        self.log.emit("prison_result", {"ranking": ranking, "winner": winner, "loser": loser})
        if winner and self.config.prison_win_bonus:
            self.adjust_pieces(winner, self.config.prison_win_bonus, "prison match win")
        self.alive.remove(loser)
        self.log.emit("elimination", {"player": loser, "pieces": self.pieces[loser], "reason": "lost the prison match"})
        await self._last_will(loser)
        self.pieces[loser] = 0

    def _eliminate_broke(self, reason: str = "no Pieces left") -> None:
        """A player with 0 Pieces is out (unless that would leave nobody)."""
        broke = [p for p in self.alive if self.pieces[p] <= 0]
        if not broke or len(broke) == len(self.alive):
            return
        for player in broke:
            self.alive.remove(player)
            self.log.emit("elimination", {"player": player, "pieces": 0, "reason": reason})

    def _choose_eliminated(self, ranking: Ranking) -> str:
        """Fewest Pieces goes, then lower placement, then a random draw.

        A player holding a life uses it instead of being eliminated, and the
        next player in line goes. If everyone left holds a life, all lives are
        used and the first in line is still eliminated.
        """
        place = {p: i for i, group in enumerate(ranking) for p in group}
        key = {p: (self.pieces[p], -place[p]) for p in self.alive}
        groups = []
        for k in sorted(set(key.values())):
            group = sorted(p for p in self.alive if key[p] == k)
            self.rng.shuffle(group)
            groups.append(group)
        line = [p for group in groups for p in group]

        eliminated = line[0]
        for player in line:
            if self.lives[player] == 0:
                eliminated = player
                break
            self.lives[player] -= 1
            self.log.emit("life_used", {"player": player, "pieces": self.pieces[player]}, actor=player)

        group = next(g for g in groups if eliminated in g)
        if len(group) > 1:
            self.log.emit("tie_break_draw", {"between": sorted(group), "chosen": eliminated})
        return eliminated

    async def _last_will(self, player: str) -> None:
        if self.pieces[player] == 0 or not self.alive:
            return
        turn = await self._ask(
            player, "will", lambda raw: self._parse_will(player, raw), WillTurn
        )
        self._log_reasoning(player, turn.private_reasoning)
        for transfer in turn.transfers:
            self._transfer(player, transfer, last_will=True)

    async def _diary(self) -> None:
        """End of the day: every living player writes a private diary entry.

        Only the writer (and the researchers) can see it. It is how a player
        remembers the day's conversations once later prompts stop showing them."""
        if self.config.memory != "diary":
            return
        self.phase = "diary"
        self.log.set_context(round=None, exchange=None)
        turns = await _all(
            *(
                self._ask(p, "diary", lambda raw, p=p: self._parse_diary(p, raw), DiaryTurn)
                for p in self.alive
            )
        )
        for player, turn in zip(self.alive, turns):
            self._log_reasoning(player, turn.private_reasoning)
            self.log.emit(
                "diary", {"summary": turn.summary, "players": turn.players}, actor=player, visible_to=[player]
            )
        self.phase = "main"

    # ------------------------------------------------- phases used by games

    async def chat_phase(self, max_exchanges: int | None = None, speakers: list[str] | None = None) -> None:
        """A free conversation among all living players.

        In each exchange everyone may talk and give Pieces at the same time,
        seeing everything said in earlier exchanges. The conversation goes on
        until an exchange where nobody says or gives anything, or until
        max_exchanges (default: config.round_exchanges).
        """
        if self.config.communication == "none":
            return
        if speakers is None:
            speakers = [p for p in self.game.players if p in self.alive] if self.game else list(self.alive)
        self._speakers = speakers
        limit = max_exchanges or self.config.round_exchanges
        self.log.emit("conversation_start", {"max_exchanges": limit}, visible_to=self._audience())
        used = 0
        for exchange in range(1, limit + 1):
            self._exchange = (exchange, limit)
            self.log.set_context(exchange=exchange)
            used = exchange
            if not await self._chat_exchange():
                break
        self._exchange = None
        self.log.set_context(exchange=None)
        self.log.emit("conversation_end", {"exchanges": used}, visible_to=self._audience())
        self._speakers = None

    def _audience(self) -> str | list[str]:
        """Who sees this conversation: everyone, or only its speakers (prison)."""
        if self._speakers is None or set(self._speakers) == set(self.alive):
            return PUBLIC
        return sorted(self._speakers)

    async def _chat_exchange(self) -> bool:
        """One exchange of a conversation. Returns whether anyone acted."""
        speakers = list(self._speakers or self.alive)
        turns = await _all(
            *(
                self._ask(p, "chat", lambda raw, p=p: self._parse_chat(p, raw), ChatTurn)
                for p in speakers
            )
        )
        for player, turn in zip(speakers, turns):
            self._log_reasoning(player, turn.private_reasoning)
            if turn.public_message:
                self.log.emit(
                    "public_message", {"text": turn.public_message}, actor=player, visible_to=self._audience()
                )
            for message in turn.private_messages:
                self.log.emit(
                    "private_message",
                    {"to": message.to, "text": message.text},
                    actor=player,
                    visible_to=sorted([player, message.to]),
                )
            for transfer in turn.transfers:
                self._transfer(player, transfer)
            if turn.buy_life:
                self._buy_life(player)
        return any(
            t.public_message or t.private_messages or t.transfers or t.buy_life for t in turns
        )

    def _buy_life(self, player: str) -> None:
        price = self.config.life_price
        assert price is not None and self.lives[player] == 0 and self.pieces[player] >= price
        self.pieces[player] -= price
        self.lives[player] = 1
        self.log.emit("life_bought", {"price": price, "pieces": self.pieces[player]}, actor=player)

    async def collect_actions(self, players: list[str]) -> dict[str, BaseModel]:
        """Ask players for a sealed action at the same time. Revealing is the game's job."""
        results = await _all(
            *(
                self._ask(
                    p,
                    "action",
                    lambda raw, p=p: self._parse_action(p, raw),
                    lambda p=p: self._default_action(p),
                )
                for p in players
            )
        )
        actions: dict[str, BaseModel] = {}
        for player, (reasoning, action) in zip(players, results):
            self._log_reasoning(player, reasoning)
            self.log.emit("action", {"action": action.model_dump()}, actor=player, visible_to=GOD)
            actions[player] = action
        return actions

    def eliminate(self, player: str, reason: str) -> None:
        """For games that eliminate players themselves (e.g. Suit Survival)."""
        if player in self.alive:
            self.alive.remove(player)
            self.log.emit("elimination", {"player": player, "pieces": self.pieces[player], "reason": reason})

    def adjust_pieces(self, player: str, delta: int, reason: str) -> None:
        """Pay to or receive from the bank during a game (clues, bonuses)."""
        self.pieces[player] = max(0, self.pieces[player] + delta)
        self.log.emit(
            "pieces_change",
            {"delta": delta, "reason": reason, "pieces": self.pieces[player]},
            actor=player,
        )

    # ------------------------------------------------------ observations

    def public_pieces(self) -> dict[str, int]:
        return {p: self.pieces[p] for p in self.alive}

    def public_lives(self) -> dict[str, int]:
        return {p: self.lives[p] for p in self.alive}

    def life_price(self) -> int | None:
        """Current price of a life, or None when lives cannot be bought now."""
        if self.config.life_price is None or (self.game is not None and self.game.final):
            return None
        return self.config.life_price

    def observe(self, player: str, kind: Kind, error: str | None = None) -> Observation:
        game = self.game
        private: dict[str, Any] = {"pieces": self.pieces[player]}
        public: dict[str, Any] = {
            "alive": list(self.alive),
            "pieces": self.public_pieces(),
            "lives": self.public_lives(),
        }
        if kind == "chat" and self._speakers is not None:
            public["in_this_conversation"] = list(self._speakers)
        if self.config.format == "show":
            rules = global_rules_show(
                self.config.communication, self.config.start_pieces,
                self.config.main_rewards, self.config.main_penalties, self.config.prison_seats,
                self.config.prison_win_bonus,
            )
            public["phase"] = self.phase
        else:
            rules = global_rules(self.config.communication, self.config.start_pieces, self.config.life_price)
        if self.config.memory in MEMORY_TEXT:
            rules += "\n" + MEMORY_TEXT[self.config.memory]
        if game is not None:
            if player in game.players:
                private.update(game.private_view(player))
            public["game"] = game.public_view()
            if self.config.format == "show" and self.phase in PHASE_TEXT:
                rules += "\n\n" + PHASE_TEXT[self.phase]
            rules += "\n\n" + game.rules
            if (
                self.config.format == "classic"
                and game.eliminates
                and not game.final
                and len(game.players) in PLACEMENT_REWARDS
            ):
                rules += "\n" + placement_text(PLACEMENT_REWARDS[len(game.players)])
        legal = game.legal_actions(player) if kind == "action" and game else []
        sample = None
        if kind == "action" and game and legal is None:
            sample = game.random_action(player, random.Random(f"{self.seed}:sample:{player}:{self._requests[player]}"))
        return Observation(
            kind=kind,
            you=player,
            day=self.day,
            game=game.name if game else None,
            round=self.log.context["round"],
            rules=rules,
            private=private,
            public=public,
            history=self.log.visible_to_player(player),
            communication=self.config.communication,
            legal_actions=legal,
            sample_action=sample,
            action_help=game.action_help(player) if kind == "action" and game else "",
            exchange=self._exchange if kind == "chat" else None,
            life_price=self.life_price() if kind == "chat" and self.lives[player] == 0 else None,
            last_error=error,
            memory=self.config.memory,
        )

    # ------------------------------------------------- asking and parsing

    async def _ask(
        self,
        player: str,
        kind: Kind,
        parse: Callable[[Any], T],
        default: Callable[[], T],
    ) -> T:
        """Ask a player, re-prompting with the error up to max_retries times (spec §2.7)."""
        self._requests[player] += 1
        error: str | None = None
        for attempt in range(1, self.config.max_retries + 2):
            if self.stop_file is not None and self.stop_file.exists():
                raise StopRequested("Stopped from the viewer.")
            try:
                raw = await self.agents[player].act(self.observe(player, kind, error))
            except AgentFailure as exc:
                raise AgentFailure(f"{player} could not respond: {exc}") from exc
            try:
                return parse(raw)
            except ValueError as exc:  # includes pydantic ValidationError and bad JSON
                error = str(exc)
                self.log.emit(
                    "invalid_output",
                    {"kind": kind, "attempt": attempt, "error": error, "raw": _jsonable(raw)},
                    actor=player,
                    visible_to=GOD,
                )
        self.log.emit("default_action", {"kind": kind}, actor=player, visible_to=GOD)
        return default()

    def _parse_chat(self, player: str, raw: Any) -> ChatTurn:
        turn = ChatTurn.model_validate(_load(raw))
        if turn.private_messages and self.config.communication != "private":
            raise ValueError("Private messages are disabled in this tournament.")
        for message in turn.private_messages:
            self._check_recipient(player, message.to, self._speakers)
        life_cost = 0
        if turn.buy_life:
            price = self.life_price()
            if price is None:
                raise ValueError("Lives cannot be bought now.")
            if self.lives[player] > 0:
                raise ValueError("You already hold a life; you can hold at most one.")
            life_cost = price
        self._check_transfers(player, turn.transfers, extra_cost=life_cost, allowed=self._speakers)
        return turn

    def _parse_will(self, player: str, raw: Any) -> WillTurn:
        turn = WillTurn.model_validate(_load(raw))
        self._check_transfers(player, turn.transfers)
        return turn

    def _parse_diary(self, player: str, raw: Any) -> DiaryTurn:
        turn = DiaryTurn.model_validate(_load(raw))
        others = [p for p in self.alive if p != player]
        unknown = sorted(set(turn.players) - set(others))
        if unknown:
            raise ValueError(f"Diary notes can only be about living players other than you: {others}. Not: {unknown}")
        return turn

    def _parse_action(self, player: str, raw: Any) -> tuple[str, BaseModel]:
        assert self.game is not None
        envelope = ActionEnvelope.model_validate(_load(raw))
        action = self.game.action_schema(player).model_validate(envelope.action)
        error = self.game.check_action(player, action)
        if error:
            raise ValueError(error)
        return envelope.private_reasoning, action

    def _default_action(self, player: str) -> tuple[str, BaseModel]:
        assert self.game is not None
        # Own RNG per request, so defaults do not depend on the order in which
        # concurrent API calls happen to finish.
        rng = random.Random(f"{self.seed}:{player}:{self._requests[player]}")
        choice = self.game.random_action(player, rng)
        return "", self.game.action_schema(player).model_validate(choice)

    def _check_recipient(self, player: str, to: str, allowed: list[str] | None = None) -> None:
        if to == player:
            raise ValueError("You cannot send messages or Pieces to yourself.")
        if to not in self.alive:
            raise ValueError(f"{to!r} is not a living player. Living players: {self.alive}")
        if allowed is not None and to not in allowed:
            raise ValueError(f"{to!r} is not in this conversation. Players here: {allowed}")

    def _check_transfers(
        self, player: str, transfers: list[Transfer], extra_cost: int = 0, allowed: list[str] | None = None
    ) -> None:
        for transfer in transfers:
            self._check_recipient(player, transfer.to, allowed)
        total = sum(t.pieces for t in transfers) + extra_cost
        if total > self.pieces[player]:
            what = "give and spend" if extra_cost else "give"
            raise ValueError(
                f"You tried to {what} {total} Pieces but you only have {self.pieces[player]}."
            )

    # ---------------------------------------------------------- effects

    def _transfer(self, sender: str, transfer: Transfer, *, last_will: bool = False) -> None:
        self.pieces[sender] -= transfer.pieces
        self.pieces[transfer.to] += transfer.pieces
        self.log.emit(
            "transfer",
            {"to": transfer.to, "pieces": transfer.pieces, "last_will": last_will},
            actor=sender,
        )

    def _log_reasoning(self, player: str, reasoning: str) -> None:
        if reasoning:
            self.log.emit("reasoning", {"text": reasoning}, actor=player, visible_to=GOD)


async def _all(*coros: Awaitable[T]) -> list[T]:
    """Run concurrently, like asyncio.gather. If one agent fails, the others'
    pending calls are cancelled instead of running on after the run stopped."""
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(c) for c in coros]
    except ExceptionGroup as errors:
        failures = [e for e in errors.exceptions if isinstance(e, RunHalted)]
        if failures:
            raise failures[0] from None
        raise
    return [task.result() for task in tasks]


def _load(raw: Any) -> dict[str, Any]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("Response must be a JSON object.")
    return data


def _jsonable(raw: Any) -> Any:
    try:
        json.dumps(raw)
        return raw
    except TypeError:
        return repr(raw)
