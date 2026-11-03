"""Tournament schedules, chosen by the number of players (spec §1).

5 players is the main design: a team day, then one elimination per day. 6
players adds the 4-player Time Auction day, kept ready for a sixth LLM later.
"""

from games.final import Final
from games.liars_dice import LiarsDice
from games.remove_one import RemoveOne
from games.secret_number import SecretNumber
from games.team_treasury import TeamTreasury
from games.time_auction import TimeAuction

SCHEDULES = {
    5: [TeamTreasury, RemoveOne, SecretNumber, LiarsDice, Final],
    6: [TeamTreasury, RemoveOne, SecretNumber, TimeAuction, LiarsDice, Final],
}

DEFAULT_SCHEDULE = SCHEDULES[5]
