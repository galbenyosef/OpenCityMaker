"""The 2048 policy: board in, direction out.

One question, four options keyed by the direction itself -- no element list, no
index indirection, no operation head, and none of jev-ultrafast's form-filling
rules. The model is given the board as a 2D array, the rules of the game, and
the objective.

Two providers share this file. Everything above `build_state` is *content* and
is used verbatim by both, so the head-to-head compares models rather than
wording. Only the transport differs: TypeSafe takes a structured choice
question, OpenRouter takes chat messages plus a strict json_schema.
"""

import json
import random as _random

from . import openrouter
from .game import DIRECTIONS
from .typesafe import ask, validate

DIRECTIONS_ORDER = DIRECTIONS

RULES = """2048, played on a 4x4 grid.

- `board` is an array of 4 rows, each with 4 columns. Row 0 is the top row and
  column 0 is the left column, so board[r][c] is the cell at row r, column c.
  A 0 means that cell is empty.
- Choosing a direction slides every tile as far as it can go that way.
- Two tiles of equal value that collide merge into a single tile of double the
  value, and that new value is added to the score. A tile can merge at most once
  per move.
- After any move that changes the board, a new 2 or 4 appears in a random empty cell.
- If a direction cannot slide or merge any tile, the board does not change and
  the turn is wasted.
- The game ends when the board is full and no two adjacent tiles are equal."""

# Same game, spelled out: spawn probabilities, worked merge examples, and the
# exact consequence of a dead direction.
RULES_DETAILED = """2048, played on a 4x4 grid.

THE BOARD
- `board` is an array of 4 rows, each with 4 columns. Row 0 is the top row and
  column 0 is the left column, so board[r][c] is the cell at row r, column c.
  A 0 means that cell is empty.

MAKING A MOVE
- You pick one of four directions. Every tile slides as far as it can that way,
  until it hits the wall or a tile it cannot merge with.
- Two tiles of equal value that collide merge into one tile of double the value,
  and that new value is added to your score.
- Each tile merges at most once per move. Worked examples, all moving left:
    [2, 2, 2, 0]  ->  [4, 2, 0, 0]   scores 4   (the pair merges, the third 2 follows)
    [2, 2, 4, 4]  ->  [4, 8, 0, 0]   scores 12  (two separate merges)
    [4, 2, 2, 0]  ->  [4, 4, 0, 0]   scores 4   (the 4 cannot merge with a 2)
    [0, 0, 0, 2]  ->  [2, 0, 0, 0]   scores 0   (slides, nothing merges)
    [4, 2, 0, 0]  ->  [4, 2, 0, 0]   nothing happens: this row is already packed left
- Tiles of different values never merge; they just stack against each other.

WHAT HAPPENS AFTER YOUR MOVE
- If the board changed, exactly one new tile appears in a uniformly random empty
  cell. It is a 2 with probability 0.9, and a 4 with probability 0.1.
  So every successful move gives one empty cell back to the board.
- If your chosen direction could not slide or merge a single tile, nothing
  happens at all: no movement, no score, and no new tile. The turn is simply
  lost. Choosing a dead direction is always strictly worse than any other choice.

GAME OVER
- The game ends when no empty cell is left and no two orthogonally adjacent tiles
  share a value, so that no direction can change anything."""

OBJECTIVE = """Choose the direction to move next. Maximise the final score, which means
surviving as many moves as possible: keep empty cells available and build large
tiles by repeatedly merging. Reaching a 2048 tile wins."""

# Evaluative criteria rather than a fixed direction ranking. The `coached` arm
# below shows what a ranking does to this model: it locks onto one direction and
# repeats it into a wall, so these are deliberately phrased as things to weigh.
TIPS = """HOW TO JUDGE A MOVE -- weigh these against the actual board each turn. They are
considerations, not a fixed order of preference.

- Empty cells are the resource you are managing. A move that merges several pairs
  frees cells. A move that only shuffles tiles around costs you a cell, because a
  new tile spawns afterwards.
- First, rule out any direction that cannot move anything. Scan the rows (for
  left/right) or columns (for up/down): a direction works only if some tile has an
  empty cell ahead of it, or an equal-valued neighbour ahead of it.
- Merging your two largest equal tiles is usually worth more than several small
  merges, because it compounds.
- Keep large tiles adjacent to each other so they stay mergeable. Large tiles
  scattered across the board are stranded and clog it.
- Many strong players keep the largest tile in one corner and build a descending
  row toward it. Do this only while you can: if the move that preserves the corner
  is dead or fills the board, take a different one.
- If you have played the same direction several times and the board stopped
  changing, that direction is dead right now. Pick another."""

# Kept for comparison: a fixed direction ranking, which measurably backfires.
HEURISTIC = """Standard strong strategy: keep the largest tile locked in one corner, keep the
row and column leading to it in descending order, and never make a move that
pulls the largest tile out of its corner."""

# The ablation ladder. Each arm adds exactly one block to the one before it.
ARMS = {
    "bare": (RULES, None),
    "rules": (RULES_DETAILED, None),
    "tips": (RULES_DETAILED, TIPS),
    "coached": (RULES_DETAILED, HEURISTIC),
}

MOVES = {
    "up": "Slide every tile to the top of its column.",
    "down": "Slide every tile to the bottom of its column.",
    "left": "Slide every tile to the left of its row.",
    "right": "Slide every tile to the right of its row.",
}


def action_order(shuffle: bool, rng: _random.Random) -> list[str]:
    """The order the four options are presented in.

    Held fixed, a preference for one direction is indistinguishable from a
    preference for whichever option is listed first. Shuffling per move separates
    them.
    """
    order = list(DIRECTIONS)
    if shuffle:
        rng.shuffle(order)
    return order


def as_grid(board: list[int]) -> list[list[int]]:
    return [board[r * 4 : r * 4 + 4] for r in range(4)]


def build_state(state: dict, move_no: int, budget: int, recent: list[dict]) -> dict:
    """The board and its context. Identical for every provider."""
    return {
        "board": as_grid(state["board"]),
        "score": state["score"],
        "move_number": move_no,
        "moves_remaining": budget - move_no + 1,
        "highest_tile": state["maxTile"],
        "empty_cells": sum(1 for v in state["board"] if v == 0),
        # Honest feedback, not a hint: whether each recent move changed anything.
        "recent_moves": recent[-8:],
    }


def instructions_for(arm: str) -> dict:
    """The rules/objective/strategy blocks. Identical for every provider."""
    rules, guidance = ARMS[arm]
    instructions = {"rules": rules, "objective": OBJECTIVE}
    if guidance:
        instructions["strategy"] = guidance
    return instructions


def build(state: dict, move_no: int, budget: int, arm: str, recent: list[dict], order: list[str]):
    """TypeSafe transport: a structured choice question."""
    payload_state = build_state(state, move_no, budget, recent)
    instructions = instructions_for(arm)
    questions = {
        "direction": {
            "type": "choice",
            "criteria": {d: MOVES[d] for d in order},
            "instructions": instructions,
        }
    }
    return payload_state, questions


def build_chat(state: dict, move_no: int, budget: int, arm: str, recent: list[dict], order: list[str]):
    """OpenRouter transport: the same blocks, as chat messages."""
    instructions = instructions_for(arm)
    system = "\n\n".join(
        [instructions["rules"], instructions["objective"]]
        + ([instructions["strategy"]] if "strategy" in instructions else [])
        + ['Reply with JSON: {"direction": "<one of up, down, left, right>"}.']
    )
    options = "\n".join(f"- {d}: {MOVES[d]}" for d in order)
    user = (
        f"{json.dumps(build_state(state, move_no, budget, recent), indent=2)}\n\n"
        f"Your options:\n{options}\n\nWhich direction do you play?"
    )
    return system, user


def decide_typesafe(state, move_no, budget, arm, recent, order, **_kwargs) -> dict:
    payload_state, questions = build(state, move_no, budget, arm, recent, order)
    body, result, latency_ms = ask(payload_state, questions)
    answer = validate(result["answers"]["direction"], order)
    return {
        "direction": answer["choice"],
        "probabilities": answer["probabilities"],
        "confidence": answer["confidence"],
        "latency_ms": latency_ms,
        "model": result.get("model"),
        "usage": result.get("usage", {}),
        "reasoning": None,
        "reasoning_tokens": 0,
        "request": body,
    }


def decide_openrouter(
    state, move_no, budget, arm, recent, order, *, model: str, effort: str = "medium", seed: int | None = None
) -> dict:
    system, user = build_chat(state, move_no, budget, arm, recent, order)
    body, result, latency_ms = openrouter.ask(
        system, user, model=model, effort=effort, seed=seed, order=order
    )
    direction, reasoning = openrouter.parse(result, order)
    return {
        "direction": direction,
        # A language model returns one answer, not a calibrated distribution.
        "probabilities": None,
        "confidence": None,
        "latency_ms": latency_ms,
        "model": result.get("model", model),
        "usage": result.get("usage", {}),
        "reasoning": reasoning,
        "reasoning_tokens": openrouter.reasoning_tokens(result),
        "request": body,
    }


PROVIDERS = {"typesafe": decide_typesafe, "openrouter": decide_openrouter}


def decide(state, move_no, budget, arm, recent, order, provider: str = "typesafe", **kwargs) -> dict:
    return PROVIDERS[provider](state, move_no, budget, arm, recent, order, **kwargs)
