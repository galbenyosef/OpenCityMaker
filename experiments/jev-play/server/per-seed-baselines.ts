/**
 * Baseline scores for specific seeds, so a model run can be compared against
 * the *same game* rather than against a median over different games.
 *
 *   npx vite-node experiments/jev-play/server/per-seed-baselines.ts -- --seeds 1000,1001,1002
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import {
  continueRun,
  getStatus,
  move,
  newRun,
  type Direction,
  type Run,
} from "../../../src/game/engine";
import { lcg } from "./rng";

const DIRECTIONS: Direction[] = ["up", "down", "left", "right"];
const legal = (run: Run) => DIRECTIONS.filter((d) => move(run, d, () => 0).changed);

const POLICIES: Record<string, (run: Run, rng: () => number) => Direction> = {
  random: (_run, rng) => DIRECTIONS[Math.floor(rng() * 4) % 4],
  "random-legal": (run, rng) => {
    const options = legal(run);
    return options[Math.floor(rng() * options.length) % options.length] ?? "left";
  },
  "priority-left-up": (run) => {
    const options = legal(run);
    return (["left", "up", "right", "down"] as Direction[]).find((d) => options.includes(d)) ?? "left";
  },
};

function play(policy: (run: Run, rng: () => number) => Direction, seed: number) {
  const rng = lcg(seed);
  let run = newRun(rng);
  let moves = 0;
  let wasted = 0;
  while (moves < 20000) {
    if (run.status === "won") run = continueRun(run);
    if (getStatus(run.board, true, run.hasWon) === "lost") break;
    const result = move(run, policy(run, rng), rng);
    moves += 1;
    if (!result.changed) wasted += 1;
    run = result.run;
  }
  return { score: run.score, maxTile: Math.max(...run.board), moves, wasted };
}

const argOf = (name: string, fallback: string) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : fallback;
};

const seeds = argOf("--seeds", "1000,1001,1002,1003,1004").split(",").map(Number);
const out = argOf("--out", "artifacts/jev/per-seed-baselines.json");

const results: Record<string, Record<number, unknown>> = {};
for (const [name, policy] of Object.entries(POLICIES)) {
  results[name] = Object.fromEntries(seeds.map((seed) => [seed, play(policy, seed)]));
}

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(results, null, 2));
for (const seed of seeds) {
  const cells = Object.entries(results).map(([n, v]) => `${n}=${(v[seed] as any).score}`);
  console.log(seed, cells.join("  "));
}
console.log(`\nwrote ${out}`);
