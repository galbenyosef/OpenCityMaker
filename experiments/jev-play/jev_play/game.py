"""Client for the CityMaker game server (`server/game-server.ts`).

The server wraps the game's real engine, so this talks to the shipped rules
without a browser in the loop.
"""

import httpx

DIRECTIONS = ("up", "down", "left", "right")


class Game:
    def __init__(self, seed: int, base_url: str = "http://127.0.0.1:5274", mode: str = "slide"):
        self.client = httpx.Client(base_url=base_url, timeout=10)
        self.seed = seed
        self.state = self._post("/new", {"seed": seed, "mode": mode})
        self.id = self.state["id"]

    def _post(self, path: str, body: dict) -> dict:
        response = self.client.post(path, json=body)
        if response.is_error:
            raise RuntimeError(f"game server {response.status_code}: {response.text}")
        return response.json()

    def move(self, direction: str) -> dict:
        """Apply a move. `changed=False` means the direction was a no-op."""
        self.state = self._post("/move", {"id": self.id, "direction": direction})
        return self.state

    def preview(self) -> dict[str, dict]:
        """One-ply consequences per direction, computed by the engine."""
        result = self._post("/preview", {"id": self.id})
        return {p["direction"]: p for p in result["previews"]}

    def keep_building(self) -> dict:
        """Continue past a 2048 win, mirroring the game's own button."""
        self.state = self._post("/continue", {"id": self.id})
        return self.state

    @property
    def board(self) -> list[int]:
        return self.state["board"]

    @property
    def status(self) -> str:
        return self.state["status"]

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Game":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def board_lines(board: list[int]) -> list[str]:
    return [f"row {r + 1}: " + " ".join(str(v) if v else "." for v in board[r * 4 : r * 4 + 4]) for r in range(4)]
