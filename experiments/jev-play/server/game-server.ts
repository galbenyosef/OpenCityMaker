/**
 * A headless control surface for CityMaker, over HTTP.
 *
 * It imports the game's real engine (`src/game/engine.ts`) -- the same pure,
 * dependency-free module the browser app plays through -- so the rules, the
 * scoring and the spawn behaviour are the shipped ones, not a re-implementation.
 * Driving it needs no browser, no CDP and no DOM.
 *
 *   npx vite-node experiments/jev-play/server/game-server.ts -- --port 5274
 *
 *   POST /new    {seed, mode?}  -> {id, board, score, status, moves, maxTile, legal}
 *   GET  /state?id=...          -> same shape
 *   POST /move   {id, direction} -> same shape, plus {changed, gained}
 *   POST /continue {id}         -> past a 2048 win, mirrors the "Keep building" button
 */

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import {
  continueRun,
  move,
  newRun,
  slide,
  type Direction,
  type MoveMode,
  type Run,
} from "../../../src/game/engine";

import { lcg } from "./rng";

const DIRECTIONS: Direction[] = ["up", "down", "left", "right"];

interface Session {
  id: string;
  run: Run;
  random: () => number;
  mode: MoveMode;
  moves: number;
  wasted: number;
}

const sessions = new Map<string, Session>();

/**
 * `move` is pure and only consumes randomness when the board actually changes,
 * so probing legality here cannot perturb the session's spawn sequence.
 */
const legal = (session: Session) =>
  DIRECTIONS.filter((d) => move(session.run, d, () => 0, session.mode).changed);

function view(session: Session, extra: Record<string, unknown> = {}) {
  return {
    id: session.id,
    board: session.run.board,
    score: session.run.score,
    status: session.run.status,
    moves: session.moves,
    wasted: session.wasted,
    maxTile: Math.max(...session.run.board),
    legal: legal(session),
    ...extra,
  };
}

function get(id: unknown): Session {
  const session = typeof id === "string" ? sessions.get(id) : undefined;
  if (!session) throw new Error(`no such session: ${String(id)}`);
  return session;
}

const routes: Record<string, (body: any, query: URLSearchParams) => unknown> = {
  "POST /new": (body) => {
    const seed = Number(body.seed ?? Date.now());
    if (!Number.isFinite(seed)) throw new Error("seed must be a number");
    const random = lcg(seed);
    const session: Session = {
      id: `s${seed}-${sessions.size + 1}`,
      run: newRun(random),
      random,
      mode: body.mode === "step" ? "step" : "slide",
      moves: 0,
      wasted: 0,
    };
    sessions.set(session.id, session);
    return view(session, { seed });
  },
  "GET /state": (_body, query) => view(get(query.get("id"))),
  "POST /move": (body) => {
    const session = get(body.id);
    if (!DIRECTIONS.includes(body.direction)) throw new Error(`bad direction: ${String(body.direction)}`);
    const before = session.run.score;
    const result = move(session.run, body.direction, session.random, session.mode);
    session.run = result.run;
    session.moves += 1;
    if (!result.changed) session.wasted += 1;
    return view(session, { changed: result.changed, gained: session.run.score - before });
  },
  "POST /continue": (body) => {
    const session = get(body.id);
    session.run = continueRun(session.run);
    return view(session);
  },
  /**
   * One-ply consequences of each direction, computed by the engine.
   *
   * Lets an experiment hand a model the outcome of every move instead of
   * requiring it to simulate one, which separates "cannot simulate" from
   * "cannot choose". `slide` is pure, so probing costs no randomness.
   */
  "POST /preview": (body) => {
    const session = get(body.id);
    const previews = DIRECTIONS.map((direction) => {
      const result = slide(session.run.board, direction, session.mode);
      const changed = !result.board.every((v, i) => v === session.run.board[i]);
      return {
        direction,
        changed,
        gained: result.points,
        merges: result.events.filter((e) => e.merged).length / 2,
        empty_after: result.board.filter((v) => !v).length,
        max_after: Math.max(...result.board),
      };
    });
    return { id: session.id, previews };
  },
  "GET /health": () => ({ ok: true, sessions: sessions.size }),
};

async function readBody(request: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

function send(response: ServerResponse, status: number, payload: unknown) {
  const body = JSON.stringify(payload);
  response.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
  response.end(body);
}

const port = Number(process.argv[process.argv.indexOf("--port") + 1]) || 5274;

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  const route = routes[`${request.method} ${url.pathname}`];
  if (!route) return send(response, 404, { error: `no route for ${request.method} ${url.pathname}` });
  try {
    send(response, 200, route(await readBody(request), url.searchParams));
  } catch (error) {
    send(response, 400, { error: (error as Error).message });
  }
}).listen(port, "127.0.0.1", () => console.log(`citymaker game server on http://127.0.0.1:${port}`));
