/**
 * One seeded LCG shared by the game server and the baseline runner, so a seed
 * names the same game in both and a jev run can be compared move-for-move
 * against a baseline on that seed.
 */
export function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}
