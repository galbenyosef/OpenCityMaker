"""OpenRouter chat-completions client, for the traditional-LLM arms.

Deliberately mirrors `typesafe.py`: one `ask()` that posts a body and returns
`(body, response, latency_ms)`. The difference is the shape of the request --
chat messages plus a strict json_schema instead of a structured choice question
-- and that a language model returns one answer rather than a distribution.

Reasoning models take seconds, not milliseconds, hence the much longer timeout.
"""

import json
import os
import time

import httpx

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
CLIENT = httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0))

DIRECTIONS = ("up", "down", "left", "right")

# strict + enum means the model structurally cannot answer with a non-direction.
def schema(order: list[str] | tuple[str, ...] = DIRECTIONS) -> dict:
    """Enum order follows the presented option order.

    It is semantically irrelevant to a validator but it is a token sequence in
    the prompt, so if it disagreed with the prose option list the --shuffle
    positional-bias control would be measuring one thing while the model
    responded to another.
    """
    return {
        "name": "move",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["direction"],
            "properties": {"direction": {"type": "string", "enum": list(order)}},
        },
    }


SCHEMA = schema()

RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}


def ask(
    system: str,
    user: str,
    model: str,
    effort: str = "medium",
    seed: int | None = None,
    include_reasoning: bool = True,
    order: list[str] | None = None,
) -> tuple[dict, dict, int]:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_schema", "json_schema": schema(order or DIRECTIONS)},
        "reasoning": {"effort": effort},
        "include_reasoning": include_reasoning,
    }
    if seed is not None:
        body["seed"] = seed

    key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {key}",
        # OpenRouter attributes traffic with these; harmless and good manners.
        "HTTP-Referer": "https://github.com/derek/OpenCityMaker",
        "X-Title": "CityMaker 2048 policy experiment",
    }
    for attempt in range(4):
        # Reset per attempt so retry backoff never counts as model latency.
        started = time.perf_counter()
        try:
            response = CLIENT.post(ENDPOINT, json=body, headers=headers)
        except httpx.HTTPError as error:
            if attempt == 3:
                raise RuntimeError(f"OpenRouter connection failed: {error}") from None
            time.sleep(2**attempt)
            continue
        if response.status_code in RETRY_STATUS and attempt < 3:
            time.sleep(2**attempt)
            continue
        if response.is_error:
            raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {response.text[:400]}")
        return body, response.json(), round((time.perf_counter() - started) * 1000)
    raise RuntimeError("OpenRouter unavailable after retries")


def parse(result: dict, options: list[str]) -> tuple[str, str | None]:
    """Pull the direction (and any exposed reasoning) out of a completion."""
    try:
        choice = result["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"unusable OpenRouter response: {json.dumps(result)[:400]}") from None

    if message.get("refusal"):
        raise ValueError(f"model refused: {message['refusal'][:200]}")

    content = message.get("content")
    if not content:
        raise ValueError(f"empty completion (finish_reason={choice.get('finish_reason')!r})")
    try:
        direction = json.loads(content)["direction"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise ValueError(f"completion was not the expected schema: {content[:200]}") from None
    if direction not in options:
        raise ValueError(f"model returned {direction!r}, not one of {options}")

    reasoning = message.get("reasoning")
    if not reasoning and isinstance(message.get("reasoning_details"), list):
        reasoning = " ".join(
            part.get("text", "") for part in message["reasoning_details"] if isinstance(part, dict)
        ).strip()
    return direction, reasoning or None


def reasoning_tokens(result: dict) -> int:
    usage = result.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return details.get("reasoning_tokens", 0) or 0
