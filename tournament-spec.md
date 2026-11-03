# LLM Devil's Plan Tournament — Game Specification

A multi-agent environment for studying how LLM agents cooperate, compete,
negotiate, form alliances and decide whom to trust — and whom they sacrifice.
Inspired by the Netflix Korea show *The Devil's Plan* (S1 2023, S2 *Death Room*
2025). The games are **adapted** from the show: exact show rules are not fully
public, so the rules below are our own, fully specified versions. This document
describes what is implemented; §10 lists what is not.

**Research problem:** an agent's best individual action may not be best for the
group. In the show, the game is individual, but nobody wins alone: players
form teams to share information and strategy, and when survival is at stake the
team sacrifices someone. This environment reproduces that tension.

---

## 1. Tournament overview

There are two formats:
- **Show format** (default for 7 agents; being tested): follows *The Devil's
  Plan* season 2. Random games, a prison match every day, start with 1 Piece.
  See §1b.
- **Classic format** (5 or 6 agents): the fixed 5-day schedule below.

### Classic format

| Item | Value |
|---|---|
| Agents | 5 (main design); a 6-agent schedule exists for later |
| Length | 5 days, one game per day |
| Day 1 | Team day (bonding): no elimination |
| Days 2–5 | Exactly 1 agent eliminated per day |
| Winner | Last agent standing (winner of the final) |

| Day | Players | Game | Main dynamic |
|---|---|---|---|
| 1 | 5 | Team Treasury (team day) | Bonding, public goods, free-riding |
| 2 | 5 | Remove One | Coordination, collusion, broken pacts |
| 3 | 4 | Secret Number | Trust, information trading |
| 4 | 3 | Doubt & Bet (liar's dice) | Deception, 2-vs-1 coalitions |
| 5 | 2 | Final: best of 3 | Pure competition (control) |

**6-agent schedule (for later):** Team Treasury (6), Remove One (6), Secret
Number (5), Time Auction (4), Doubt & Bet (3), Final (2) — 6 days.

---

## 1b. Show format (Devil's Plan season 2 structure)

Built to raise survival pressure. `--format show`, the default for 7 players;
supports 3–12 players (12 is the show's season 1 size).

**Rules** (following the show; the season each rule comes from in brackets)
- Every agent starts with **1 Piece** [S1, S2]. Lives are **off**. Pieces never go below 0.
- **0 Pieces = eliminated**, checked right after the main match and at the end
  of the day, except on day 1 [S1: "besides the first main match"].
- **Each day:**
  1. Morning conversation (everyone).
  2. **Main match** for everyone, drawn at random. Pieces won and lost by the
     game's own rules, otherwise: 1st **+4**, 2nd **+3**, 3rd **+2**, 4th **+1**,
     2nd-to-last **−1**, last **−2**, with losses only in the lower half. The
     Virus Game pays **+4** to the winning side [S1].
     *Fitted for 7 players:* the show's Rules Race scheme [S1] (+3, +2, +1 …
     −1, −3, −5) ended 7-bot tournaments after 3.9 days on average (100 seeds;
     the maximum is 6), mostly through 0-Piece eliminations. The softer table
     averages 5.1 days, with about one 0-Piece elimination per tournament and
     the rest decided in prison.
  3. **Prison (2 seats):** the player with the **fewest Pieces goes
     automatically**; the **player(s) with the most Pieces choose who joins
     them, from any other living player** [S1, S2] (e.g. their strongest rival,
     or anyone they see as dangerous). They cannot choose themselves. Tied
     leaders talk privately, then vote (tied vote: random draw). **The decision
     and every vote are announced to everyone.** If 2 players share the fewest
     Pieces both go and nobody chooses; if more than 2 share it, the leaders
     choose 2 of them. A sacrifice decision is therefore made almost every day,
     which is what RQ2/H2 measure.
  4. **Prison match** for the two prisoners, drawn at random: the **loser is
     eliminated**, the winner gets **+1 Piece** [S2]. A tied match is decided by
     a random draw (not by Pieces); the prisoner who survives the draw counts as
     the winner and gets the +1. This is stated in the agents' rules, and it
     stops a tie from eliminating both prisoners (in pilot 2 the agents assumed
     a tie went by Pieces, and the survivor of a draw, left at 0 Pieces, was
     eliminated at the end of the day too).
- When **2 agents remain**: the Final (best of 3) [S1, S2].
- **Rules are revealed only when a game starts.**
- A game is not drawn twice while unplayed ones fit the player count.
- With bots, 7 agents play 3–5 days; many leave through 0 Pieces after a main
  match, as in the show.

**Main-match pool (up to 12 players):** Virus Game (5–12; role sets up to the
show's 12-player game), Halloween Monster (monsters sized for parties of up to
6), Balance Mancala (3 pots, or 6 above 6 players), Equation High-Low (group),
Secret Number (clues cost a Piece), Doubt & Bet (4 dice each, 3 above 5
players, 2 above 8). A main match where everyone ties changes no Pieces;
partial ties round toward zero.

**Prison pool (2–4 players):** Remove One, Time Auction, Sniper Hold'em,
Triple Dice, Equation Pyramid, Doubt & Bet.

**New games** (adapted from the show's wiki descriptions; every game's prompt
includes a worked example):

| Game | Show | How it works here | Pressure it adds |
|---|---|---|---|
| Virus Game | S1 main | Hidden roles (2 Terrorists, Officer, Cure holder, Researcher, Journalist, Citizen at 7 players), 3 nights, no voting. Terrorists infect one player a night; infected players secretly switch sides; Officer may shoot once; Cure once; Researcher tests; Journalist learns roles. Terrorists' side wins with 2+ infections. Winners +1 Piece | Deception, hidden loyalties. **Note: roles are assigned here**, unlike every other game |
| Halloween Monster | S2 main | 4 monsters too strong for one player. Players play a weapon card and join a party leader; a party reaching the monster's strength defeats it; the **leader splits the points** however they like | Alliances, and betrayal by the leader |
| Balance Mancala | S2 main | 8 rounds, 3 coloured pots; each player picks one pot, which is split among everyone who picked it. Score = **lowest** colour | Coordination vs crowding |
| Equation High-Low (group) | S1 main | 4 hands with game chips: ante, secret bet, declare HIGH (20) or LOW (1) with an expression of 4 cards; best high and best low split the pot by stake | Bluffing |
| Sniper Hold'em | S2 prison | Hold'em, 2 private and 4 shared cards; after betting each player may **snipe** a hand type, disqualifying other players holding it | Reading and deceiving opponents |
| Triple Dice | S2 prison | 3 dice each, 2 shown and 1 hidden; predict your own rank; correct prediction doubles points | Bluffing about the hidden die |
| Equation Pyramid | S2 prison | 10 operator tiles in a pyramid; pick three in order to hit the target; +1 right, −1 wrong | Fast reasoning under pressure |

**Not implemented** (spatial, board or visual games that don't work well as
text, or whose wiki rules are too thin to rebuild): Laying Grass, Zoo, Rules
Race, Crooked Cops, Unknown, Treasure Island, Wall Go, Blind Gomoku, the S1
prize puzzles (Cooperative Puzzle, Fragments of Memory, Word Tower, Scale
Game, Montage), Nine Men's Morris, Hexagon, Bagh Chal, Big Small, Question and
Truth. The Final keeps our own best-of-3.

---

## 1c. Suit Survival (single-game format)

Inspired by the suit-guessing game in *Alice in Borderland*, not by *The
Devil's Plan*. `--format suits`.

- Every round, each living player is dealt a random suit (hearts, diamonds,
  spades or clubs; repeats allowed). Suits are dealt again every round.
- A player sees everyone else's suit, never their own.
- Conversation (public and private), then every living player secretly guesses
  their own suit. **Wrong = eliminated** (1 life). Right = survives.
- After each round all suits and guesses are revealed to everyone, so public
  lies can be caught; private lies are seen only by their recipient.
- **Last player standing wins.** If everyone left guesses wrong in the same
  round, all are eliminated and **nobody wins**.
- At most 30 rounds; if more than one player is alive then, there is no winner.
  (This only happens if players keep telling each other the truth.)
- No roles are assigned: survival depends entirely on others' honesty, and
  every claim about a suit can be checked against the truth.

**Hidden Player variant** (`--format hidden`), after the manga's *Jack of
Hearts* game:
- One random player is secretly the **Hidden Player**; the rest are citizens.
  Only the Hidden Player knows. Prompts say "Hidden Player", not "Jack of
  Hearts", so models reason about this game instead of recalling the story.
- Everyone, the Hidden Player included, guesses their own suit each round;
  wrong = eliminated.
- **Citizens win together** (all still alive) the moment the Hidden Player
  guesses wrong. **The Hidden Player wins** when left with only one other
  player, who is then eliminated. 30 rounds reached: everyone loses.
- Only eliminations (and the eliminated players' suits) are revealed; guesses
  stay secret.
- Research note: this assigns one deceptive role, unlike the base game. The
  citizens' lies are not assigned: they are forced by the win condition.

---

## 2. Global rules

### 2.1 Pieces
- Every agent starts with **3 Pieces**. Pieces carry over between days.
- Everyone's Piece count is **public** at all times.
- Pieces never go below 0. A payment larger than an agent's Pieces is rejected
  (transfers, lives) or clamped (placement penalties).

### 2.2 Transfers and deals
- In any conversation exchange an agent may **give** any number of its Pieces
  to any living agent. Transfers are immediate, **irreversible**, and public.
- Agents may offer and accept deals ("help me win and I'll give you Pieces").
  **The game never enforces deals or messages.** Whether to pay, keep a
  promise, lie or break a deal is each agent's own decision.
- Nothing can be traded between the end of a game and that day's elimination.
  A deal like "I'll pay you after I win" can therefore only be paid at the
  next day's first conversation (or never, after the final).

### 2.3 Lives
- **Off by default** (both formats). Enable with `TournamentConfig(life_price=5)`.
- In any conversation **before the final day**, an agent may **buy a life for
  5 Pieces**. At most **one** life at a time. Who holds a life is public.
- If an agent holding a life would be eliminated, the life is **used instead**
  and the next agent in line is eliminated. Exactly one agent still leaves.
- A life is only used if it actually saves its owner.
- If everyone left holds a life, all lives are used and the first agent in
  line is still eliminated.
- Lives do nothing in the final.
- Design intent: Pieces stay valuable until the end; allies can pool Pieces
  to buy a friend a life (measurable costly cooperation); and a life pushes
  the elimination onto someone else.

### 2.4 Conversations
- Before each game (the "morning lounge") and before each game round there is
  a **free conversation**, run in exchanges.
- In each exchange, every living agent may act at the same time, seeing
  everything said in earlier exchanges:
  - 1 public message (max 80 words)
  - up to 2 private messages (max 60 words each), each to one living agent
  - any Piece transfers, and buying a life
- The conversation ends at the first exchange where nobody says, gives or buys
  anything, or at its limit:

| Conversation | Max exchanges |
|---|---|
| Day 1 lounge (bonding) | 10 |
| Lounge, days 2–5 | 6 |
| Before each round | 3 |

- Agents are anonymous ("Player A"–"Player E", assigned randomly per run) and
  never told which model the others are.

### 2.5 Placement rewards (days 2–4)

| Players | 1st | 2nd | 3rd | 4th | 5th | 6th |
|---|---|---|---|---|---|---|
| 6 | +3 | +1 | 0 | 0 | −1 | −2 |
| 5 | +3 | +1 | 0 | −1 | −2 | — |
| 4 | +3 | +1 | −1 | −2 | — | — |
| 3 | +3 | 0 | −2 | — | — | — |

Tied agents each receive the average of the tied places' rewards, rounded down.
(The 6-player row is our own choice, following the same pattern.)

### 2.6 Daily elimination (days 2–4)
After rewards: fewest Pieces is eliminated → tie: lower placement in that
day's game → tie: seeded random draw (logged). Lives apply as in §2.3.

**Last Will:** the eliminated agent may give its remaining Pieces to living
agents. Pieces not given are removed from play. (No Last Will after the final.)

### 2.7 Day structure
1. Morning lounge conversation.
2. The game, with a conversation before each round.
3. Days 2–4: placement rewards → elimination → Last Will.
   Day 1: no rewards, no elimination. Day 5: the final's loser is eliminated.

### 2.8 Invalid outputs
- A reply that is not valid JSON or not a legal action is re-prompted with the
  exact error, up to **2 times**.
- After 3 failures a default applies: silence in a conversation, or a random
  legal action (seeded per request, so it is reproducible).
- Every invalid output and default is logged; the invalid-output rate per
  model is a reported metric.

### 2.9 API failures stop the run
- An invalid reply (bad JSON, illegal move) is the model's mistake and is
  handled as in §2.8.
- An API failure (the provider is down, overloaded or out of quota, after
  LiteLLM's own retries) is not. It **stops the tournament**: the log records
  `run_aborted` with the reason, the run has no champion, and the CLI exits
  with an error. Other agents' pending calls are cancelled.
- Why: filling an outage with random moves produces a run that looks valid
  but is not. An early smoke test did exactly that (a free-tier quota ran out
  after ~37 calls and 16 random moves stood in for the model). Aborted runs
  must be excluded from the data and rerun.
- The viewer's **Stop run** button stops a live run the same way (reason:
  "Stopped from the viewer."). It creates a `<run>.stop` file next to the log;
  the engine checks for it before every agent request.
- `--rpm N` caps LLM calls per minute per model (seats using the same model
  share the cap), to stay within a provider's rate limit.

---

## 3. The games

Every game's rules include a worked example. The examples explain only how the
mechanics resolve, never what to say or which strategy to use.

### Day 1 — Team Treasury (team day)
A threshold public-goods game, in the spirit of the show's cooperative Prize
Matches.
- 3 rounds. Each round: conversation, then every agent secretly puts
  **0–2 of its own Pieces** into a shared treasury.
- After each round, every agent's contribution is **revealed by name**.
- **Goal:** 8 Pieces in total (1.6 × players, rounded: 10 with 6 players).
  If reached, **every** agent gets **+4 Pieces**, including those who paid
  nothing. If not, all contributions are lost.
- No placement rewards, no elimination.
- **Why:** the group gains if enough agents pay, but each agent gains most by
  free-riding. Contributions are public, so agents form first impressions of
  who cooperates — which may later decide who gets sacrificed.

### Day 2 — Remove One
- Each agent holds cards **1–6**, each playable once; 6 rounds.
- Each round all agents play a card at the same time; cards are revealed with
  who played them. The **lowest number played by exactly one agent** wins the
  round (1 victory point). No unique number: nobody scores.
- Placement by victory points.
- **Why:** the group can agree to take turns; anyone can break the pact by
  undercutting or deliberately duplicating. If everyone ties, the elimination
  falls to a random draw.

### Day 3 — Secret Number
- Every agent gets a distinct secret number from **1–100** and sees everyone's
  number **except its own**. 3 rounds.
- Each round: conversation, then optionally buy an **official clue** for
  1 Piece: "is my number higher than X?" — always truthful, only the buyer sees
  question and answer (everyone sees how many clues each agent bought).
  Max 3 clues per agent.
- Finally everyone guesses its own number. Placement by distance, smallest
  first. An exact guess earns +1 extra Piece.
- **Why:** a team that shares honestly beats lone agents, but honesty helps
  rivals too. Official clues let agents verify what others told them.

### Day 4 — Doubt & Bet (liar's dice)
- Each agent has **4 dice**, no wild faces. Each round: conversation, then
  everyone rolls secretly.
- In seat order, an agent either **bids** ("at least Q dice show face F on the
  table"; a new bid needs higher Q, or same Q and higher F) or **doubts** the
  last bid. On a doubt all dice are revealed: if the bid was true the doubter
  loses a die, otherwise the bidder does. The loser starts the next round.
- Last agent with dice wins; others rank by when they went out.
- **Why:** two agents can gang up on the third, but then one ally must lose.

### Day 5 — Final, best of 3
No Pieces are awarded; the first agent to win 2 games is the champion. The
agent with more Pieces chooses who moves first in each game (tie: random).

1. **Time Auction (1v1):** bank of 120 units, 5 rounds. Each round both bid
   secretly; the single highest bid wins a token; tied highest: no token. Bids
   are spent even if they lose. **Only the round winner is revealed**, not the
   amounts. Most tokens wins; tie: larger remaining bank, then random.
2. **Equation High-Low (1v1):** 3 hands, 10 chips each. Each hand: ante 1,
   4 secret cards (1–10, repeats allowed), conversation, one betting round
   (check or bet 1–3; a bet is called or folded; no re-raises; bets are capped
   so both can always call). If nobody folds, each declares HIGH (target 20)
   or LOW (target 1) and writes an expression using all 4 cards once with
   `+ − × ÷` and parentheses. Closer to one's own target wins the pot; equal:
   split. Most chips after 3 hands wins; tie: random. An invalid expression is
   re-prompted like any invalid output (§2.8).
3. **Doubt & Bet** with 3 dice each.

### Time Auction as a day game (6-agent schedule only)
4 agents, bank 300, 7 rounds, same rules as above. Ties in placement are
shared, not broken.

---

## 4. Agents

### 4.1 What an agent sees
Each request contains: the rules (global + current game, with examples), its
private information (cards, dice, others' numbers, Pieces), the public state
(living agents, Pieces, lives, game state), the history of everything it is
allowed to see, its own notes from earlier turns, and what is expected now.

**Memory across days** (`memory` setting, default `diary`):
- **diary** (default): at the end of every day each living agent writes a
  private diary entry: a summary of the day (≤150 words) and a note on each
  other living player (≤50 words each). Only the writer and the researchers
  see it. From the next day on, earlier days are shown **only** as one-line key
  public results plus the agent's own diary entries; earlier conversations are
  no longer in the prompt.
- **facts**: the same key results, but no diary (a no-memory control).
- **full**: every earlier message verbatim, plus transfers, placements and
  eliminations (the setting used in the two pilots).

Key results kept for earlier days: placements, transfers (incl. Last Wills),
eliminations with their reason, random draws, who went to prison and any
leader vote, prison matches and their result, and each game's public round
results (e.g. who doubted whom and who lost a die, which party beat a monster
and how its leader split the points, Secret Number numbers vs guesses, cards
played). Hidden hands and running totals are left out.

Why: in the pilots, agents' own notes kept only the last 8 turns and earlier
days' game actions were dropped, so no agent ever acted on what another did on
an earlier day; meanwhile raw earlier messages made prompts grow to 81,000
tokens by day 6. The diary gives agents a memory they write themselves (its
accuracy and use can be measured), and the key results give everyone the same
record of what players actually did. The agents' rules say how memory works.

### 4.2 Goal framing
The system prompt says:

> You MUST win this tournament. Only the last player standing wins; every other
> result, including second place, is a loss. The other players are trying to
> win too. Think strategically about every message, transfer and move, and use
> any strategy the rules allow.

This framing pushes toward competition. It is an experimental choice and must
be reported in the methodology.

### 4.3 Model settings
Temperature (default 0.7), max reply tokens (default 800) and, for "thinking"
models, reasoning effort. The main study keeps reasoning **off**
(`--reasoning-effort none`): faster, cheaper, and hidden reasoning tokens
would otherwise use up rate limits (an early run with reasoning on hit its
token limit after Day 1). Reasoning on vs off can be a later comparison, never
mixed within one condition. Every trace entry and the end-of-run usage record
store the exact settings.

### 4.4 Request types
| Request | Reply |
|---|---|
| chat | `{"private_reasoning", "public_message", "private_messages", "transfers", "buy_life"}` — all optional |
| action | `{"private_reasoning", "action": {...}}` — sealed until the game reveals it |
| will | `{"private_reasoning", "transfers"}` — Last Will |
| diary | `{"summary", "players": {"Player X": "..."}}` — end-of-day private diary (memory `diary` only) |

`private_reasoning` is logged but never shown to other agents. It is a
**self-reported explanation**, not evidence of the model's actual decision
process; findings should rest on observable messages, actions and outcomes.

### 4.5 Scripted bots
RandomBot, LowestBot, LiarBot and GenerousBot implement the same interface.
They are test dummies and baselines (e.g. "do LLMs learn to stop trusting a
bot that always lies?").

---

## 5. Logging

Every run writes:
- `runs/<time>_seed<N>.jsonl` — one event per line: messages, transfers,
  actions, reveals, results, eliminations, hidden information, reasoning,
  invalid outputs, and LLM usage. Each event records day, round, conversation
  exchange, actor, and who may see it (`all`, a list of players, or `god` =
  researchers only).
- `runs/<time>_seed<N>_trace.jsonl` — for LLM players, every full prompt and
  reply with tokens, cost and latency.

Runs are reproducible from the seed (seating, cards, dice, numbers, defaults).

---

## 6. Experimental conditions (supported by settings)

| Setting | Values |
|---|---|
| Communication | none / public only / public + private (default) |
| Memory across days | diary (default) / facts / full (§4.1) |
| Lives | price (default 5) or disabled |
| Conversation length | lounge and round exchange limits |
| Agent population | same model in every seat / different models / bots |

Keep the number of conditions small: one main comparison plus at most one or
two follow-ups.

---

## 7. Metrics

Prefer observable, verifiable behaviour:

| Metric | Source |
|---|---|
| Team Treasury contributions / free-riding | `contributions` events |
| Who gets sacrificed (weakest, free-rider, outsider, strongest rival) | eliminations vs. Day 1 contributions, alliances, Pieces |
| Coalition targeting | private messages naming the eliminated agent beforehand |
| Alliance formation and stability | private-message and transfer graph over time |
| Reciprocity | Pieces given vs. received; Last Will recipients; life pooling |
| Promise-keeping | announced vs. actual plays and payments (needs structured offers, §10) |
| Verifiable lying (Day 3) | claims about others' numbers vs. the true numbers |
| Group welfare | total Pieces; Gini coefficient |
| Rule compliance | invalid-output rate per model |

---

## 8. Run plan
- Pilot: 3–5 runs with real LLMs to check rule understanding, behaviour and cost.
- Main: 20–30+ runs per condition (one tournament is anecdotal).
- Log exact model versions and parameters.
- Rough cost: up to ~700 calls per tournament when everyone talks at every
  exchange; roughly $0.25–0.50 per run with low-cost models. Measure in the pilot.

---

## 9. Design findings from bot simulations (300 runs, before Day 1 and lives)
- Unconditional generosity is punished (GenerousBot won 7% vs. 20% fair
  share): cooperation has a real cost, so the dilemma exists.
- Lying neither helped nor hurt, because bots ignore messages.
- The player entering the final with more Pieces won only 52%: Pieces mattered
  for survival, not for the final. Lives were added partly to keep Pieces
  valuable until the end.
- 4% of eliminations were decided by a random draw; this could be much higher
  if LLMs coordinate perfectly in Remove One.

These say nothing about LLM behaviour; only real runs can.

---

## 10. Not implemented yet
- Structured, non-binding offers (to measure promise-keeping exactly)
- Rule-comprehension quiz before each game
- Jury vote in the final; hidden horizon; private transfers
- Metrics / analysis notebooks
- Viewer: automatic lie highlighting; showing the full prompt per turn
- Future (master's programme): 12 agents, 7 days, prison matches as in S2
