"""Probe 1: can the model tell which directions do anything?

No game loop, no strategy, no score. Show a board, ask four independent yes/no
questions -- "would this direction move or merge any tile?" -- and grade against
the engine. Chance is 50% per direction, 6.25% for getting all four right.

This isolates perception plus one-ply simulation. If a model fails here, its
2048 score explains itself and nothing further needs measuring.

    uv run --env-file .env python -m jev_play.legality --provider typesafe --boards 120
"""

import argparse
import json
import os
import random
from pathlib import Path

from . import openrouter
from .policy import RULES_DETAILED, as_grid
from .typesafe import ask, validate

DIRECTIONS = ("up", "down", "left", "right")

QUESTION = """Given the board, decide whether this one direction would change it.

A direction changes the board if at least one tile can slide into an empty cell
that way, or if at least two adjacent tiles in that direction have equal values
and would merge. If neither is true, the direction does nothing at all."""


def sample_boards(root: Path, count: int, seed: int = 7) -> list[dict]:
    """Real boards from recorded play, with the engine's verdict attached."""
    pool: list[dict] = []
    for path in sorted(root.glob("*/seed-*/moves.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("board_before") and row.get("legal") is not None:
                pool.append({"board": row["board_before"], "legal": row["legal"]})
    # Deduplicate, so a long run cannot dominate the probe.
    unique = {tuple(b["board"]): b for b in pool}
    rng = random.Random(seed)
    # Stratify. On most real boards all four directions work, and a model that
    # simply always answers "yes" scores ~85% on an unstratified sample without
    # discriminating anything. Half the probe is drawn from boards that have at
    # least one dead direction, where "always yes" is guaranteed wrong.
    easy = [b for b in unique.values() if len(b["legal"]) == 4]
    hard = [b for b in unique.values() if len(b["legal"]) < 4]
    rng.shuffle(easy)
    rng.shuffle(hard)
    half = count // 2
    picked = hard[:half] + easy[: count - min(half, len(hard))]
    rng.shuffle(picked)
    return picked[:count]


def ask_typesafe(board: list[int]) -> dict[str, bool]:
    """One request, four independent binary heads."""
    state = {"board": as_grid(board), "empty_cells": sum(1 for v in board if v == 0)}
    questions = {
        d: {
            "type": "choice",
            "criteria": {
                "changes": f"Moving {d} would slide or merge at least one tile.",
                "nothing": f"Moving {d} would change nothing at all.",
            },
            "instructions": {"rules": RULES_DETAILED, "question": QUESTION, "direction": d},
        }
        for d in DIRECTIONS
    }
    _body, result, _ms = ask(state, questions)
    return {d: validate(result["answers"][d], ["changes", "nothing"])["choice"] == "changes" for d in DIRECTIONS}


SCHEMA = {
    "name": "legality",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": list(DIRECTIONS),
        "properties": {d: {"type": "boolean"} for d in DIRECTIONS},
    },
}


def ask_openrouter(board: list[int], model: str, effort: str) -> dict[str, bool]:
    system = f"{RULES_DETAILED}\n\n{QUESTION}\n\nAnswer true if the direction changes the board, false if not."
    user = json.dumps({"board": as_grid(board)}, indent=2) + "\n\nFor each direction: does it change the board?"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
        "reasoning": {"effort": effort},
    }
    response = openrouter.CLIENT.post(
        openrouter.ENDPOINT,
        json=body,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
    )
    if response.is_error:
        raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {response.text[:300]}")
    answer = json.loads(response.json()["choices"][0]["message"]["content"])
    return {d: bool(answer[d]) for d in DIRECTIONS}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("typesafe", "openrouter"), default="typesafe")
    parser.add_argument("--model", default="openai/gpt-5.6-luna")
    parser.add_argument("--effort", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--boards", type=int, default=120)
    parser.add_argument("--artifacts", default="../../artifacts/jev")
    args = parser.parse_args()

    root = Path(args.artifacts)
    boards = sample_boards(root, args.boards)
    tag = "jev" if args.provider == "typesafe" else f"{args.model.rsplit('/', 1)[-1]}-{args.effort}"
    out = root / "legality" / f"{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    per_direction = exact = graded = 0
    # A board where every direction is legal is answered correctly by always
    # saying "yes", so track the discriminating subset separately.
    hard = hard_correct = 0
    with out.open("w") as log:
        for i, case in enumerate(boards, 1):
            truth = {d: d in case["legal"] for d in DIRECTIONS}
            try:
                said = (
                    ask_typesafe(case["board"])
                    if args.provider == "typesafe"
                    else ask_openrouter(case["board"], args.model, args.effort)
                )
            except Exception as error:  # noqa: BLE001 - record and continue
                log.write(json.dumps({"board": case["board"], "error": str(error)}) + "\n")
                continue
            correct = sum(1 for d in DIRECTIONS if said[d] == truth[d])
            per_direction += correct
            graded += 4
            exact += correct == 4
            if not all(truth.values()):
                hard += 1
                hard_correct += correct == 4
            log.write(json.dumps({"board": case["board"], "truth": truth, "said": said}) + "\n")
            if i % 20 == 0:
                print(f"  {i}/{len(boards)}  per-direction {per_direction / graded:.1%}", flush=True)

    print(f"\n{tag}: {graded // 4} boards graded")
    print(f"  per-direction accuracy : {per_direction / graded:.1%}   (chance 50%)")
    print(f"  all four correct       : {exact / (graded // 4):.1%}   (chance 6.25%)")
    if hard:
        print(f"  all four, boards with >=1 dead direction: {hard_correct / hard:.1%}  (n={hard})")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
