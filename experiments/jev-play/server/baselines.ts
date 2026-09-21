/**
 * Reference policies for the jev experiment, played against the game's real engine.
 *
 *   npx vite-node experiments/jev-play/server/baselines.ts -- --seeds 200
 *
 * Same seeded LCG as the game server, so a seed names one exact game and the
 * comparison against a jev run on that seed is paired.
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import {
  continueRun,
  getStatus,
  move,
  newRun,
  slide,
  type Board,
  type Direction,
  type Run,
} from "../../../src/game/engine";
import { lcg } from "./rng";

const DIRECTIONS: Direction[] = ["up", "down", "left", "right"];
const MOVE_CAP = 20000;

const legal = (run: Run) => DIRECTIONS.filter((d) => move(run, d, () => 0).changed);

type Policy = (run: Run, random: () => number) => Direction;

/** Uniform over all four directions, no-ops included: what an agent that cannot read the board does. */
const random: Policy = (_run, rng) => DIRECTIONS[Math.floor(rng() * 4) % 4];

/** Uniform over legal moves only: isolates "can't read the board" from "can't pick well". */
const randomLegal: Policy = (run, rng) => {
  const options = legal(run);
  return options[Math.floor(rng() * options.length) % options.length] ?? "left";
};

/** The classic dumb 2048 ladder, and the degenerate policy an LLM tends to collapse into. */
const priority: Policy = (run) => {
  const options = legal(run);
  return (["left", "up", "right", "down"] as Direction[]).find((d) => options.includes(d)) ?? "left";
};

/** Board quality: free space dominates, then keeping rows/columns ordered and neighbours close. */
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

/** Depth-2 expectimax over the spawn distribution: the upper reference. */
const expectimax: Policy = (run) => {
  let best: Direction = "left";
  let bestValue = -Infinity;
  for (const direction of legal(run)) {
    const first = slide(run.board, direction);
    const empties = first.board.flatMap((v, i) => (v === 0 ? [i] : []));
    if (!empties.length) continue;
    // Average over spawn positions, weighting 2 at 0.9 and 4 at 0.1.
    let expected = 0;
    for (const index of empties) {
      for (const [value, weight] of [[2, 0.9] as const, [4, 0.1] as const]) {
        const next = [...first.board];
        next[index] = value;
        const replies = DIRECTIONS.map((d) => slide(next, d)).filter(
          (r) => !r.board.every((v, i) => v === next[i]),
        );
        const best2 = replies.length
          ? Math.max(...replies.map((r) => heuristic(r.board) + r.points * 0.5))
          : -500;
        expected += (weight / empties.length) * best2;
      }
    }
    const value = expected + first.points * 0.5;
    if (value > bestValue) {
      bestValue = value;
      best = direction;
    }
  }
  return best;
};

const POLICIES: Record<string, Policy> = {
  random,
  "random-legal": randomLegal,
  "priority-left-up": priority,
  "expectimax-d2": expectimax,
};

function play(policy: Policy, seed: number) {
  const rng = lcg(seed);
  let run = newRun(rng);
  let moves = 0;
  let wasted = 0;
  while (moves < MOVE_CAP) {
    if (run.status === "won") run = continueRun(run);
    if (getStatus(run.board, true, run.hasWon) === "lost") break;
    const result = move(run, policy(run, rng), rng);
    moves += 1;
    if (!result.changed) wasted += 1;
    run = result.run;
  }
  return { score: run.score, maxTile: Math.max(...run.board), moves, wasted };
}

const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

const argOf = (name: string, fallback: string) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : fallback;
};

const seedCount = Number(argOf("--seeds", "200"));
const out = argOf("--out", "artifacts/jev/baselines.json");
const seeds = Array.from({ length: seedCount }, (_, i) => 1000 + i);

const policies: Record<string, unknown> = {};
for (const [name, policy] of Object.entries(POLICIES)) {
  const started = Date.now();
  const games = seeds.map((seed) => play(policy, seed));
  const scores = games.map((g) => g.score);
  policies[name] = {
    median_score: median(scores),
    mean_score: Math.round(mean(scores)),
    max_score: Math.max(...scores),
    median_max_tile: median(games.map((g) => g.maxTile)),
    best_tile: Math.max(...games.map((g) => g.maxTile)),
    median_moves: median(games.map((g) => g.moves)),
    wasted_rate: Number((mean(games.map((g) => g.wasted / g.moves))).toFixed(4)),
    seconds: Number(((Date.now() - started) / 1000).toFixed(1)),
  };
  console.log(name.padEnd(18), JSON.stringify(policies[name]));
}

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({ seeds: seedCount, seed_base: 1000, policies }, null, 2));
console.log(`\nwrote ${out}`);
