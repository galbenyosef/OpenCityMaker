"""Turn a moves.jsonl log into the numbers the experiment is actually asking for."""

import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

from .game import DIRECTIONS


def entropy(counts: Counter) -> float:
    """Shannon entropy in bits over the 4 directions. 2.0 = uniform, 0.0 = one direction forever."""
    total = sum(counts.values())
    if not total:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values() if n)


def tokens(record: dict, *names: str) -> int:
    usage = record.get("usage") or {}
    value = next((usage[name] for name in names if name in usage), 0)
    # A failed or streaming-interrupted call can report usage fields as null.
    return value if isinstance(value, int) else 0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summarize(moves: list[dict], meta: dict) -> dict:
    clicks = [m for m in moves if m.get("direction")]
    executed = [m for m in clicks if m["changed"]]
    wasted = [m for m in clicks if not m["changed"]]
    directions = Counter(m["direction"] for m in clicks)
    latencies = [m["latency_ms"] for m in moves if m.get("latency_ms") is not None]
    confidences = [m["confidence"] for m in moves if m.get("confidence") is not None]
    confident_legal = [m["confidence"] for m in executed if m.get("confidence") is not None]
    confident_wasted = [m["confidence"] for m in wasted if m.get("confidence") is not None]
    last = moves[-1] if moves else {}
    return {
        **meta,
        "final_score": last.get("score_after", 0),
        "max_tile": last.get("max_tile_after", 0),
        "decisions": len(moves),
        "clicks": len(clicks),
        # NOTE: this is the exact complement of wasted_move_rate, not an
        # independent check. The game server defines `legal` as "this direction
        # changes the board", so `direction in legal` is identical to `changed`.
        # Kept for older artifacts; report only one of the two.
        "legal_pick_rate": round(sum(1 for m in clicks if m["direction"] in (m.get("legal") or [])) / len(clicks), 4)
        if clicks
        else None,
        "moves_applied": len(executed),
        # The sharpest single number: did it pick a direction that does nothing?
        "wasted_move_rate": round(len(wasted) / len(clicks), 4) if clicks else None,
        "direction_counts": {d: directions.get(d, 0) for d in DIRECTIONS},
        # Catches the degenerate "presses left forever" policy, which scores by accident.
        "direction_entropy_bits": round(entropy(directions), 4),
        # Language models return one answer, not a calibrated distribution, so
        # every confidence here can legitimately be None.
        "mean_confidence": round(mean(confidences), 4) if confidences else None,
        "confidence_on_applied": round(mean(confident_legal), 4) if confident_legal else None,
        "confidence_on_wasted": round(mean(confident_wasted), 4) if confident_wasted else None,
        "latency_ms_p50": round(percentile(latencies, 0.50)) if latencies else None,
        "latency_ms_p95": round(percentile(latencies, 0.95)) if latencies else None,
        "latency_ms_mean": round(mean(latencies)) if latencies else None,
        # TypeSafe reports input_tokens/output_tokens; accept the OpenAI names too.
        "input_tokens": sum(tokens(m, "input_tokens", "prompt_tokens") for m in moves),
        "output_tokens": sum(tokens(m, "output_tokens", "completion_tokens") for m in moves),
        # Nested under usage.completion_tokens_details, so not reachable by `tokens`.
        "reasoning_tokens": sum(m.get("reasoning_tokens") or 0 for m in moves),
    }


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def compare(run: dict, baselines: dict | None) -> str:
    """One scannable table: the jev arm against every baseline policy."""
    rows = [("jev/" + run["arm"], run["final_score"], run["max_tile"], run["moves_applied"], run["wasted_move_rate"])]
    for name, stats in (baselines or {}).get("policies", {}).items():
        rows.append(
            (name, stats["median_score"], stats["median_max_tile"], stats["median_moves"], stats["wasted_rate"])
        )
    width = max(len(r[0]) for r in rows)
    header = f"{'policy'.ljust(width)}  {'score':>8}  {'maxTile':>8}  {'moves':>6}  {'wasted':>7}"
    lines = [header, "-" * len(header)]
    for name, score, tile, moves, waste in rows:
        waste_text = "-" if waste is None else f"{waste:.1%}"
        lines.append(f"{name.ljust(width)}  {score:>8}  {tile:>8}  {moves:>6}  {waste_text:>7}")
    return "\n".join(lines)
