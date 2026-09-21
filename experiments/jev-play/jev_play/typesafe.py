"""Minimal direct client for TypeSafe's choice endpoint.

The earlier version of this experiment went through `jev_ultrafast.model.choose`,
which wraps every question in browser-agent scaffolding: an `elements` list, an
`operation` head offering CLICK/DONE/BLOCKED, and `NEXT_ACTION` -- a block of
form-filling rules about autocomplete suggestions and date pickers -- attached to
every question. None of that belongs in a tile game.

This talks to the same model with nothing but the board and the rules.
"""

import os
import time

import httpx

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CLIENT = httpx.Client(http2=True, timeout=30)


def ask(state: dict, questions: dict, model: str | None = None) -> tuple[dict, dict, int]:
    """Post one request. Returns (request_body, response, latency_ms)."""
    body = {
        "model": model or os.environ.get("TYPESAFE_MODEL", "jev-latest"),
        "state": state,
        "questions": questions,
    }
    key = os.environ["TYPESAFE_API_KEY"]
    for attempt in range(3):
        # Reset per attempt: retry backoff is not model latency, and letting it
        # leak in turns p95 into a rate-limit meter.
        started = time.perf_counter()
        try:
            response = CLIENT.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as error:
            raise RuntimeError(f"TypeSafe connection failed: {error}") from None
        if response.status_code in {429, 503, 529} and attempt < 2:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            raise RuntimeError(f"TypeSafe HTTP {response.status_code}: {response.text[:300]}")
        return body, response.json(), round((time.perf_counter() - started) * 1000)
    raise RuntimeError("TypeSafe unavailable")


def validate(answer: dict, options: list[str]) -> dict:
    """The model must return one of our options, with a real distribution over exactly them."""
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        ok = (
            answer["choice"] in options
            and set(probabilities) == set(options)
            and all(isinstance(n, (int, float)) and 0 <= n <= 1 for n in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
        )
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        raise ValueError(f"unusable TypeSafe answer: {answer!r}")
    return answer
