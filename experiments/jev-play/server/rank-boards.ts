/**
 * Score every logged board with depth-2 expectimax, so a model's actual choice
 * can be compared against a strong reference move.
 *
 *   npx vite-node experiments/jev-play/server/rank-boards.ts -- \
 *     --log artifacts/jev/direct-rules/seed-1000/moves.jsonl
 *
 * Emits one JSON line per board: the ranking of all four directions best-first,
 * plus each direction's value and whether it is legal. Joining this back onto
 * the move log separates "can it tell which moves are legal" from "can it tell
 * which legal move is better" -- two very different failures.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { slide, type Board, type Direction } from "../../../src/game/engine";

const DIRECTIONS: Direction[] = ["up", "down", "left", "right"];

function heuristic(board: Board): number {
  const empties = board.filter((v) => !v).length;
  let monotonic = 0;
  let smooth = 0;
  for (let i = 0; i < 16; i++) {
    const right = i % 4 < 3 ? board[i + 1] : null;
    const down = i < 12 ? board[i + 4] : null;
    for (const neighbour of [right, down]) {
      if (neighbour === null) continue;
      if (board[i] && neighbour) smooth -= Math.abs(Math.log2(board[i]) - Math.log2(neighbour));
      if (board[i] >= neighbour) monotonic += 1;
    }
  }
  return empties * 12 + monotonic * 2 + smooth;
}

/** Expected value of `direction` from `board`, averaging over the spawn. */
function value(board: Board, direction: Direction): number | null {
  const first = slide(board, direction);
  if (first.board.every((v, i) => v === board[i])) return null; // illegal
  const empties = first.board.flatMap((v, i) => (v === 0 ? [i] : []));
  if (!empties.length) return first.points * 0.5 + heuristic(first.board);
  let expected = 0;
  for (const index of empties) {
    for (const [tile, weight] of [[2, 0.9] as const, [4, 0.1] as const]) {
      const next = [...first.board];
      next[index] = tile;
      const replies = DIRECTIONS.map((d) => slide(next, d)).filter(
        (r) => !r.board.every((v, i) => v === next[i]),
      );
      const best = replies.length
        ? Math.max(...replies.map((r) => heuristic(r.board) + r.points * 0.5))
        : -500;
      expected += (weight / empties.length) * best;
    }
  }
  return expected + first.points * 0.5;
}

const argOf = (name: string, fallback: string) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : fallback;
};

const logPath = argOf("--log", "");
if (!logPath) throw new Error("pass --log <moves.jsonl>");
const out = argOf("--out", logPath.replace(/\.jsonl$/, ".ranked.jsonl"));

const lines = readFileSync(logPath, "utf8").split("\n").filter(Boolean);
const ranked = lines.map((line) => {
  const row = JSON.parse(line);
  const board: Board = row.board_before;
  const values = Object.fromEntries(DIRECTIONS.map((d) => [d, value(board, d)]));
  const legal = DIRECTIONS.filter((d) => values[d] !== null);
  const ranking = [...legal].sort((a, b) => (values[b] as number) - (values[a] as number));
  return JSON.stringify({
    move: row.move,
    chose: row.direction,
    legal,
    ranking,
    best: ranking[0] ?? null,
    // Where the model's pick sat in the reference ordering: 1 = best legal move.
    rank_of_choice: ranking.indexOf(row.direction) + 1 || null,
    values,
  });
});

writeFileSync(out, ranked.join("\n") + "\n");
console.log(`ranked ${ranked.length} boards -> ${out}`);
