"""Halloween Monster (S2 day 3), adapted.

Each round a monster appears that is too strong for one player. Players secretly
play a weapon card and name a party leader to join. A party whose total power
reaches the monster's strength defeats it; if several do, only the strongest
does. The leader of the winning party then splits the monster's points among
the party however they like. Most points ranks first.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from games.base import Game, Ranking, rank_by_score

if TYPE_CHECKING:
    from engine.tournament import Tournament

ROUNDS = 4
CARDS_PER_PLAYER = 5
CARD_VALUES = range(1, 6)


class AttackAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: int
    leader: str


class SplitAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allocation: dict[str, int]


class HalloweenMonster(Game):
    name = "Halloween Monster"
    min_players = 3
    max_players = 12

    def __init__(self, players, rng) -> None:
        super().__init__(players, rng)
        n = min(len(self.players), 6)  # monsters sized for parties of a few players
        self.hands: dict[str, list[int]] = {
            p: sorted(rng.choice(CARD_VALUES) for _ in range(CARDS_PER_PLAYER)) for p in self.players
        }
        self.monsters = [
            {"strength": rng.randint(2 * n, 3 * n), "points": rng.choice([4, 5, 6])} for _ in range(ROUNDS)
        ]
        self.points: dict[str, int] = {p: 0 for p in self.players}
        self.results: list[dict[str, Any]] = []
        self.round = 0
        self.stage = "attack"
        self.splitting: dict[str, Any] | None = None  # {"leader", "members", "points"}

    @property
    def rules(self) -> str:
        return (
            "GAME: Halloween Monster.\n"
            f"- Every player gets {CARDS_PER_PLAYER} secret weapon cards (values "
            f"{CARD_VALUES.start}-{CARD_VALUES.stop - 1}). A played card is used up.\n"
            f"- {ROUNDS} rounds. Each round a monster appears with a strength and a point value, "
            "usually too strong for one player alone.\n"
            "- Each round: conversation, then everyone secretly plays one card (or 0 to rest) and "
            "names a party leader: yourself to lead, or another player to join their party. If the "
            "player you join is not leading this round, you fight alone.\n"
            "- A party's power is the sum of its cards. A party whose power reaches the monster's "
            "strength defeats it. If several parties do, only the strongest wins (a tie: nobody).\n"
            "- The winning party's leader then splits the monster's points among the party members "
            "however they want. Nobody else gets points.\n"
            "- Most points at the end ranks first.\n"
            "Example: a monster has strength 14 and 6 points. B leads; A and C join B. They play "
            "5, 4 and 5 = 14, so they defeat it. B then decides the split, e.g. B 2, A 2, C 2, or "
            "B 6, A 0, C 0."
        )

    async def play(self, t: Tournament) -> Ranking:
        t.log.emit("game_start", {"game": self.name, "players": self.players, "monsters": ROUNDS})
        t.log.emit("deal", {"hands": {p: list(h) for p, h in self.hands.items()}}, visible_to="god")
        for self.round in range(1, ROUNDS + 1):
            t.log.set_context(round=self.round)
            monster = self.monsters[self.round - 1]
            t.log.emit("monster", {"round": self.round, **monster})
            await t.chat_phase()
            self.stage = "attack"
            actions = await t.collect_actions(self.players)
            await self._resolve(t, monster, actions)
        t.log.set_context(round=None)
        return rank_by_score(self.points)

    async def _resolve(self, t: Tournament, monster: dict[str, int], actions: dict[str, Any]) -> None:
        for p, a in actions.items():
            if a.card:
                self.hands[p].remove(a.card)
        leaders = {p for p, a in actions.items() if a.leader == p}
        parties: dict[str, list[str]] = {}
        for p, a in actions.items():
            key = a.leader if a.leader in leaders else p
            parties.setdefault(key, []).append(p)
        power = {k: sum(actions[m].card for m in members) for k, members in parties.items()}
        strong = [k for k, v in power.items() if v >= monster["strength"]]
        winner = None
        if strong:
            best = max(power[k] for k in strong)
            top = [k for k in strong if power[k] == best]
            winner = top[0] if len(top) == 1 else None
        result = {
            "round": self.round,
            "parties": {k: {"members": sorted(m), "power": power[k]} for k, m in parties.items()},
            "plays": {p: actions[p].card for p in self.players},
            "winner_party": winner,
        }
        if winner is None:
            result["allocation"] = {}
        else:
            members = sorted(parties[winner])
            if len(members) == 1:
                allocation = {members[0]: monster["points"]}
            else:
                self.stage = "split"
                self.splitting = {"leader": winner, "members": members, "points": monster["points"]}
                allocation = (await t.collect_actions([winner]))[winner].allocation
                self.splitting = None
                self.stage = "attack"
            for p, pts in allocation.items():
                self.points[p] += pts
            result["allocation"] = allocation
        self.results.append(result)
        t.log.emit("monster_result", {**result, "points": dict(self.points)})

    def private_view(self, player: str) -> dict[str, Any]:
        return {"my_cards": list(self.hands[player])}

    def public_view(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "round": self.round,
            "rounds": ROUNDS,
            "monster": self.monsters[self.round - 1] if self.round else None,
            "points": dict(self.points),
            "cards_left": {p: len(h) for p, h in self.hands.items()},
            "results": list(self.results),
        }
        if self.splitting:
            view["splitting"] = dict(self.splitting)
        return view

    def action_schema(self, player: str) -> type[BaseModel]:
        return SplitAction if self.stage == "split" else AttackAction

    def action_help(self, player: str) -> str:
        if self.stage == "split" and self.splitting:
            s = self.splitting
            return (
                f'You lead the winning party {s["members"]}. Split {s["points"]} points among them: '
                '{"allocation": {"Player X": <points>, ...}} (whole numbers, total exactly '
                f'{s["points"]})'
            )
        return (
            f'{{"card": <one of your cards {sorted(set(self.hands[player]))}, or 0 to rest>, '
            f'"leader": <yourself to lead, or the player whose party you join>}}'
        )

    def legal_actions(self, player: str) -> list[dict[str, Any]] | None:
        if self.stage == "split":
            return None
        cards = [0] + sorted(set(self.hands[player]))
        return [{"card": c, "leader": leader} for c in cards for leader in self.players]

    def check_action(self, player: str, action: BaseModel) -> str | None:
        if self.stage != "split":
            return super().check_action(player, action)
        s = self.splitting
        assert s is not None
        alloc = action.allocation
        if set(alloc) - set(s["members"]):
            return f"You can only give points to party members {s['members']}."
        if any(v < 0 for v in alloc.values()):
            return "Points cannot be negative."
        if sum(alloc.values()) != s["points"]:
            return f"The split must add up to exactly {s['points']} points."
        return None

    def random_action(self, player: str, rng: random.Random) -> dict[str, Any]:
        if self.stage != "split":
            return super().random_action(player, rng)
        s = self.splitting
        assert s is not None
        members, points = s["members"], s["points"]
        allocation = {m: points // len(members) for m in members}
        for m in members[: points % len(members)]:
            allocation[m] += 1
        return {"allocation": allocation}
