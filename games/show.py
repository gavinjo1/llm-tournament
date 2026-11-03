"""Game pools for the show format (Devil's Plan season 2 structure).

Each day a main match is drawn at random from MAIN_POOL and, after it, a
prison match from PRISON_POOL, among the games that fit the number of
players. A game is not drawn twice in one tournament while others remain.
"""

from __future__ import annotations

import random

from games.base import Game
from games.equation_group import EquationHighLowGroup
from games.equation_pyramid import EquationPyramid
from games.final import Final
from games.halloween import HalloweenMonster
from games.liars_dice import LiarsDice
from games.mancala import BalanceMancala
from games.remove_one import RemoveOne
from games.secret_number import SecretNumber
from games.sniper_holdem import SniperHoldem
from games.time_auction import TimeAuction
from games.triple_dice import TripleDice
from games.virus import VirusGame

MAIN_POOL: list[type[Game]] = [
    VirusGame,
    HalloweenMonster,
    BalanceMancala,
    EquationHighLowGroup,
    SecretNumber,  # 3-5 players; clues cost Pieces, so it only appears later
    LiarsDice,
]
PRISON_POOL: list[type[Game]] = [
    RemoveOne,
    TimeAuction,
    SniperHoldem,
    TripleDice,
    EquationPyramid,
    LiarsDice,
]
FINAL = Final


def draw(pool: list[type[Game]], players: int, used: set[str], rng: random.Random) -> type[Game]:
    """A random game for this many players, preferring ones not played yet."""
    fits = [g for g in pool if g.min_players <= players <= g.max_players]
    if not fits:
        raise ValueError(f"No game in the pool fits {players} players")
    fresh = [g for g in fits if g.name not in used]
    choice = rng.choice(fresh or fits)
    used.add(choice.name)
    return choice
