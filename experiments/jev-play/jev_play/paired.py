"""Paired comparison: the model against the baselines on the *same* seeds.

Comparing one run against a median over 200 different games is not a comparison.
This lines up seed-for-seed.

    uv run python -m jev_play.paired --arm direct-bare --seeds 1000,1001,1002,1003,1004
"""

import argparse
import json
from pathlib import Path
from statistics import median

POLICIES = ("random", "random-legal", "priority-left-up")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="../../artifacts/jev")
    parser.add_argument("--arm", default="direct-bare")
    parser.add_argument("--seeds", default="1000,1001,1002,1003,1004")
    args = parser.parse_args()

    root = Path(args.artifacts)
    per_seed = json.loads((root / "per-seed-baselines.json").read_text())
    seeds = [int(s) for s in args.seeds.split(",")]

    runs = {}
    for seed in seeds:
        path = root / args.arm / f"seed-{seed}" / "run.json"
        if path.exists():
            runs[seed] = json.loads(path.read_text())
    if not runs:
        print(f"no runs found under {root / args.arm}")
        return 1

    head = f"{'seed':>6} {args.arm:>14} " + " ".join(f"{p:>16}" for p in POLICIES)
    head += f"   {'wasted':>7} {'legal-pick':>10} {'moves':>6}"
    print(head)
    print("-" * len(head))
    for seed, run in runs.items():
        cells = " ".join(f"{per_seed[p][str(seed)]['score']:>16}" for p in POLICIES)
        print(
            f"{seed:>6} {run['final_score']:>14} {cells}   "
            f"{run['wasted_move_rate']:>6.1%} {run['legal_pick_rate']:>9.1%} {run['moves_applied']:>6}"
        )

    scores = [r["final_score"] for r in runs.values()]
    medians = " ".join(f"{median([per_seed[p][str(s)]['score'] for s in runs]):>16}" for p in POLICIES)
    print("-" * len(head))
    print(f"{'median':>6} {median(scores):>14} {medians}")

    print()
    for policy in POLICIES:
        wins = sum(1 for s, r in runs.items() if r["final_score"] > per_seed[policy][str(s)]["score"])
        print(f"{args.arm} beats {policy:<18} on {wins}/{len(runs)} paired seeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
