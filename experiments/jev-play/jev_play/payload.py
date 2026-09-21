"""Print the exact request body, without sending it.

    uv run python -m jev_play.payload --moves-in left,up,left,down
"""

import argparse
import json

from .game import Game
from .openrouter import SCHEMA
from .policy import ARMS, DIRECTIONS_ORDER, build, build_chat


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--moves-in", default="left,up,left,down", help="Moves to play first, for a live board.")
    parser.add_argument("--arm", choices=tuple(ARMS), default="bare")
    parser.add_argument("--provider", choices=("typesafe", "openrouter"), default="typesafe")
    parser.add_argument("--model", default="openai/gpt-5.6-luna")
    parser.add_argument("--base-url", default="http://127.0.0.1:5274")
    args = parser.parse_args()

    with Game(args.seed, args.base_url) as game:
        recent = []
        for direction in filter(None, (m.strip() for m in args.moves_in.split(","))):
            result = game.move(direction)
            recent.append({"direction": direction, "changed": result["changed"], "gained": result["gained"]})
        if args.provider == "openrouter":
            system, user = build_chat(game.state, 5, 300, args.arm, recent, list(DIRECTIONS_ORDER))
            body = {
                "model": args.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": SCHEMA},
                "reasoning": {"effort": "medium"},
            }
        else:
            state, questions = build(game.state, 5, 300, args.arm, recent, list(DIRECTIONS_ORDER))
            body = {"model": "jev-latest", "state": state, "questions": questions}

    print(json.dumps(body, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
