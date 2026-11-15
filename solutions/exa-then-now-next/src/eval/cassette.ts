/**
 * Record/replay for evaluation runs (Node only).
 *
 * Every live call (Exa search, page fetch, typed judgment) is stored once in an append-only JSONL
 * cassette under the SHA-256 of its canonical request. Re-running an experiment replays the stored
 * responses: it costs nothing, needs no network, and gives identical numbers even for judges that
 * are not perfectly deterministic. Re-scoring with new code is then a replay, and only genuinely new
 * requests go to the network ("auto"), or fail loudly ("replay").
 *
 * A run manifest pins what produced a result: git commit and dirty flag, Node version, models,
 * the cassette's own digest, arguments and costs.
 */
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { gunzipSync, gzipSync } from "node:zlib";
import { execSync } from "node:child_process";
import { canonicalJson } from "../lib/council.ts";
import type { Assets, DecisionProvider, DecisionResult, Question } from "../decide/decide.ts";
import type { FetchFn, LaneResult, SearchFn } from "../warrant/lanes.ts";

export type CassetteMode = "record" | "replay" | "auto";

const sha = (s: string) => createHash("sha256").update(s).digest("hex");

export class Cassette {
  readonly path: string;
  readonly mode: CassetteMode;
  private entries = new Map<string, unknown>();
  hits = 0;
  misses = 0;

  constructor(path: string, mode: CassetteMode = "auto") {
    this.path = path;
    this.mode = mode;
    // A committed `<path>.gz` is unpacked on first use, so a fresh clone can replay without API keys.
    if (!existsSync(path) && existsSync(`${path}.gz`)) writeFileSync(path, gunzipSync(readFileSync(`${path}.gz`)));
    if (existsSync(path)) {
      for (const line of readFileSync(path, "utf8").split("\n")) {
        if (!line.trim()) continue;
        const e = JSON.parse(line) as { key: string; response: unknown };
        this.entries.set(e.key, e.response);
      }
    }
  }

  get size() {
    return this.entries.size;
  }

  /** Write `<path>.gz` (what gets committed; the raw JSONL stays local). */
  pack(): void {
    if (existsSync(this.path)) writeFileSync(`${this.path}.gz`, gzipSync(readFileSync(this.path), { level: 9 }));
  }

  /** Digest of the cassette file: pins exactly which recorded responses a result was computed from. */
  digest(): string {
    return existsSync(this.path) ? sha(readFileSync(this.path, "utf8")) : sha("");
  }

  async wrap<T>(kind: string, request: unknown, live: () => Promise<T>): Promise<T> {
    const key = sha(canonicalJson({ kind, request }));
    if (this.mode !== "record" && this.entries.has(key)) {
      this.hits++;
      return structuredClone(this.entries.get(key)) as T;
    }
    if (this.mode === "replay") throw new Error(`cassette miss (${kind}): not recorded in ${this.path}`);
    const response = await live();
    this.misses++;
    this.entries.set(key, response);
    appendFileSync(this.path, `${JSON.stringify({ key, kind, request, response, at: new Date().toISOString() })}\n`);
    return response;
  }

  search(fn: SearchFn): SearchFn {
    return (query, objective) => this.wrap<LaneResult[]>("exa.search", { query, objective }, () => fn(query, objective));
  }

  fetch(fn: FetchFn): FetchFn {
    return (url) => this.wrap<string>("exa.fetch", { url }, () => fn(url));
  }

  /** Judgments are keyed by provider, state, questions and image digests (the images are not stored). */
  decisions(p: DecisionProvider): DecisionProvider {
    return {
      id: p.id,
      decide: (state: unknown, questions: Question[], assets?: Assets) =>
        this.wrap<DecisionResult>(
          `decide.${p.id}`,
          { state, questions, assets: assets ? Object.fromEntries(Object.entries(assets).map(([k, a]) => [k, { format: a.format, sha256: sha(a.dataBase64) }])) : undefined },
          () => p.decide(state, questions, assets),
        ),
    };
  }
}

export interface RunManifest {
  name: string;
  started: string;
  ended: string;
  git: { commit: string; dirty: boolean };
  node: string;
  args: string[];
  models: Record<string, string>;
  cassette?: { path: string; digest: string; entries: number; hits: number; misses: number };
  costs?: Record<string, unknown>;
  outputs: string[];
}

export function gitState(cwd: string): RunManifest["git"] {
  const run = (c: string) => {
    try {
      return execSync(c, { cwd, encoding: "utf8" }).trim();
    } catch {
      return "";
    }
  };
  return { commit: run("git rev-parse HEAD") || "unknown", dirty: run("git status --porcelain") !== "" };
}

export function writeManifest(path: string, m: RunManifest): void {
  writeFileSync(path, `${JSON.stringify(m, null, 2)}\n`);
}
