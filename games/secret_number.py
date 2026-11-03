"""Day 2 — Secret Number (spec §3).

Each player has a secret number from 1-100 that everyone can see except the
player itself. Over 3 negotiation rounds players trade (true or false) hints,
and may buy a truthful official clue for 1 Piece. Then everyone guesses their
own number; the smallest error ranks first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

LOW, HIGH = 1, 100
ROUNDS = 3
MAX_CLUES = 3
CLUE_COST = 1


class ClueAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clue: int | None = None
    """Ask "is my number higher than X?". None = no clue this round."""


class GuessAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guess: int


class SecretNumber(Game):
    name = "Secret Number"
    min_players = 3
    max_players = 12
    rules = (
        "GAME: Secret Number.\n"
        f"- Every player has a different secret number from {LOW}-{HIGH}. You can see "
        "everyone's number EXCEPT your own.\n"
        f"- There are {ROUNDS} negotiation rounds. Each round there is a chat phase, then "
        f"you may buy an official clue for {CLUE_COST} Piece: ask \"is my number higher "
        f"than X?\" and get a truthful private answer. Max {MAX_CLUES} clues per game.\n"
        "- Anything players tell each other may be a lie. Official clues are always true.\n"
        "- After the last round, everyone secretly guesses their own number.\n"
        "- Placement is by distance between guess and number, smallest first. An exact "
        "guess earns +1 extra Piece.\n"
        "Example: your number is 42, but you cannot see it. You pay 1 Piece for the clue "
        "\"higher than 50?\" and get NO. Another player tells you \"your number is about "
        "70\" - your clue shows that was false. You guess 40: your distance is 2."
    )

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        numbers = rng.sample(range(LOW, HIGH + 1), len(self.players))
        self.numbers: dict[str, int] = dict(zip(self.players, numbers))
        self.clues: dict[str, list[dict[str, Any]]] = {p: [] for p in self.players}
        self.round = 0
        self.stage = "clue"
        self.t: Tournament | None = None

    async def play(self, t: Tournament) -> Ranking:
        self.t = t
        t.log.emit("game_start", {"game": self.name, "players": self.players, "rounds": ROUNDS})
        t.log.emit("deal", {"numbers": dict(self.numbers)}, visible_to="god")

        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            await t.chat_phase()
            self.stage = "clue"
            actions = await t.collect_actions(self.players)
            for player in self.players:
                x = actions[player].clue
                if x is None:
                    continue
                higher = self.numbers[player] > x
                self.clues[player].append({"round": self.round, "higher_than": x, "answer": higher})
                t.adjust_pieces(player, -CLUE_COST, "official clue")
                t.log.emit(
                    "clue_result",
                    {"higher_than": x, "answer": higher},
                    actor=player,
                    visible_to=[player],
                )

        t.log.set_context(round=None)
        self.stage = "guess"
        actions = await t.collect_actions(self.players)
        guesses = {p: actions[p].guess for p in self.players}
        errors = {p: abs(guesses[p] - self.numbers[p]) for p in self.players}
        t.log.emit(
            "reveal",
            {"numbers": dict(self.numbers), "guesses": guesses, "errors": errors},
        )
        for player in self.players:
            if errors[player] == 0:
                t.adjust_pieces(player, +1, "exact guess bonus")
        return rank_by_score({p: -e for p, e in errors.items()})

    def _can_buy_clue(self, player: str) -> bool:
        assert self.t is not None
        return len(self.clues[player]) < MAX_CLUES and self.t.pieces[player] >= CLUE_COST

    def private_view(self, player: str) -> dict[str, Any]:
        return {
            "others_numbers": {p: n for p, n in self.numbers.items() if p != player},
            "my_clues": list(self.clues[player]),
            "clues_left": MAX_CLUES - len(self.clues[player]),
        }

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "rounds": ROUNDS,
            "stage": self.stage,
            "clues_bought": {p: len(c) for p, c in self.clues.items()},
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return ClueAction if self.stage == "clue" else GuessAction

    def action_help(self, player: str) -> str:
        if self.stage == "guess":
            return f'Guess your own number: {{"guess": <{LOW}-{HIGH}>}}'
        if not self._can_buy_clue(player):
            return 'You cannot buy a clue now (no clues left or no Pieces): {"clue": null}'
        return (
            f'Buy a clue for {CLUE_COST} Piece with {{"clue": X}} (X from {LOW}-{HIGH - 1}, '
            'answers "is my number higher than X?"), or skip with {"clue": null}'
        )

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        if self.stage == "guess":
            return [{"guess": g} for g in range(LOW, HIGH + 1)]
        skip: list[dict[str, Any]] = [{"clue": None}]
        if not self._can_buy_clue(player):
            return skip
        return skip + [{"clue": x} for x in range(LOW, HIGH)]
