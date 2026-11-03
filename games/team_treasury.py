"""Day 1 — Team Treasury: the bonding day (spec §3).

A team game in the spirit of the show's cooperative Prize Matches, built as a
threshold public-goods game. Over 3 rounds everyone secretly puts 0-2 Pieces
into a shared treasury; contributions are then revealed by name. If the total
reaches the goal, every player gets the bonus, including those who paid
nothing. If not, everything paid in is lost. Nobody is eliminated today.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

ROUNDS = 3
MAX_CONTRIBUTION = 2
BONUS = 4
GOAL_PER_PLAYER = 1.6  # 8 with 5 players, 10 with 6


class ContributeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contribute: int


def team_goal(players: int) -> int:
    return round(GOAL_PER_PLAYER * players)


class TeamTreasury(Game):
    name = "Team Treasury"
    min_players = 3
    max_players = 6
    eliminates = False
    lounge_exchanges: ClassVar[int] = 10  # a long first conversation: time to bond

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.goal = team_goal(len(self.players))
        self.contributed: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0
        self.t: Tournament | None = None

    @property
    def rules(self) -> str:
        return (
            "GAME: Team Treasury. This is a TEAM DAY: nobody is eliminated today and there "
            "are no placement rewards.\n"
            f"- {ROUNDS} rounds. Each round starts with a chat phase, then every player "
            f"secretly puts 0-{MAX_CONTRIBUTION} of their own Pieces into a shared treasury.\n"
            "- After each round, everyone's contribution is revealed by name.\n"
            f"- If the treasury reaches {self.goal} Pieces in total by the end, EVERY player "
            f"gets +{BONUS} Pieces, including players who put in nothing. If it does not, "
            "all Pieces put in are lost.\n"
            f"Example (5 players, goal {self.goal}): A, B and C put in 2 each over the game, D "
            "puts in 2, E puts in 0. The total is 8, so the goal is reached: everyone gets "
            f"+{BONUS}. A, B, C and D end with {BONUS - 2} more Pieces than they paid in; E "
            f"ends with {BONUS} more."
        )

    def total(self) -> int:
        return sum(self.contributed.values())

    async def play(self, t: Tournament) -> Ranking:
        self.t = t
        t.log.emit(
            "game_start",
            {"game": self.name, "players": self.players, "rounds": ROUNDS, "goal": self.goal, "bonus": BONUS},
        )
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            await t.chat_phase()
            actions = await t.collect_actions(self.players)
            amounts = {p: actions[p].contribute for p in self.players}
            for player, amount in amounts.items():
                if amount:
                    t.adjust_pieces(player, -amount, "team treasury contribution")
                self.contributed[player] += amount
            result = {"round": self.round, "contributions": amounts, "total": self.total()}
            self.results.append(result)
            t.log.emit("contributions", {**result, "goal": self.goal, "by_player": dict(self.contributed)})

        t.log.set_context(round=None)
        success = self.total() >= self.goal
        t.log.emit(
            "team_result",
            {"success": success, "total": self.total(), "goal": self.goal, "bonus": BONUS if success else 0},
        )
        if success:
            for player in self.players:
                t.adjust_pieces(player, +BONUS, "team goal reached")
        return [list(self.players)]

    def _max_contribution(self, player: str) -> int:
        assert self.t is not None
        return min(MAX_CONTRIBUTION, self.t.pieces[player])

    def private_view(self, player: str) -> dict[str, Any]:
        return {}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "goal": self.goal,
            "total_so_far": self.total(),
            "contributed_by_player": dict(self.contributed),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return ContributeAction

    def action_help(self, player: str) -> str:
        top = self._max_contribution(player)
        return f'Put 0-{top} of your Pieces into the treasury: {{"contribute": <0-{top}>}}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"contribute": k} for k in range(self._max_contribution(player) + 1)]
