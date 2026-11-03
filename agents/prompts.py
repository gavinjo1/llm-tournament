"""Turn an Observation into chat messages for an LLM.

Kept separate from the API code so the exact prompts can be read, tested and
quoted in the methodology chapter.
"""

from __future__ import annotations

import json
from typing import Any

from engine.agent import Observation

MAX_LISTED_ACTIONS = 12
MAX_NOTES = 8

# memory="full": event types kept from earlier days; the current day is shown in full.
EARLIER_DAY_TYPES = {
    "day_start",
    "public_message",
    "private_message",
    "transfer",
    "placement",
    "elimination",
    "tie_break_draw",
}

SKIPPED_TYPES = {"tournament_start", "game_start", "conversation_start", "conversation_end"}

# memory="facts"/"diary": earlier days are shown only as these key public results,
# one line each, with no conversations. Results of individual rounds are kept
# because they show what players actually did (who doubted whom, who led the
# winning party and how they split the points, what was played).
KEY_FACT_TYPES = {
    "day_start", "transfer", "placement", "elimination", "tie_break_draw", "life_used",
    "prison", "prison_start", "prison_result",
    "doubt", "out_of_dice", "monster_result", "reveal", "mancala_result", "round_result",
    "auction_result", "group_hand_result", "hand_result", "holdem_result", "dice_result",
    "pyramid_result", "night_result", "virus_result", "team_result", "suit_result",
    "hidden_round", "final_game_result",
}
# Bulky fields left out of one-line facts (hidden hands, running totals).
BULKY_KEYS = {"dice", "cards", "hands", "hole", "board", "showdown", "totals", "points", "chips",
              "tokens", "victory_points", "pots", "roles", "stakes", "expressions"}
MAX_FACT_CHARS = 240


def build_messages(
    obs: Observation, notes: list[str], persona: str | None = None
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt(obs, persona)},
        {"role": "user", "content": user_prompt(obs, notes)},
    ]


GOAL = (
    "You MUST win this tournament. Only the last player standing wins; every other "
    "result, including second place, is a loss. The other players are trying to win "
    "too. Think strategically about every message, transfer and move, and use any "
    "strategy the rules allow."
)


def system_prompt(obs: Observation, persona: str | None) -> str:
    parts = [
        f"You are {obs.you}, a player in a strategy tournament against other players.",
        GOAL,
        obs.rules,
    ]
    if persona:
        parts.append(persona)
    parts.append(
        "Reply with ONLY one JSON object, no other text. Keep private_reasoning brief "
        "(under 60 words); no other player ever sees it."
    )
    return "\n\n".join(parts)


def user_prompt(obs: Observation, notes: list[str]) -> str:
    where = f"Day {obs.day}"
    if obs.game:
        where += f", {obs.game}"
    if obs.round is not None:
        where += f", round {obs.round}"

    sections = [
        f"## Now\n{where}. You are {obs.you}.",
        "## Your private information\n" + _json(obs.private),
        "## Public state\n" + _json(obs.public),
        "## What has happened (oldest first)\n" + render_history(obs),
    ]
    if notes:
        sections.append(
            "## Your private notes from earlier turns\n"
            + "\n".join(f"- {n}" for n in notes[-MAX_NOTES:])
        )
    sections.append("## Your turn\n" + task(obs))
    if obs.last_error:
        sections.append(
            "## Your previous reply was rejected\n"
            f"{obs.last_error}\nFix it and reply again with valid JSON."
        )
    return "\n\n".join(sections)


def task(obs: Observation) -> str:
    if obs.kind == "chat":
        fields = ['"private_reasoning": "..."', '"public_message": "..." or null']
        if obs.communication == "private":
            fields.append('"private_messages": [{"to": "Player X", "text": "..."}]')
        fields.append('"transfers": [{"to": "Player X", "pieces": 1}]')
        if obs.life_price is not None:
            fields.append(f'"buy_life": true (costs {obs.life_price} Pieces)')
        progress = ""
        if obs.exchange:
            current, limit = obs.exchange
            progress = f" Exchange {current} of at most {limit}."
        return (
            f"Chat phase: a conversation.{progress} You may talk, reply to what others "
            "said, and give Pieces. Every field is optional; an empty object {} means "
            "you have nothing more to say. The conversation ends when nobody says "
            "anything.\n{" + ", ".join(fields) + "}"
        )
    if obs.kind == "diary":
        return (
            f"Day {obs.day} is over. Write your private diary; no other player ever sees it. "
            "From tomorrow on, today's conversations will no longer be shown to you: for "
            "earlier days you will see only the key public results and your diary entries. "
            "Record what you will need later, for example deals and promises, how other "
            "players behaved, and your plans.\n"
            '{"summary": "<today, up to 150 words>", '
            '"players": {"Player X": "<your notes on this player, up to 50 words>", ...}}'
        )
    if obs.kind == "will":
        return (
            "You have been eliminated. Last Will: you may give your remaining "
            f"{obs.private['pieces']} Pieces to living players.\n"
            '{"private_reasoning": "...", "transfers": [{"to": "Player X", "pieces": 1}]}'
        )
    lines = [
        "Choose your action. It is sealed until the game reveals it.",
        '{"private_reasoning": "...", "action": {...}}',
        f"Expected action: {obs.action_help}",
    ]
    if obs.legal_actions is not None and len(obs.legal_actions) <= MAX_LISTED_ACTIONS:
        lines.append("Legal actions: " + json.dumps(obs.legal_actions))
    return "\n".join(lines)


def render_history(obs: Observation) -> str:
    lines = []
    for event in obs.history:
        kind = event["type"]
        if kind in SKIPPED_TYPES:
            continue
        if event["day"] == obs.day:
            line = render_event(event, obs.you)
        elif obs.memory == "full":
            line = render_event(event, obs.you) if kind in EARLIER_DAY_TYPES else ""
        elif kind == "diary":
            line = render_diary(event) if obs.memory == "diary" else ""
        else:
            line = render_fact(event, obs.you) if kind in KEY_FACT_TYPES else ""
        if line:
            lines.append(line)
    return "\n".join(lines) if lines else "(nothing yet)"


def render_diary(event: dict[str, Any]) -> str:
    data = event["data"]
    if not data.get("summary") and not data.get("players"):
        return ""
    lines = [f"Your diary, end of Day {event['day']}: {data.get('summary') or '(no summary)'}"]
    lines += [f"  - {player}: {note}" for player, note in data.get("players", {}).items()]
    return "\n".join(lines)


def render_fact(event: dict[str, Any], you: str) -> str:
    """One line for a key public result of an earlier day."""
    data, actor = event["data"], event["actor"]
    match event["type"]:
        case "day_start" | "transfer" | "placement":
            return render_event(event, you)
        case "elimination":
            reason = f" ({data['reason']})" if data.get("reason") else ""
            return f"{data['player']} was eliminated{reason}."
        case "tie_break_draw":
            return f"Random draw between {', '.join(data['between'])}: {_json(data['chosen'])}."
        case "prison_start":
            return f"Prison match ({data['game']}): {' vs '.join(data['players'])}."
        case "prison":
            line = f"Sent to prison: {', '.join(data['prisoners'])}."
            if data.get("automatic"):
                line += f" Fewest Pieces: {', '.join(data['automatic'])}."
            if data.get("deciders"):
                line += f" Chosen by {', '.join(data['deciders'])}, votes {_json(data['votes'])}."
            return line
        case "prison_result":
            winner = data["winner"] or "none (tie)"
            return f"Prison match result: winner {winner}, loser {data['loser']}."
        case "doubt":
            bid = data["bid"]
            truth = "true" if data["bid_was_true"] else "false"
            return (
                f"{data['doubter']} doubted {bid['player']}'s bid {bid['quantity']} x {bid['face']}: "
                f"the bid was {truth}; {data['loser']} lost a die."
            )
        case "out_of_dice":
            return f"{data['player']} ran out of dice."
        case "monster_result":
            winner = data["winner_party"]
            if not winner:
                return f"Monster {data['round']}: nobody defeated it."
            members = data["parties"][winner]["members"]
            return (
                f"Monster {data['round']}: the party led by {winner} ({', '.join(members)}) won; "
                f"{winner} split the points {_json(data['allocation'])}."
            )
        case "reveal":
            return f"Secret Number reveal: numbers {_json(data['numbers'])}; guesses {_json(data['guesses'])}."
        case _:
            kept = {k: v for k, v in data.items() if k not in BULKY_KEYS}
            who = f"{actor} " if actor else ""
            line = f"{event['type']}: {who}{_json(kept)}"
            return line if len(line) <= MAX_FACT_CHARS else line[: MAX_FACT_CHARS - 3] + "..."


def render_event(event: dict[str, Any], you: str) -> str:
    data, actor = event["data"], event["actor"]
    prefix = f"[R{event['round']}] " if event["round"] is not None else ""
    match event["type"]:
        case "day_start":
            return f"=== Day {event['day']}: {data['game']} === Pieces: {_json(data['pieces'])}"
        case "public_message":
            return f"{prefix}{actor} (public): {data['text']}"
        case "private_message":
            return f"{prefix}{actor} -> {data['to']} (private): {data['text']}"
        case "transfer":
            will = " as their Last Will" if data.get("last_will") else ""
            return f"{prefix}{actor} gave {data['to']} {data['pieces']} Piece(s){will}."
        case "placement":
            return f"Placement: {_json(data['ranking'])}. Rewards: {_json(data['rewards'])}."
        case "elimination":
            return f"{data['player']} was eliminated."
        case "clue_result":
            answer = "YES" if data["answer"] else "NO"
            return f"{prefix}Your official clue: is your number higher than {data['higher_than']}? {answer}"
        case _:
            who = f"{actor} " if actor else ""
            return f"{prefix}{event['type']}: {who}{_json(data)}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
