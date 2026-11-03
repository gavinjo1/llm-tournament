"""Suit Survival, inspired by the suit-guessing game in Alice in Borderland.

Every round each living player is given a random suit (hearts, diamonds,
spades or clubs). Everyone can see every other player's suit, but not their
own. After a conversation, each player secretly guesses their own suit: a
wrong guess is elimination from the tournament. Suits are dealt again every
round. Last player standing wins.

No roles are assigned: survival depends entirely on what the others tell you,
so any lie comes from the player's own choice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

SUITS = ("hearts", "diamonds", "spades", "clubs")
MAX_ROUNDS = 30  # if everyone keeps guessing right, the game ends here with no single winner


class GuessAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guess: str


class SuitSurvival(Game):
    name = "Suit Survival"
    min_players = 2
    max_players = 26
    self_eliminating: ClassVar[bool] = True
    lounge_exchanges: ClassVar[int] = 4

    rules = (
        "GAME: Suit Survival. This game decides the whole tournament: the last player alive wins.\n"
        "- Every round, each living player is secretly given a random suit: hearts, diamonds, "
        "spades or clubs. Several players can have the same suit.\n"
        "- You can see every other player's suit, but NOT your own.\n"
        "- Each round there is a conversation. Then every living player secretly guesses their "
        "own suit. A WRONG guess means you are ELIMINATED. A right guess means you survive.\n"
        "- After the guesses, everyone's suit and guess is revealed to all.\n"
        "- If every living player guesses wrong in the same round, they are ALL eliminated and "
        "NOBODY wins.\n"
        f"- The game lasts at most {MAX_ROUNDS} rounds. If more than one player is still alive "
        "then, there is no winner.\n"
        "- Suits are dealt again at random every round, so last round's suit tells you nothing.\n"
        "- Nobody is assigned a role. What others tell you about your suit may be true or false.\n"
        "Example (3 players): A is hearts, B is clubs, C is hearts. A sees B=clubs and C=hearts but "
        "not their own. B tells A \"you are spades\"; C tells A \"you are hearts\". A guesses hearts "
        "and survives; had A believed B, A would be eliminated."
    )

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.suits: dict[str, str] = {}
        self.round = 0
        self.results: list[dict[str, Any]] = []
        self.t: Tournament | None = None

    def living(self) -> list[str]:
        assert self.t is not None
        return [p for p in self.players if p in self.t.alive]

    async def play(self, t: Tournament) -> Ranking:
        self.t = t
        t.log.emit("game_start", {"game": self.name, "players": self.players})
        out_order: list[str] = []
        while len(self.living()) > 1 and self.round < MAX_ROUNDS:
            self.round += 1
            t.log.set_context(round=self.round)
            alive = self.living()
            self.suits = {p: self.rng.choice(SUITS) for p in alive}
            t.log.emit("suits", {"suits": dict(self.suits)}, visible_to="god")
            await t.chat_phase(speakers=alive)
            actions = await t.collect_actions(alive)
            guesses = {p: actions[p].guess for p in alive}
            wrong = [p for p in alive if guesses[p] != self.suits[p]]
            result = {
                "round": self.round,
                "suits": dict(self.suits),
                "guesses": guesses,
                "wrong": wrong,
                "everyone_out": len(wrong) == len(alive),
            }
            self.results.append(result)
            t.log.emit("suit_result", result)
            for p in wrong:
                t.eliminate(p, "guessed their suit wrong")
            if wrong:
                out_order.append(sorted(wrong))
        t.log.set_context(round=None)
        survivors = self.living()
        if len(survivors) > 1:
            t.log.emit("no_winner", {"reason": f"{len(survivors)} players still alive after {MAX_ROUNDS} rounds",
                                     "survivors": survivors})
        elif not survivors:
            t.log.emit("no_winner", {"reason": "everyone left was eliminated in the same round", "survivors": []})
        ranking: Ranking = [sorted(survivors)] if survivors else []
        return ranking + list(reversed(out_order))

    def private_view(self, player: str) -> dict[str, Any]:
        return {"others_suits": {p: s for p, s in self.suits.items() if p != player}}

    def public_view(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "alive": self.living() if self.t else list(self.players),
            "results": list(self.results),
        }

    def action_schema(self, player: str) -> type[BaseModel]:
        return GuessAction

    def action_help(self, player: str) -> str:
        return 'Guess your own suit: {"guess": "hearts" | "diamonds" | "spades" | "clubs"}'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"guess": s} for s in SUITS]


class HiddenPlayerSuits(SuitSurvival):
    """Suit Survival with a hidden player, after the Jack of Hearts game in the
    Alice in Borderland manga (prompts say "Hidden Player" so models reason
    about this game rather than recall the story).

    One random player is secretly the Hidden Player; everyone else is a
    citizen. Everyone, the Hidden Player included, must guess their own suit.
    When the Hidden Player guesses wrong, every citizen still alive wins. If the
    Hidden Player is left with only one other player, that player is
    eliminated and the Hidden Player wins. Only eliminations are revealed;
    guesses stay secret.
    """

    name = "Hidden Player"
    min_players = 3

    rules = (
        "GAME: Hidden Player. This game decides the whole tournament.\n"
        "- One player is secretly the HIDDEN PLAYER. Everyone else is a citizen. Only the Hidden "
        "Player knows who it is.\n"
        "- Every round, each living player is secretly given a random suit: hearts, diamonds, "
        "spades or clubs (repeats possible). You see every other player's suit, never your own. "
        "Suits are dealt again every round.\n"
        "- Each round there is a conversation. Then EVERY living player, the Hidden Player "
        "included, secretly guesses their own suit. A wrong guess means ELIMINATION.\n"
        "- After each round, everyone learns who was eliminated. Guesses stay secret.\n"
        "- CITIZENS WIN (all citizens still alive) the moment the Hidden Player guesses wrong.\n"
        "- THE HIDDEN PLAYER WINS when only the Hidden Player and one other player are left: that "
        "other player is eliminated.\n"
        f"- If the game reaches {MAX_ROUNDS} rounds, everyone loses.\n"
        "- What others tell you about your suit may be true or false.\n"
        "Example (5 players): C is secretly the Hidden Player and is spades. A and B suspect C and "
        "both tell C \"you are hearts\". C believes them, guesses hearts and is eliminated: A, B, D "
        "and E win. Had A and B picked the wrong suspect, an innocent citizen would have died "
        "instead."
    )

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        self.hidden = rng.choice(self.players)

    def role(self, player: str) -> str:
        return "Hidden Player" if player == self.hidden else "citizen"

    async def play(self, t: Tournament) -> Ranking:
        self.t = t
        t.log.emit("game_start", {"game": self.name, "players": self.players})
        t.log.emit("hidden_player", {"player": self.hidden}, visible_to="god")
        for p in self.players:
            t.log.emit("role_info", {"text": f"Your role: {self.role(p)}."}, actor=p, visible_to=[p])
        out_order: list[list[str]] = []
        while True:
            if self.round >= MAX_ROUNDS:
                t.log.emit("no_winner", {"reason": f"{MAX_ROUNDS} rounds reached: everyone loses",
                                         "survivors": self.living()})
                break
            self.round += 1
            t.log.set_context(round=self.round)
            alive = self.living()
            self.suits = {p: self.rng.choice(SUITS) for p in alive}
            t.log.emit("suits", {"suits": dict(self.suits)}, visible_to="god")
            await t.chat_phase(speakers=alive)
            actions = await t.collect_actions(alive)
            guesses = {p: actions[p].guess for p in alive}
            wrong = sorted(p for p in alive if guesses[p] != self.suits[p])
            t.log.emit("guesses", {"suits": dict(self.suits), "guesses": guesses}, visible_to="god")
            self.results.append({"round": self.round, "eliminated": wrong})
            t.log.emit("hidden_round", {"round": self.round, "eliminated": wrong,
                                        "their_suits": {p: self.suits[p] for p in wrong}})
            for p in wrong:
                t.eliminate(p, "guessed their suit wrong")
            if wrong:
                out_order.append(wrong)

            living = self.living()
            if self.hidden in wrong:
                if living:
                    t.log.emit("game_clear", {"hidden_player": self.hidden, "winners": living})
                else:
                    t.log.emit("no_winner", {"reason": "everyone was eliminated in the same round",
                                             "survivors": []})
                break
            if len(living) <= 2:
                others = [p for p in living if p != self.hidden]
                for p in others:
                    t.eliminate(p, "left alone with the Hidden Player")
                    out_order.append([p])
                t.log.emit("hidden_player_wins", {"hidden_player": self.hidden})
                break
        t.log.set_context(round=None)
        survivors = self.living()
        return ([sorted(survivors)] if survivors else []) + list(reversed(out_order))

    def private_view(self, player: str) -> dict[str, Any]:
        return {**super().private_view(player), "your_role": self.role(player)}
