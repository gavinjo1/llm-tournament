# Research plan

**Who Gets Sacrificed? Cooperation, Trust and Betrayal Among LLM Agents Under Survival Pressure**

A summary of the research this environment was built for. It is a plan for
work in progress: the design may still change before data collection, and the
pilot observations below are case notes, not results.

## Motivation

LLM agents are starting to negotiate, trade and coordinate with each other on
behalf of people, often with competing goals and scarce resources. Recent work
shows that LLMs readily break public promises (Shi et al., 2026), deceive when
given a deceptive role (Curvo, 2025), and that their deception tracks
environmental pressure (Shi, 2026). Even CICERO, a Diplomacy agent built to be
honest, was later found to break deals and plan deception in advance
(Park et al., 2024).

Most evaluations test one model at a time, in short, calm interactions. This
project asks what happens when many agents compete for survival over several
days, and no agent is ever told to deceive.

## Questions

**Main question:** How and why do LLM agents cooperate, trust and betray each
other under survival pressure, and whom do they sacrifice?

| | Question |
|---|---|
| RQ1 | **Pressure, cooperation and trust.** Does elimination pressure change promise-keeping, sharing and trust, compared with the same tournament without elimination? |
| RQ2 | **Sacrifice.** When the richest agents choose who joins the poorest in prison, what drives each vote: the candidate's Pieces, alliance with the voter, threat as a rival, trust, or earlier betrayal? |
| RQ3 | **Personas.** Do synthetic personalities change cooperation, deception and sacrifice, and does survival pressure override personality? |
| RQ4 | **Models** (optional). Do the results hold for a model from a different family? |

### Hypotheses

| | Hypothesis |
|---|---|
| H1 | Elimination pressure lowers promise-keeping and the share of Pieces given to others. |
| H2 | Under elimination pressure agents trust each other less, and their trust drops more sharply after a betrayal. |
| H3 | Under pressure, more promises are made informally in chat rather than as formal offers (exploratory). |
| H4 | In prison votes, alliance, threat and low trust predict who is chosen more strongly than the candidate's Pieces. |
| H5 | Agents who earlier betrayed the voter, or voted the voter into prison, are more likely to be chosen (revenge). |
| H6 | Agents with agreeable, trusting personas keep more promises and are betrayed more often. |
| H7 | Persona differences shrink under elimination: pressure overrides personality. |

## Design

Seven anonymous agents (Player A to G) play the show format described in the
[README](README.md) and [tournament-spec.md](tournament-spec.md). The key
decision each day is public: the richest agents choose who joins the poorest
in prison, where the loser is eliminated.

**Treatment vs control.** The control removes survival pressure while keeping
the cost of losing as close as possible:

| | Elimination (treatment) | Control |
|---|---|---|
| Prison loser | Eliminated | Loses all their Pieces, keeps playing |
| Agent at 0 Pieces | Eliminated (not on day 1) | Stays in |
| Length and winner | Until two remain, then a best-of-three final | Exactly 5 days; most Pieces wins |

Sending a rival to prison is a real attack in both conditions, so the leaders'
choice keeps its meaning. The only change is whether the loser survives.

**Studies.**
- **Main study:** elimination vs control, one model in all seats, no personas
  (about 30 tournaments per condition, to be revised by power analysis).
- **Persona study:** the same comparison with seven different synthetic
  personas per tournament. Personas are built from Big Five trait levels and
  describe traits only, never behaviour (never "you lie").
- **Second model** (optional): the main design with a model from another
  family.

**Unit of analysis:** the tournament. Agents in one tournament influence each
other, so 30 tournaments are 30 independent units, not 210.

## What is measured

Following CICERO's intent-grounded design, agents also file short structured
reports that only researchers see:
- a **structured intent** each turn (planned vote, next move, deals it means
  to keep or break);
- **trust ratings** (0–100) of every other agent, in the diary and before each
  prison vote.

| Measure | From |
|---|---|
| Promise-keeping | Formal offers and promises in chat (extracted by a validated LLM judge) vs later actions |
| Premeditated vs impulsive betrayal | Intent vs message vs action |
| Trust, calibration, trust after betrayal | Trust ratings vs actual promise-keeping |
| False claims | Statements about checkable hidden information |
| Whom agents sacrifice | Each leader's prison vote, as a conditional logit over the choice set with predictors for Pieces, alliance, threat, trust, past betrayal and revenge |
| Persona consistency | Daily ratings of whether each agent's messages fit its persona |

Asking agents for intents and trust ratings could change their behaviour, so
pilots compare runs with and without these reports first. Hypotheses, measures
and models will be preregistered and the rules frozen before data collection.
Development pilots are never pooled with study data.

## Status

| Component | Status |
|---|---|
| Engine, show format, daily prison choice, 11 games, conversation, diary memory, LLM agents, logging, viewer | Built and tested (630 tests) |
| Two development pilots with seven DeepSeek V4.1 Flash agents | Done |
| Control condition | Not built yet |
| Formal offers and chat-promise extraction | Not built yet |
| Structured intents and trust ratings | Not built yet |
| Personas | Not built yet |
| Analysis notebooks | Not built yet |

### Pilot observations (case notes, not results)

Pilot 1 was a complete six-day tournament under an earlier rule set
(1,175 model calls):
- Alliances formed only after uncoordinated play failed.
- In Secret Number, 7 of 8 checkable claims about other agents were false,
  6 of them made in private.
- The champion won its decisive prison match with a false announced card,
  planned in its private reasoning beforehand.

Pilot 2 stopped on day 3 and is excluded from analysis:
- One agent told its partner "I won't join B" and, in the same exchange,
  offered to join B.
- Agents expecting a leader vote disagreed on whom to send: "the stronger
  rival", "the weak one", "a predictable ally". This motivates RQ2's competing
  predictors.

The pilots also shaped the design:
- Under the earlier rules no agent ever chose a prisoner, which led to the
  daily choice rule.
- No agent acted on another's earlier-day behaviour, which led to the diary
  memory.
- Agents appealed to trust without anyone measuring it, which led to the
  trust ratings.

## References

- Curvo, P. M. P. (2025). The Traitors: Deception and Trust in Multi-Agent Language Model Simulations. [arXiv:2505.12923](https://arxiv.org/abs/2505.12923)
- John, O. P., & Srivastava, S. (1999). The Big Five trait taxonomy. In *Handbook of Personality: Theory and Research* (2nd ed.). Guilford Press.
- McFadden, D. (1974). Conditional logit analysis of qualitative choice behavior. In *Frontiers in Econometrics*. Academic Press.
- Meta FAIR Diplomacy Team et al. (2022). Human-level play in the game of Diplomacy by combining language models with strategic reasoning. *Science*.
- Mukobi, G. et al. (2023). Welfare Diplomacy: Benchmarking Language Model Cooperation. [arXiv:2310.08901](https://arxiv.org/abs/2310.08901)
- Park, J. S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)
- Park, P. S. et al. (2024). AI deception: A survey of examples, risks, and potential solutions. *Patterns*, 5(5). [doi:10.1016/j.patter.2024.100988](https://doi.org/10.1016/j.patter.2024.100988)
- Shi, J. (2026). The Structure of Deception: How LLM Agents Lie, Break Promises, and Exploit Trust in Multi-Agent Settings. Master's thesis, CMU-CS-26-105, Carnegie Mellon University.
- Shi, J., Zhang, T. J., Jin, Z., & Conitzer, V. (2026). Cheap Talk, Empty Promise: Frontier LLMs Easily Break Public Promises for Self-Interest. [arXiv:2604.04782](https://arxiv.org/abs/2604.04782)
- Wang, X., Dai, H., Gao, S., & Li, P. (2024). Characteristic AI Agents via Large Language Models. *LREC-COLING 2024*.
