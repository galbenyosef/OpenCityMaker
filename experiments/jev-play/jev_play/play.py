"""Let the model play a full game of CityMaker.

    uv run --env-file .env python -m jev_play.play --seed 12345 --moves 300 --arm bare

One TypeSafe call per move: board in, direction out.
"""

import argparse
import json
import time
from pathlib import Path
from random import Random

from .game import Game
from .policy import ARMS, action_order, decide
from .report import compare, summarize


def short_model(model: str | None) -> str:
    """openai/gpt-5.6-luna -> luna; used only to name the artifact directory."""
    return (model or "jev").rsplit("/", 1)[-1].replace("gpt-5.6-", "")


def run(
    seed: int,
    budget: int,
    arm: str,
    base_url: str,
    out_dir: Path,
    shuffle: bool = False,
    provider: str = "typesafe",
    model: str | None = None,
    effort: str = "medium",
) -> dict:
    rng = Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    moves: list[dict] = []
    recent: list[dict] = []
    end = "move_budget"
    started = time.perf_counter()

    with Game(seed, base_url) as game, (out_dir / "moves.jsonl").open("w") as log:
        for n in range(1, budget + 1):
            if game.status == "lost":
                end = "lost"
                break
            if game.status == "won":
                game.keep_building()

            before = dict(game.state)
            tick = time.perf_counter()
            order = action_order(shuffle, rng)
            kwargs = {"model": model, "effort": effort, "seed": seed} if provider == "openrouter" else {}
            # The preview arm hands the model each move's computed outcome, so it
            # never has to simulate one itself.
            if arm == "preview":
                kwargs["previews"] = game.preview()
            try:
                decision = decide(before, n, budget, arm, recent, order, provider=provider, **kwargs)
            except (ValueError, RuntimeError) as error:
                log.write(json.dumps({"move": n, "seed": seed, "arm": arm, "error": str(error)}) + "\n")
                end = "model_error"
                break

            direction = decision["direction"]
            after = game.move(direction)
            record = {
                "move": n,
                "seed": seed,
                "arm": arm,
                "board_before": before["board"],
                "score_before": before["score"],
                "legal": before["legal"],
                "option_order": order,
                "direction": direction,
                "direction_probabilities": decision.get("probabilities"),
                "confidence": decision.get("confidence"),
                "latency_ms": decision["latency_ms"],
                "model": decision["model"],
                "usage": decision["usage"],
                "reasoning_tokens": decision.get("reasoning_tokens", 0),
                "changed": after["changed"],
                "gained": after["gained"],
                "board_after": after["board"],
                "score_after": after["score"],
                "max_tile_after": after["maxTile"],
                "status": after["status"],
                "wall_ms": round((time.perf_counter() - tick) * 1000),
            }
            # Keep the chain of thought only where it explains a mistake: a move
            # that turned out to do nothing. That is the evidence worth having.
            if not after["changed"] and decision.get("reasoning"):
                record["reasoning"] = decision["reasoning"][-1500:]
            moves.append(record)
            log.write(json.dumps(record) + "\n")
            log.flush()
            recent.append({"direction": direction, "changed": after["changed"], "gained": after["gained"]})
            # A language model returns one answer, so there may be no distribution.
            probabilities = decision.get("probabilities") or {}
            shown = f"p={probabilities[direction]:.2f}" if direction in probabilities else "      "
            print(
                f"{n:>4}  {direction:<6} {shown}"
                f"  score={after['score']:<7} max={after['maxTile']:<5} {decision['latency_ms']:>5}ms"
                f"{'' if after['changed'] else '  WASTED'}",
                flush=True,
            )

    summary = summarize(
        moves,
        {
            "arm": arm,
            "seed": seed,
            "budget": budget,
            "shuffled": shuffle,
            "protocol": "direct",
            "provider": provider,
            "model": model,
            "effort": effort if provider == "openrouter" else None,
            "end_reason": end,
            "wall_seconds": round(time.perf_counter() - started, 1),
        },
    )
    (out_dir / "run.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--moves", type=int, default=300)
    parser.add_argument("--arm", choices=tuple(ARMS), default="bare")
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomise the order the four options are listed in, per move, to separate "
        "order bias from a genuine direction preference.",
    )
    parser.add_argument("--provider", choices=("typesafe", "openrouter"), default="typesafe")
    parser.add_argument("--model", default=None, help="OpenRouter model id, e.g. openai/gpt-5.6-luna")
    parser.add_argument("--effort", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--base-url", default="http://127.0.0.1:5274")
    parser.add_argument("--out", default=None)
    parser.add_argument("--baselines", default="../../artifacts/jev/baselines.json")
    args = parser.parse_args()

    if args.provider == "openrouter":
        if not args.model:
            parser.error("--provider openrouter needs --model")
        label = f"{short_model(args.model)}-{args.effort}-{args.arm}"
    else:
        label = f"direct-{args.arm}"
    label += "-shuffled" if args.shuffle else ""
    out_dir = Path(args.out or f"../../artifacts/jev/{label}/seed-{args.seed}")
    summary = run(
        args.seed, args.moves, args.arm, args.base_url, out_dir,
        args.shuffle, args.provider, args.model, args.effort,
    )
    print("\n" + json.dumps(summary, indent=2))

    baselines_path = Path(args.baselines)
    baselines = json.loads(baselines_path.read_text()) if baselines_path.exists() else None
    print("\n" + compare(summary, baselines))
    print(f"\nartifacts -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
