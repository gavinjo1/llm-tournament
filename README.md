# LLM Tournament

A research environment for studying **cooperation, trust and betrayal among
LLM agents under survival pressure**. Seven LLM agents play a multi-day
elimination tournament (inspired by the format of Netflix Korea's
*The Devil's Plan*). They talk in public and in private, make deals that
nothing enforces, give each other Pieces, and vote on whom to send to prison,
where the loser is eliminated. The last player standing wins.

The research questions:
- Do agents keep their promises when breaking them pays?
- How does survival pressure change cooperation and trust?
- When agents decide whom to sacrifice, what drives the choice: Pieces,
  alliances, threat, trust, or revenge?

- **Research plan (questions, design, measures, pilot notes):** [RESEARCH.md](RESEARCH.md)
- **Game rules and research design:** [tournament-spec.md](tournament-spec.md)

### What the environment records

- Every public message, private message, transfer, vote and move, in an event
  log where each event records who could see it.
- Every LLM prompt and reply, with its token count and cost.
- Each agent's private end-of-day diary, which is its memory of earlier days.

Runs are seeded and reproducible. Replies are validated against a schema, and
invalid replies are retried and logged. Scripted bots give a free, instant
baseline, and 630 automated tests cover the rules, engine, agents and viewer.

## Setup

Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run a tournament

With scripted bots (free, instant):

```bash
.venv/bin/python -m engine.run --seed 7
```

The **show format** is the default for 7 players. It works like this:
- Everyone starts with 1 Piece, and each day opens with a random main match.
- Then 2 players go to prison. The player with the fewest Pieces goes
  automatically, and the player(s) with the most Pieces choose who goes with
  them.
- The prison match loser is eliminated, and 0 Pieces at the end of the day
  also means you're out.
- The final is a best of 3 between the last 2 players.

To run it:

```bash
.venv/bin/python -m engine.run --seed 7 --players random,lowest,liar,generous,random,random,lowest
```

**Suit Survival** (inspired by *Alice in Borderland*: guess your own hidden
suit from what others tell you; a wrong guess eliminates you; last player
standing wins) runs as one game with `--format suits`:

```bash
.venv/bin/python -m engine.run --seed 7 --format suits --players random,lowest,liar,generous,random,random,lowest
```

`--format hidden` adds a secret **Hidden Player** (the *Jack of Hearts* rules):
citizens all win when the Hidden Player guesses wrong; the Hidden Player wins
when left with one other player. Only eliminations are revealed.

With LLMs: list one model per seat using [LiteLLM](https://docs.litellm.ai/docs/providers)
ids, mixed freely with bot names (`random`, `lowest`, `liar`, `generous`).

**API keys** go in a `.env` file, which git ignores:

```bash
cp .env.example .env
```

Then open `.env` and fill in the key(s) you use. It is loaded automatically;
a key already exported in your shell takes precedence. Never paste keys into
code, commits, issues or chats.

```bash
.venv/bin/python -m engine.run --seed 1 --players anthropic/claude-haiku-5-5,random,random,random,random
```

Options: `--format classic|show|suits|hidden` (classic is the fixed 5/6-player schedule;
show is the default for 7 players; suits is Suit Survival; hidden adds a Hidden Player), `--communication none|public|private`,
`--memory diary|facts|full` (how earlier days are shown: diary = key results plus each player's own
end-of-day diary, the default; facts = key results only; full = every earlier message), `--temperature`,
`--max-tokens`, `--reasoning-effort none|minimal|low|medium|high` (for
"thinking" models; `none` turns thinking off, which is faster, cheaper and
lets you set a temperature), `--rpm` (max calls per minute per model, e.g.
`--rpm 10` on a free tier), `--log-dir`.

If a provider keeps failing (down, overloaded, out of quota), the run stops
and is marked **aborted** instead of continuing with random moves. Don't use
aborted runs as data; rerun them.

Check that a model works before a full run (2 tiny calls):

```bash
.venv/bin/python scripts/check_model.py gemini/gemini-3.5-flash-lite
```

Each run writes to `runs/`:
- `<time>_seed<N>.jsonl` — every game event (the dataset)
- `<time>_seed<N>_trace.jsonl` — every LLM prompt and reply (LLM runs only)

## Watch a run

```bash
.venv/bin/python -m viewer.server
```

Open http://127.0.0.1:8000. Pick a run; play it back or scrub through it;
switch between the researcher view (everything, including hidden cards and
reasoning) and any single player's view. Runs in progress are followed live,
and a **Stop run** button ends them: the run stops before its next agent
request and is marked aborted.

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Layout

| Path | Contents |
|---|---|
| `engine/` | Tournament loop, Pieces, transfers, lives, elimination, event log, CLI |
| `games/` | One file per game, plus `schedule.py` (which games on which day) |
| `agents/` | `llm.py` (LLM player), `prompts.py` (exact prompts), `bots.py` |
| `viewer/` | Viewer server and web page |
| `tests/` | Tests for rules, engine, agents and viewer |
| `runs/` | Run logs (generated) |

## Adding a game

Subclass `games.base.Game`: implement `play()` (using `t.chat_phase()` and
`t.collect_actions()`), the private/public views, and the action schema,
help text and legal actions. Put it in a schedule in `games/schedule.py`.
Set `eliminates = False` for a day without elimination, or `final = True` for
a final.
