# Results

Two providers against CityMaker's real engine (`src/game/engine.ts`):
`jev-1.13.0` via TypeSafe `jev-latest`, and `openai/gpt-5.6-luna` /
`openai/gpt-5.6-terra` via OpenRouter. Baselines use the same seeded LCG, so a
seed names one exact game.

Jump to: [jev's prompt ladder](#does-more-rules--more-tips-help-the-prompt-ladder)
· [GPT-5.6 Luna and Terra](#traditional-llms-gpt-56-luna-and-terra)

## Headline

**Most of the original failure was the harness, not the model.**

The first version of this experiment routed every decision through
`jev_ultrafast.model.choose`, which wraps the question in browser-agent
scaffolding: an `elements` list of clickable buttons, an `operation` head
offering CLICK/DONE/BLOCKED, and `NEXT_ACTION` — a block of form-filling rules
about autocomplete suggestions and date pickers — attached to *every* question.
The board arrived as prose in a field beside all of that.

Replacing it with a direct call carrying the board as a **2D array**, the rules
of 2048, and the objective changed the outcome by ~33×:

| protocol | score | max tile | wasted moves | direction entropy |
| --- | ---: | ---: | ---: | ---: |
| via jev-agent (`bare`) | 36 | 8 | 95.3% | 0.11 bits |
| **direct (`bare`)** | **1460** | **128** | **18.9%** | **1.77 bits** |

Same model, same game, same seed. The difference is entirely in how the question
was asked. Input tokens per decision fell from ~2200 to ~710 at the same time.

## Does it actually play well? Paired against baselines

One run against a median over 200 different games is not a comparison, so these
are seed-for-seed on the same games (400-move budget):

| seed | direct | `random` | `random-legal` | `priority-left-up` | wasted |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1000 | 1184 | 404 | 2728 | 3316 | 19.5% |
| 1001 | 1588 | 1252 | 716 | 2360 | 18.6% |
| 1002 | 2324 | 1076 | 404 | 3732 | 19.7% |
| 1003 | 868 | 416 | 1160 | 2276 | 15.3% |
| 1004 | 1188 | 1388 | 1008 | 1716 | 21.6% |
| **median** | **1188** | 1076 | 1008 | **2360** | |

- beats `random` on **4/5** seeds
- beats `random-legal` on **3/5** seeds
- beats `priority-left-up` on **0/5** seeds
- `expectimax-d2` medians **13232** (max tile 1024) over 200 seeds

So: it is now genuinely playing, and edges out uniform random — but the margin
over random is small and it never once beats the dumbest real strategy
("always go left, else up, else right, else down"). It is roughly *random-level*,
not skilled.

**On the wasted-move rate.** Uniform `random` wastes 11.8% of its moves on these
five seeds (15.3% across 200). jev wastes 15–30%. It is *not* better than chance
at noticing which directions do anything — reading the board well enough to
avoid the old lock-in, but not well enough to simulate a move before choosing it.

> **Correction.** Earlier versions of this file reported "wasted-move rate" and
> "legal-pick rate" as two separate columns. They are the same number. The game
> server defines a legal direction as one that changes the board
> (`server/game-server.ts`: `DIRECTIONS.filter(d => move(...).changed)`), so
> `legal_pick_rate == 1 - wasted_move_rate` identically, verified across every
> run ever produced. Only the wasted rate is reported now.

## Does more rules / more tips help? The prompt ladder

Four arms over the same five seeds (1000–1004, 400-move budget). Each adds one
block to the one before it:

| arm | what it adds | score | max tile | moves | wasted | entropy |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `bare` | minimal rules | 1188 | 128 | 120 | 19.5% | 1.84 |
| **`rules`** | **+ spawn probabilities (90% a 2, 10% a 4), worked merge examples, explicit cost of a dead direction** | **1312** | 128 | **134** | 29.7% | 1.74 |
| `tips` | + evaluative criteria ("weigh these", not an order) | 764 | 64 | 100 | **14.2%** | 1.84 |
| `coached` | + a fixed direction ranking | 80 | 16 | 18 | 95.5% | 1.00 |
| | | | | | | |
| `random` | | 1076 | 128 | 134 | 11.8% | |
| `random-legal` | | 1008 | 64 | 121 | 0% | |
| `priority-left-up` | | 2360 | 256 | 200 | 0% | |

Head-to-head on the same seeds:

| arm | beats `random` | beats `random-legal` | beats `priority-left-up` |
| --- | ---: | ---: | ---: |
| `bare` | 4/5 | 3/5 | 0/5 |
| **`rules`** | **5/5** | 3/5 | **1/5** |
| `tips` | 2/5 | 2/5 | 0/5 |
| `coached` | 2/5 | 1/5 | 0/5 |

### What the ladder says

**Spelling out the mechanics helped; telling it how to play hurt.**

- `rules` is the best arm. Adding the spawn probabilities, five worked merge
  examples, and a plain statement that a dead direction forfeits the turn moved
  the median score 1188 → 1312, made it the first arm to beat `random` on
  *every* seed, and the first to beat `priority-left-up` on any seed at all.
- `tips` did exactly what it was written to do and still lost. It has the lowest
  wasted rate of any arm (19.5% → 14.2%) — the "rule out dead directions
  first" instruction landed — but the score fell by a third and games got
  shorter (120 → 100 moves). Avoiding wasted turns is not the same as scoring:
  a cautious shuffle that merges nothing is legal, and it fills the board.
- `coached` is catastrophic and reproducible: 95.5% wasted across five seeds,
  a median of 18 successful moves before the game ended. A fixed direction
  ranking is the single worst thing found in this experiment, and enriched rules
  did not rescue it.

The pattern across every arm: **this model will follow prescriptive guidance far
more faithfully than it will read the board.** Factual mechanics give it
something to reason from. Preference orderings give it something to obey, and it
obeys them past the point of absurdity.

### One caveat on the wasted-move numbers

Uniform `random` wastes 11.8% of its moves on these five seeds. No jev arm beat
that, including `tips` at 14.2%. So none of them is better than chance at
spotting which directions are alive — `tips` merely narrowed the gap.

## Traditional LLMs: GPT-5.6 Luna and Terra

Same game server, same shared prompt blocks, different transport: OpenRouter
chat-completions with a strict `json_schema` enum over the four directions.
`payload.py` was used to confirm the `rules` and `objective` text reaching both
providers is byte-identical, so this compares models rather than wording.

**Seed 1000 only, one game per cell.**

| policy | score | tile | moves | wasted | p50 | p95 | think tok | end | $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| luna-high `rules` | 6228\* | 512 | 399 | 0.2% | 12.0s | 40.9s | 737k | **budget** | 0.97 |
| **luna-low `coached`** | **5520** | 512 | 373 | 3.1% | 4.8s | 8.1s | 158k | lost | 0.28 |
| luna-high `coached` | 3700 | 256 | 292 | 0.3% | 7.4s | 23.6s | 300k | lost | 0.43 |
| `priority-left-up` | 3316 | 256 | 274 | 0% | — | — | — | lost | — |
| terra-med `coached` | 3176 | 256 | 257 | 1.5% | 4.7s | 10.2s | 78k | lost | 1.54 |
| luna-low `rules` | 2800 | 256 | 222 | 0.4% | 5.5s | 9.2s | 118k | lost | 0.19 |
| `random-legal` | 2728 | 256 | 217 | 0% | — | — | — | lost | — |
| terra-med `rules` | 1456 | 128 | 149 | 0% | 8.3s | 22.4s | 102k | lost | 1.56 |
| jev `direct-rules` | 1312 | 128 | 134 | 26.8% | 0.35s | — | — | budget | — |
| `random` | 404 | 32 | 82 | 18.3% | — | — | — | lost | — |

\* **Censored, not a win.** luna-high `rules` hit the 400-move cap while still
alive. Its true score is higher than 6228 and it is not comparable to the rows
that played to a loss. The move cap should be raised to ~1500 before this cell
is ranked against the others.

### What holds up

**They read the board.** Wasted moves fall to **0–3.1%**, against jev's 17–55%.
Six configs, two models, two arms, no exceptions. This is the one jev could never
do: pick a direction that actually changes something.

**Coaching reverses sign.** The strategy paragraph that drove jev to 95.5% wasted
moves and a median score of 80 *helps* the LLMs — luna-low 2800 → 5520,
terra 1456 → 3176. The exception is luna-high, where it hurt. So the collapse is
**jev-specific, not a property of language models at this task**. Advice is only
useful to a model that can check it against the board; a model that cannot
simply obeys it into a wall.

**luna beats terra decisively**, on both arms, at roughly 1/6th the cost. The
more expensive model lost every head-to-head here.

### What does not hold up yet

**Every cell is n = 1.** Per-seed baseline scores on this seed set span
404–3732, so single-game noise is comparable to the differences being claimed.
The ordering *within* the LLM rows should not be trusted; the gap between the
LLM block and the jev block is large enough to survive it.

**Reasoning effort has no clean story.** high+`rules` is the top scorer and
high+`coached` is mid-table. That is an effort × arm interaction, or it is
noise, and one game per cell cannot tell the two apart.

### The trade

jev answers in **350 ms** for a fraction of a cent. Luna answers in **5–12 s**
(p95 up to 41 s) and burns 78k–737k reasoning tokens per game. That is roughly
15–35× the latency to go from "worse than random" to "beats the dumb baseline".
Whether that is worth it depends entirely on whether the task needs the board
read at all.

## Why does jev fail? Two probes that locate the deficit

The score tables say jev plays badly. They do not say *which* faculty is missing:
reading the grid, simulating a move, or choosing between known outcomes. Two
probes separate them, and they agree from opposite directions.

### First, isolate choice from legality

Restricting to boards where **all four moves are legal** removes legality as a
confound and asks only: given four working moves, does it pick a good one?
Reference is depth-2 expectimax.

| policy | all-legal boards | picks the best move | mean rank |
| --- | ---: | ---: | ---: |
| jev `bare` | 70 | 24.3% | 2.53 |
| jev `rules` | 69 | 24.6% | 2.49 |
| luna-low `rules` | 142 | 50.0% | 1.79 |
| luna-high `rules` | 228 | 53.1% | 1.71 |
| *chance* | | *25.0%* | *2.50* |

**jev is exactly at chance.** Its probability distribution is equally empty: it
assigns 0.247 average probability to legal directions and 0.261 to illegal ones
— slightly backwards. Confidence does not predict the outcome either.

### Probe 1: can it tell which moves are legal?

No game loop, no strategy. 120 real boards, stratified so half contain at least
one dead direction. Four binary judgements per board, graded against the engine.

| model | per-direction | all four | all four, board has a dead direction | "dead" precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| **jev** | **85.0%** | **49.2%** | 13.3% | 48.1% | 18.3% |
| luna-low | 90.6% | 65.0% | 30.0% | 96.4% | 38.0% |
| **always answer "yes" (null)** | **85.2%** | **50.0%** | 0.0% | — | 0% |

**jev is indistinguishable from a constant "yes"** — marginally *below* a null
that ignores the board entirely. The one real signal: when jev does flag a
direction dead it is right 48.1% of the time against a 14.8% base rate, 3.2×
chance. But it flags only 27 of 71 dead directions. Real signal, almost never
deployed. Luna's flags are 96.4% precise.

### Probe 2: hand it the computed consequences

The `preview` arm puts each move's outcome *inside* its option label —
`"left: the board changes; 2 merge(s) for +8 points; 5 empty cells afterwards"`
— computed by the engine via `POST /preview`. The model no longer simulates; it
only chooses.

| policy | score | tile | wasted | picks the best move | mean rank |
| --- | ---: | ---: | ---: | ---: | ---: |
| jev `rules` | 1312 | 128 | 26.8% | 24.6% ±10.2 | 2.49 |
| **jev `preview`** | **5116** | **512** | **0.0%** | 29.5% ±6.2 | 2.26 |
| luna-low `rules` | 2800 | 256 | 0.4% | **50.0% ±8.2** | 1.79 |
| **luna-low `preview`** | **2304** | 256 | 0.0% | **32.1% ±8.8** | 2.05 |

**The same intervention has opposite signs.** jev 1312 → 5116; luna 2800 → 2304.

Scores are one game each, so the move-quality columns carry the weight — they
rest on 69–250 independent decisions. A two-proportion z-test on the change in
best-move rate:

- luna `rules` → `preview`: **z = 2.84**, significant at 5%
- jev `rules` → `preview`: z = 0.78, not significant

### What the two probes say together

**jev's deficit is simulation, not choice.** It cannot work out which moves are
live (Probe 1), and that single failure explains the 26.8% wasted moves, the
chance-level play and the low score. Its 3.9× gain in Probe 2 came almost
entirely from wasted moves going to zero — the preview simply *tells* it what it
could not derive. Its strategic choice barely moved and remains near chance.

**For luna the preview is a distraction, not a prosthetic.** It could already
simulate (0.4% wasted unaided). Handing it one-ply greedy features appears to
anchor it on them and crowd out the deeper reasoning that reached 50%.

This is a favourable read for what jev is actually built for. Picking among web
controls whose consequences are already described in their labels is exactly the
regime where the prosthetic is free — nothing ever has to derive what a button
does. 2048 is hostile precisely because it withholds that.

## The order-bias control

"Prefers up" and "prefers whichever option is listed first" are indistinguishable
under a fixed option order. `--shuffle` randomises the listing order per move.

| arm | top direction | direction entropy | position entropy |
| --- | --- | ---: | ---: |
| jev-agent `bare-shuffled` | up 281/300 | 0.41 bits | 1.99 bits |
| jev-agent `coached-shuffled` | left 300/300 | 0.00 bits | 1.98 bits |
| direct `bare-shuffled` | left 44/94 | 1.82 bits | 1.97 bits |

Position entropy near 2.0 bits means the pick was uniform across list slots, so
**none of the arms show positional bias** — the model tracks the label wherever
it is placed. Under the old protocol that label preference was pathological
(up 281/300); under the direct protocol it is a mild left-lean on top of a
genuinely varied policy.

## Speed and cost

p50 decision latency 349–362 ms, essentially unchanged across protocols — one
call per move. The direct protocol is ~3× cheaper per decision (~710 vs ~2200
input tokens) because it carries no element list and no `NEXT_ACTION` block.

## What this does and does not show

- It measures the **choice model as a 2048 policy**, with our code owning
  perception and execution. It does not measure a browser agent navigating a
  page.
- The dominant variable turned out to be **prompt framing**, not model
  capability. Any conclusion of the form "this model can't play 2048" from the
  first protocol would have been wrong.
- 5 paired seeds per arm in the ladder; 1 seed for the shuffled controls.
  Five seeds is enough to see the coaching collapse (95.5% wasted, all five) but
  thin for the `bare` vs `rules` gap, which is the claim most in need of more.
- Only `jev-latest` / `jev-1.13.0` tested.
- The one-ply preview idea flagged here earlier has now been run; see
  "Two probes that locate the deficit" above. It helped jev enormously and
  measurably hurt luna.
- Still untested: **jev on its own ground.** Every result here is jev on a task
  that withholds exactly the thing it cannot compute. The reciprocal test —
  jev against a reasoning LLM on a web-navigation task, measuring latency and
  cost as well as success — is the one that would say whether jev is *good*,
  rather than whether 2048 is hard for it.
