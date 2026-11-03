"""The Virus Game (S1 day 1), adapted: a hidden-role game without voting.

Terrorists infect one player each night. The Officer can shoot one player
(once). The Cure holder can cure one infected player (once). The Researcher
tests one player each night for infection; the Journalist learns one player's
role each night. An infected player secretly switches to the terrorists' side.
After 3 nights, the terrorists' side wins if at least 2 players are infected.

Unlike the other games, roles are assigned here, as in the show.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking

if TYPE_CHECKING:
    from engine.tournament import Tournament

TERRORIST, OFFICER, CURE, RESEARCHER, JOURNALIST, CITIZEN = (
    "Terrorist", "Officer", "Cure holder", "Researcher", "Journalist", "Citizen",
)
ROLE_SETS = {
    5: [TERRORIST, OFFICER, CURE, RESEARCHER, CITIZEN],
    6: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, CITIZEN],
    7: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, JOURNALIST, CITIZEN],
    8: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, JOURNALIST] + [CITIZEN] * 2,
    9: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, JOURNALIST] + [CITIZEN] * 3,
    10: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, RESEARCHER, JOURNALIST] + [CITIZEN] * 3,
    11: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, RESEARCHER, JOURNALIST] + [CITIZEN] * 4,
    12: [TERRORIST, TERRORIST, OFFICER, CURE, RESEARCHER, RESEARCHER, JOURNALIST] + [CITIZEN] * 5,
}
NIGHTS = 3
INFECTIONS_TO_WIN = {n: (2 if n <= 7 else 3) for n in range(5, 13)}
WIN_REWARD = 4  # the show: the winning terrorists got 4 Pieces each
LOSS_PENALTY = 0


class NightAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str | None = None


class VirusGame(Game):
    name = "Virus Game"
    min_players = 5
    max_players = 12

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        roles = list(ROLE_SETS[len(self.players)])
        rng.shuffle(roles)
        self.role: dict[str, str] = dict(zip(self.players, roles))
        self.terrorists = [p for p in self.players if self.role[p] == TERRORIST]
        self.infected: set[str] = set()
        self.shot: set[str] = set()
        self.bullet = True
        self.cure_left = True
        self.notes: dict[str, list[str]] = {p: [] for p in self.players}
        self.night = 0
        self.shots_public: list[dict[str, Any]] = []
        self.finished = False

    @property
    def rules(self) -> str:
        roles = ROLE_SETS[len(self.players)]
        counts = ", ".join(f"{roles.count(r)} {r}" for r in dict.fromkeys(roles))
        need = INFECTIONS_TO_WIN[len(self.players)]
        return (
            "GAME: Virus Game. Every player secretly receives a role. There is NO voting.\n"
            f"- Roles in this game of {len(self.players)}: {counts}.\n"
            "- Terrorists know each other. Each night they choose one non-terrorist to infect "
            "(if they pick different targets, one of their picks is chosen at random).\n"
            "- Officer: may shoot one player, once per game. A shot player is out of this game "
            "(not the tournament) and can no longer act.\n"
            "- Cure holder: may cure one player, once per game. Curing an infected player removes "
            "the infection; curing a healthy player wastes the cure.\n"
            "- Researcher: each night tests one player and privately learns if they are infected.\n"
            "- Journalist: each night privately learns one player's role.\n"
            "- Citizen: no night action.\n"
            "- An infected player is told privately and secretly switches to the terrorists' side.\n"
            "- Each night: conversation, then night actions. Order: infection, cure, shot, then "
            "tests and reports. Shots are announced; infections and roles are not.\n"
            f"- After {NIGHTS} nights: the terrorists' side (terrorists + infected) wins if at least "
            f"{need} players are infected; otherwise the other players win.\n"
            f"- Rewards for this game: every player on the winning side gets +{WIN_REWARD} Pieces; the "
            "others get nothing (instead of the usual main-match rewards). All roles are revealed at "
            "the end.\n"
            "Example: night 1 the terrorists infect C; the Cure holder cures C, so C is healthy "
            "again. Night 2 they infect E and nobody cures E: E is told and now wins with the "
            "terrorists. One more infection by night 3 and the terrorists' side wins."
        )

    def main_rewards(self, ranking: Ranking) -> dict[str, int]:
        winners = set(ranking[0]) if len(ranking) > 1 or self.finished else set()
        return {p: WIN_REWARD if p in winners else LOSS_PENALTY for p in self.players}

    def side(self, player: str) -> str:
        return "terrorists" if self.role[player] == TERRORIST or player in self.infected else "citizens"

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "nights": NIGHTS})
        t.log.emit("roles", {"roles": dict(self.role)}, visible_to="god")
        for p in self.players:
            text = f"Your role: {self.role[p]}."
            if self.role[p] == TERRORIST:
                text += f" Terrorists: {', '.join(self.terrorists)}."
            self.notes[p].append(text)
            t.log.emit("role_info", {"text": text}, actor=p, visible_to=[p])

        for self.night in range(1, NIGHTS + 1):
            t.log.set_context(round=self.night)
            await t.chat_phase()
            askers = [p for p in self.players if len(self.legal_actions(p)) > 1]
            actions = await t.collect_actions(askers) if askers else {}
            target = {p: (actions[p].target if p in actions else None) for p in self.players}
            self._resolve(t, target)

        t.log.set_context(round=None)
        self.finished = True
        infected = sorted(self.infected)
        winner = "terrorists" if len(infected) >= INFECTIONS_TO_WIN[len(self.players)] else "citizens"
        winners = sorted(p for p in self.players if self.side(p) == winner)
        losers = sorted(p for p in self.players if p not in winners)
        t.log.emit(
            "virus_result",
            {"winner": winner, "infected": infected, "shot": sorted(self.shot), "roles": dict(self.role)},
        )
        return [winners, losers] if losers else [winners]

    def _resolve(self, t: Tournament, target: dict[str, str | None]) -> None:
        picks = [target[p] for p in self.terrorists if p not in self.shot and target[p]]
        if picks:
            victim = self.rng.choice(sorted(set(picks), key=picks.index))
            self.infected.add(victim)
            t.log.emit("infection", {"night": self.night, "player": victim}, visible_to="god")
            for p in self.terrorists:
                self.notes[p].append(f"Night {self.night}: you infected {victim}.")
            self.notes[victim].append(
                f"Night {self.night}: you were INFECTED. You now win with the terrorists "
                f"({', '.join(self.terrorists)})."
            )
            t.log.emit("infected_notice", {"night": self.night}, actor=victim, visible_to=[victim])

        for p, role in self.role.items():
            if p in self.shot or not target[p]:
                continue
            who = target[p]
            if role == CURE and self.cure_left:
                self.cure_left = False
                worked = who in self.infected
                self.infected.discard(who)
                self.notes[p].append(f"Night {self.night}: you used the cure on {who}.")
                if worked:
                    self.notes[who].append(f"Night {self.night}: you were cured and are healthy again.")
                t.log.emit("cure", {"night": self.night, "player": who, "worked": worked}, actor=p, visible_to="god")

        shots = []
        for p, role in self.role.items():
            if role == OFFICER and p not in self.shot and target[p] and self.bullet:
                self.bullet = False
                shots.append(target[p])
        for who in shots:
            self.shot.add(who)
        self.shots_public.append({"night": self.night, "shot": shots})
        t.log.emit("night_result", {"night": self.night, "shot": shots})

        for p, role in self.role.items():
            if p in self.shot or not target[p]:
                continue
            who = target[p]
            if role == RESEARCHER:
                text = f"Night {self.night}: {who} is {'INFECTED' if who in self.infected else 'not infected'}."
            elif role == JOURNALIST:
                text = f"Night {self.night}: {who}'s role is {self.role[who]}."
            else:
                continue
            self.notes[p].append(text)
            t.log.emit("investigation", {"text": text}, actor=p, visible_to=[p])

    def private_view(self, player: str) -> dict[str, Any]:
        view: dict[str, Any] = {"role": self.role[player], "side": self.side(player), "notes": list(self.notes[player])}
        if self.role[player] == OFFICER:
            view["bullet_left"] = self.bullet
        if self.role[player] == CURE:
            view["cure_left"] = self.cure_left
        return view

    def public_view(self) -> dict[str, Any]:
        view: dict[str, Any] = {"night": self.night, "nights": NIGHTS, "shots": list(self.shots_public)}
        if self.finished:
            view["roles"] = dict(self.role)
        return view

    def action_schema(self, player: str) -> type[BaseModel]:
        return NightAction

    def _targets(self, player: str) -> list[str]:
        role = self.role[player]
        if player in self.shot:
            return []
        if role == TERRORIST:
            return [p for p in self.players if p not in self.terrorists and p not in self.shot]
        if role == OFFICER and self.bullet:
            return [p for p in self.players if p != player and p not in self.shot]
        if role == CURE and self.cure_left:
            return [p for p in self.players if p not in self.shot]
        if role in (RESEARCHER, JOURNALIST):
            return [p for p in self.players if p != player and p not in self.shot]
        return []

    def action_help(self, player: str) -> str:
        targets = self._targets(player)
        verb = {TERRORIST: "infect", OFFICER: "shoot", CURE: "cure", RESEARCHER: "test",
                JOURNALIST: "investigate"}.get(self.role[player], "act on")
        return f'Night action ({self.role[player]}): {{"target": one of {targets}}} to {verb}, or {{"target": null}} to skip'

    def legal_actions(self, player: str) -> list[dict[str, Any]]:
        return [{"target": None}] + [{"target": p} for p in self._targets(player)]
