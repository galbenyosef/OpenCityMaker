"""Every finished run, side by side with the baselines.

Auto-discovers whatever is under `artifacts/jev/<tag>/seed-*`, so jev's prompt
arms and the OpenRouter LLM arms appear in one table. Sorted by median score.

    uv run python -m jev_play.ladder
    uv run python -m jev_play.ladder --seeds 1000

`legal_pick_rate` is deliberately not shown: the game server defines a legal
direction as one that changes the board, so it is the exact complement of
`wasted` and printing both would present one metric as two findings.
"""

import argparse
import json
from pathlib import Path
from statistics import median

BASELINES = ("random", "random-legal", "priority-left-up")
SKIP = {"baselines.json", "per-seed-baselines.json"}


def collect(root: Path, seeds: list[int] | None) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    for path in sorted(root.glob("*/seed-*/run.json")):
        tag = path.parent.parent.name
        if tag in SKIP:
            continue
        run = json.loads(path.read_text())
        if seeds and run.get("seed") not in seeds:
            continue
        runs.setdefault(tag, []).append(run)
    return runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="../../artifacts/jev")
    parser.add_argument("--seeds", default=None, help="Comma-separated; default is every seed found.")
    args = parser.parse_args()
    root = Path(args.artifacts)
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None

    runs = collect(root, seeds)
    if not runs:
        print(f"no runs under {root}")
        return 1

    rows = []
    for tag, group in runs.items():
        rows.append(
            {
                "tag": tag,
                "n": len(group),
                "score": median([r.get("final_score", 0) for r in group]),
                "tile": median([r.get("max_tile", 0) for r in group]),
                "moves": median([r.get("moves_applied", 0) for r in group]),
                "wasted": median([r.get("wasted_move_rate") or 0 for r in group]),
                "entropy": median([r.get("direction_entropy_bits") or 0 for r in group]),
                "latency": median([r.get("latency_ms_p50") or 0 for r in group]),
                "reasoning": median([r.get("reasoning_tokens") or 0 for r in group]),
            }
        )

    per_seed_path = root / "per-seed-baselines.json"
    per_seed = json.loads(per_seed_path.read_text()) if per_seed_path.exists() else {}
    baseline_seeds = seeds or sorted({int(s) for s in next(iter(per_seed.values()), {})}) if per_seed else []
    for name in BASELINES:
        games = [per_seed[name][str(s)] for s in baseline_seeds if str(s) in per_seed.get(name, {})]
        if not games:
            continue
        waste = median([g["wasted"] / g["moves"] for g in games])
        rows.append(
            {
                "tag": name,
                "n": len(games),
                "score": median([g["score"] for g in games]),
                "tile": median([g["maxTile"] for g in games]),
                "moves": median([g["moves"] for g in games]),
                "wasted": waste,
                "entropy": None,
                "latency": None,
                "reasoning": None,
            }
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    width = max(len(r["tag"]) for r in rows)
    header = (
        f"{'policy'.ljust(width)} {'n':>2} {'score':>7} {'tile':>6} {'moves':>6} "
        f"{'wasted':>7} {'entropy':>7} {'p50 ms':>8} {'think tok':>10}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        ent = f"{r['entropy']:.2f}" if r["entropy"] is not None else "-"
        lat = f"{r['latency']:.0f}" if r["latency"] is not None else "-"
        think = f"{r['reasoning']:.0f}" if r["reasoning"] else "-"
        print(
            f"{r['tag'].ljust(width)} {r['n']:>2} {r['score']:>7.0f} {r['tile']:>6.0f} {r['moves']:>6.0f} "
            f"{r['wasted']:>6.1%} {ent:>7} {lat:>8} {think:>10}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
