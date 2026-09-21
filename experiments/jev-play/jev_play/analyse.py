"""Compare finished arms, and answer the confound the headline number raises.

A policy that always picks "up" and a policy that always picks the first offered
option look identical under a fixed action order. Shuffling the order per move
separates them:

  * positional  -> chosen_index stays e1 while the direction varies
  * directional -> the direction stays "up" while chosen_index varies

    uv run python -m jev_play.analyse
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from .report import compare, entropy, load


def describe(run_dir: Path) -> dict | None:
    summary_path, log_path = run_dir / "run.json", run_dir / "moves.jsonl"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text())
    moves = [m for m in load(log_path) if m.get("direction")]
    # Which listed position the pick came from -- order bias vs direction preference.
    positions = Counter(
        str((m.get("option_order") or m.get("action_order") or []).index(m["direction"]) + 1)
        for m in moves
        if m["direction"] in (m.get("option_order") or m.get("action_order") or [])
    )
    indices = positions
    directions = Counter(m["direction"] for m in moves)
    orders = [m.get("option_order") or m.get("action_order") for m in moves]
    shuffled = any(o != orders[0] for o in orders) if orders else False
    summary.update(
        shuffled=shuffled,
        index_counts=dict(indices),
        index_entropy_bits=round(entropy(indices), 4) if indices else None,
        top_index_share=round(max(indices.values()) / sum(indices.values()), 4) if indices else None,
        top_direction_share=round(max(directions.values()) / sum(directions.values()), 4) if directions else None,
        # How often the pick was a legal move -- the direct "is it reading the board" test.
        legal_pick_rate=round(sum(1 for m in moves if m["direction"] in m["legal"]) / len(moves), 4) if moves else None,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="../../artifacts/jev")
    args = parser.parse_args()
    root = Path(args.artifacts)

    runs = [r for d in sorted(root.glob("*/seed-*")) if (r := describe(d))]
    baselines_path = root / "baselines.json"
    baselines = json.loads(baselines_path.read_text()) if baselines_path.exists() else None

    for run in runs:
        label = f"{run.get('protocol', 'jev-agent')}/{run['arm']}" + ("-shuffled" if run["shuffled"] else "")
        print(f"\n=== {label} (seed {run['seed']}) ===")
        print(
            f"score {run['final_score']}  maxTile {run['max_tile']}  applied {run['moves_applied']}/{run['clicks']}"
            f"  wasted {run['wasted_move_rate']:.1%}"
        )
        print(f"directions {run['direction_counts']}  entropy {run['direction_entropy_bits']} bits")
        print(
            f"positions  {run['index_counts']}  entropy {run['index_entropy_bits']} bits"
            f"  (shuffled={run['shuffled']})"
        )
        print(f"legal-pick rate {run['legal_pick_rate']:.1%}   latency p50 {run['latency_ms_p50']}ms")

    if runs:
        print("\n" + compare(runs[0], baselines))
        print("\nchance legal-pick rate for a blind policy is ~75-100% (most boards have 3-4 legal moves)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
