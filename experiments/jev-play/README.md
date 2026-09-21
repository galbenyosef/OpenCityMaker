# Can a model play CityMaker?

An experiment: drive CityMaker's 2048 engine with two very different kinds of
model, and see which can actually play.

- **TypeSafe `jev`** — a fast choice model that *picks* from a fixed set of
  options rather than generating text (~350 ms per move).
- **GPT-5.6 Luna / Terra** via OpenRouter — reasoning LLMs answering the same
  question through a strict `json_schema` enum (~5–12 s per move).

2048 is an unusually clean test. The action space is exactly four, every move is
an independent decision, and there is a well-known score ladder to measure
against. Unlike a web form there is no *correct* option, only a *better* one.

## How it is wired

```
game-server.ts  ──▶  board as 2D array  ──▶  TypeSafe   ──▶  "left"  ──▶  POST /move
 (real engine)       + rules + objective     OpenRouter      a choice    (real engine)
```

The prompt *content* is a shared object; only the transport differs. Use
`payload.py` to confirm both providers receive byte-identical rules text —
without that, the comparison measures wording rather than models.

- **`server/game-server.ts`** wraps `src/game/engine.ts` — the game's own pure,
  dependency-free engine — behind HTTP. Same rules, same scoring, same spawn
  behaviour as the shipped app, with no browser, no CDP and no DOM scraping.
- **`jev_play/typesafe.py`** is a ~50-line direct client for
  `api.typesafe.ai/v1/systemone`.
- **`jev_play/openrouter.py`** is its counterpart for chat-completions, with a
  strict enum schema so an invalid direction is structurally impossible.
- **`jev_play/policy.py`** sends one question with four options keyed by
  direction name, plus the board as a 2D array and the rules of 2048.

### Why not go through `jev-ultrafast`?

The first version of this experiment did, and it badly distorted the result.
`jev_ultrafast.model.choose` is built for web pages, so it wraps every question
in browser-agent scaffolding:

- an `elements` list of clickable buttons, with the choice made by *index*
- an `operation` head offering `CLICK` / `DONE` / `BLOCKED`
- `NEXT_ACTION` attached to **every** question — *"Fill required fields before
  submitting"*, *"For date pickers, CLICK the field, date, then confirmation"*

The board only ever appeared as prose in a field beside all that. Scores went
from 36 to 1460 on the same seed once it was removed. See `RESULTS.md`.

The old protocol's artifacts are kept under `artifacts/jev/{bare,coached,...}/`
for comparison; the current one writes to `artifacts/jev/direct-*/`.

## Arms

A ladder, each arm adding one block to the one before it:

| Arm | What it adds | Median score (5 seeds) |
| --- | --- | ---: |
| `bare` | Minimal rules + objective. | 1188 |
| `rules` | + spawn probabilities (90% a 2, 10% a 4), worked merge examples, the explicit cost of a dead direction. | **1312** |
| `tips` | + evaluative criteria, phrased as things to weigh rather than an order to follow. | 764 |
| `coached` | + a fixed direction ranking ("strongly prefer left and up"). | 80 |

Plus one arm that is not a rung on that ladder:

| Arm | What it changes |
| --- | --- |
| `preview` | Each option label carries the move's **computed** outcome (merges, points, empty cells, or "nothing moves"), from `POST /preview`. The model no longer simulates, it only chooses — which separates "cannot simulate" from "cannot choose". |

Plus one control:

| Flag | What it changes |
| --- | --- |
| `--shuffle` | Randomises the order the four options are listed in, **per move**. Separates a genuine direction preference from bias toward whichever option is listed first. |

The short version: **spelling out the mechanics helps, telling it how to play
hurts.** `coached` wastes 95.5% of its moves. See `RESULTS.md`.

Legal moves are deliberately **never** disclosed — inferring them from the board
is part of playing 2048, and the wasted-move rate measures whether it can.

Baselines (`server/baselines.ts`) play the same engine with the same seeded LCG:

- `random` — uniform over all four directions, no-ops included.
- `random-legal` — uniform over legal moves only: isolates "can't read the
  board" from "can't pick well".
- `priority-left-up` — the classic dumb 2048 ladder. **If a policy can't beat
  this, it isn't playing well.**
- `expectimax-d2` — depth-2 expectimax, the upper reference.

## Running it

```bash
# 1. baselines (free, ~60s)
cd ../..
npx vite-node experiments/jev-play/server/baselines.ts -- --seeds 200
npx vite-node experiments/jev-play/server/per-seed-baselines.ts -- --seeds 1000,1001,1002,1003,1004

# 2. game server
npx vite-node experiments/jev-play/server/game-server.ts &

# 3. the model plays (one API call per move)
cd experiments/jev-play
uv sync && cp .env.example .env     # add TYPESAFE_API_KEY and OPENROUTER_API_KEY

# an LLM arm
uv run --env-file .env python -m jev_play.play --provider openrouter \
    --model openai/gpt-5.6-luna --effort low --seed 1000 --moves 1500 --arm coached
for arm in bare rules tips coached; do
  for seed in 1000 1001 1002 1003 1004; do
    uv run --env-file .env python -m jev_play.play --seed $seed --moves 400 --arm $arm
  done
done

# 4. probe *why* a model fails, rather than just how much
#    legality: can it tell which directions do anything? (no game loop)
uv run --env-file .env python -m jev_play.legality --provider typesafe --boards 120
#    move quality: score every logged board with depth-2 expectimax, then compare
npx vite-node ../../experiments/jev-play/server/rank-boards.ts -- \
    --log ../../artifacts/jev/direct-rules/seed-1000/moves.jsonl

# 5. read the results
uv run python -m jev_play.ladder                       # arms side by side vs baselines
uv run python -m jev_play.paired --arm direct-rules    # seed-for-seed detail
uv run python -m jev_play.analyse                      # per-run entropies
```

Artifacts land in `artifacts/jev/direct-<arm>/seed-<n>/{moves.jsonl,run.json}`.

## Inspecting the prompt

Print the exact request body without sending it — no API call, no cost:

```bash
uv run python -m jev_play.payload --arm rules
uv run python -m jev_play.payload --arm rules --provider openrouter
```

```json
{
  "state": {
    "board": [[2,0,0,0],[0,0,0,0],[4,0,0,0],[2,2,2,0]],
    "score": 4, "move_number": 5, "highest_tile": 4, "empty_cells": 11,
    "recent_moves": [{"direction":"left","changed":true,"gained":0}, ...]
  },
  "questions": {
    "direction": {
      "type": "choice",
      "criteria": {
        "up": "Slide every tile to the top of its column.", ...
      },
      "instructions": {"rules": "2048, played on a 4x4 grid...", "objective": "..."}
    }
  }
}
```

## Metrics

Per move the log keeps the full 4-way probability distribution, the confidence,
the option ordering, latency and token usage. `run.json` reduces that to:

- **wasted-move rate** — fraction of picks that changed nothing. Uniform random
  sits at 15.3%; anything far above that means the board isn't being read.
  (There is no separate "legal-pick rate": the server defines a legal direction
  as one that changes the board, so it is the exact complement of this number.
  Reporting both would present one metric as two findings.)
- **direction entropy (bits)** — 2.0 is uniform, 0.0 is one direction forever.
  Catches a policy that locks onto a single direction and hammers it.
- confidence split across applied vs. wasted moves — does it know when it
  doesn't know?

## Headline

jev's deficit is **simulation, not choice**. On a legality probe it is
indistinguishable from always answering "yes" (85.0% vs an 85.2% null), and on
boards where all four moves are legal it picks the best one at exactly chance.
Hand it each move's computed outcome and it goes 1312 → 5116. The same help
measurably *hurts* a reasoning LLM, which could already simulate.

## Results

See `RESULTS.md`.
