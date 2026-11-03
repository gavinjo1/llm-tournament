"""Rule text shown to players. Game-specific rules live with each game."""

from __future__ import annotations


def global_rules(communication: str, start_pieces: int, life_price: int | None = None) -> str:
    """The classic format: one game per day, fewest Pieces is eliminated."""
    lines = [
        "You are a player in a multi-day elimination tournament.",
        f"- Every player starts with {start_pieces} Pieces. Everyone's Piece count is public.",
        "- One game is played per day. On a team day nobody is eliminated (that day's "
        "rules say so). On the other days, Pieces are awarded by placement after the game.",
        "- Then the player with the fewest Pieces is eliminated. Ties: lower placement in "
        "that day's game is eliminated, then a random draw.",
        "- Pieces never go below 0.",
        "  Example: after today's rewards A has 5 Pieces, B has 2 and C has 2. B and C are "
        "tied for fewest; whichever of them placed lower in today's game is eliminated.",
        "- The last player standing wins the tournament.",
    ]
    return "\n".join(lines + _shared_lines(communication, life_price))


def global_rules_show(
    communication: str,
    start_pieces: int,
    main_rewards: tuple[int, ...],
    main_penalties: tuple[int, ...],
    prison_seats: int,
    prison_win: int,
) -> str:
    """The show format: main match, prison choice, prison match, 0 Pieces = out."""
    places = ("1st", "2nd", "3rd", "4th")
    top = ", ".join(f"{p} {r:+d}" for p, r in zip(places, main_rewards))
    ends = ["last"] + [f"{n}-to-last" for n in ("2nd", "3rd", "4th")]
    bottom = ", ".join(f"{ends[i]} {r:+d}" for i, r in enumerate(reversed(main_penalties)))
    lines = [
        "You are a player in a multi-day elimination tournament.",
        f"- Every player starts with {start_pieces} Piece{'s' if start_pieces != 1 else ''}. "
        "Everyone's Piece count is public. Pieces never go below 0.",
        "- A player with 0 Pieces is ELIMINATED, both right after the main match and at the end of "
        "the day. Exception: nobody is eliminated for 0 Pieces on day 1.",
        "- Each day starts with a MAIN MATCH that everyone plays. Pieces are won and lost by its "
        f"rules; unless the game says otherwise: {top}, {bottom}, everyone else 0 (losses only "
        "ever apply to the lower half).",
        f"- Then {prison_seats} players go to PRISON. The player with the FEWEST Pieces goes "
        "automatically. The player(s) with the MOST Pieces choose who fills the remaining "
        "seat(s): they may choose ANY other living player. Tied leaders talk privately, then "
        "vote (a tied vote is settled by a random draw). The decision and every vote are "
        "announced to everyone. If several players share the fewest Pieces, they all go when "
        "they fit the seats; if more of them are tied than there are seats, the leaders choose "
        "which of them go.",
        f"- Prisoners play a PRISON MATCH: the loser is ELIMINATED; the winner gets +{prison_win} "
        "Piece. If the match ends in a tie, a random draw (not Pieces) decides who loses, and "
        "the prisoner who survives the draw counts as the winner and gets the Piece.",
        "- The games change every day. You learn each game's rules only when it starts.",
        "- When two players remain, they play a final (best of three) for the win.",
        "- The last player standing wins the tournament.",
        "  Example: after the main match, D has 1 Piece, everyone else has more, and A has the "
        "most. D goes to prison, and A chooses any other player, say B, to join D. The prison "
        "match loser is eliminated.",
    ]
    return "\n".join(lines + _shared_lines(communication, None))


def _shared_lines(communication: str, life_price: int | None) -> list[str]:
    lines = []
    if life_price is not None and communication != "none":
        lines.append(
            f"- Lives: in any conversation before the final day you may buy a life for "
            f"{life_price} Pieces. You can hold at most one, and who holds one is public. If "
            "you would be eliminated while holding a life, the life is used instead and the "
            "next player in line is eliminated. Lives do nothing in the final."
        )
    if communication == "none":
        lines.append("- There is no communication between players in this tournament.")
    else:
        lines.append(
            "- Before each game and each round there is a conversation. It runs in "
            "exchanges: in each exchange everyone may speak at the same time and sees "
            "what was said before, so you can reply to each other. The conversation "
            "ends when nobody says or gives anything in an exchange, or at its limit."
        )
        lines.append(
            "- In each exchange you may send one public message (max 80 words) and give "
            "any number of your Pieces to players in the conversation. Transfers are "
            "immediate, irreversible and public."
        )
        if communication == "private":
            lines.append(
                "- You may also send up to 2 private messages per exchange (max 60 words "
                "each), each to one player in the conversation. Only you and the recipient "
                "see them."
            )
        lines.append(
            "- You may offer or accept deals, for example Pieces now or later in exchange "
            "for help. The game does not enforce deals or messages: whether to pay, keep "
            "a promise, lie or break a deal is each player's own decision."
        )
    lines.append(
        "- When you are eliminated you may give your remaining Pieces to living players "
        "(Last Will). Pieces you keep are removed from play."
    )
    return lines


MEMORY_TEXT = {
    "facts": (
        "- Memory: from the next day on you no longer see earlier days' conversations. "
        "For earlier days you see only the key public results: placements, transfers, "
        "prison decisions, game results and eliminations."
    ),
    "diary": (
        "- Memory: at the end of each day you write a private diary that no other player "
        "sees. From the next day on you no longer see earlier days' conversations. For "
        "earlier days you see only the key public results (placements, transfers, prison "
        "decisions, game results, eliminations) and your own diary entries."
    ),
}


def placement_text(table: list[int]) -> str:
    places = ", ".join(f"{i}: {r:+d}" for i, r in enumerate(table, start=1))
    return (
        f"Placement rewards in Pieces ({places}). Tied players each receive the "
        "average of the tied places' rewards, rounded down."
    )


PHASE_TEXT = {
    "main": "THIS IS THE MAIN MATCH. Everyone plays. Afterwards the player with the fewest Pieces "
    "goes to prison, and the player(s) with the most Pieces choose who joins them.",
    "prison": "THIS IS A PRISON MATCH. Only the prisoners play. The loser is ELIMINATED; the winner "
    "gains Pieces. If the match ends in a tie, a random draw decides who loses.",
    "choose": "THIS IS THE PRISON DECISION. You hold the most Pieces, so you decide who goes to prison.",
}
