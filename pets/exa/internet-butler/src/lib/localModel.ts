/**
 * On-device language model. Personal documents are read here and never leave the device.
 *
 * Backends, in order of preference:
 *  1. Gemma 4 E2B via LiteRT-LM JS on WebGPU (Google's open on-device model; ~2.3 GB
 *     download, cached by the browser). Qualifies for "Best Use of Gemma".
 *  2. Chrome's built-in Prompt API (Gemini Nano) with JSON-schema constrained output.
 *  3. None: deterministic extraction and templates, labelled OFFLINE_DETERMINISTIC.
 */

export const GEMMA_MODEL = "hf://litert-community/gemma-4-E2B-it-litert-lm";
const LITERT_CDN = "https://cdn.jsdelivr.net/npm/@litert-lm/core@0.19.0/+esm";

export type Backend = "gemma-litert" | "chrome-prompt-api" | "none";
export type ModelStatus = "idle" | "loading" | "ready" | "unavailable" | "error";

export interface LocalModelState {
  backend: Backend;
  status: ModelStatus;
  detail: string;
}

interface PromptSession {
  prompt(input: string, options?: { responseConstraint?: object }): Promise<string>;
}
interface LanguageModelStatic {
  availability(options?: object): Promise<"unavailable" | "downloadable" | "downloading" | "available">;
  create(options?: object): Promise<PromptSession>;
}
interface LiteRtMessage {
  content?: string | Array<{ type?: string; text?: string }>;
}
interface LiteRtConversation {
  sendMessage(message: string | { role: string; content: string }): Promise<LiteRtMessage>;
}
interface LiteRtEngine {
  createConversation(config?: object): Promise<LiteRtConversation>;
}

const LM_OPTIONS = {
  expectedInputs: [{ type: "text", languages: ["en"] }],
  expectedOutputs: [{ type: "text", languages: ["en"] }],
};

export class LocalModel {
  state: LocalModelState = { backend: "none", status: "idle", detail: "No on-device model loaded" };
  private engine?: LiteRtEngine;
  private session?: PromptSession;
  private listeners = new Set<() => void>();

  onChange(fn: () => void) {
    this.listeners.add(fn);
  }

  private set(state: Partial<LocalModelState>) {
    this.state = { ...this.state, ...state };
    this.listeners.forEach((fn) => fn());
  }

  static capabilities() {
    const g = globalThis as unknown as { navigator?: { gpu?: unknown }; LanguageModel?: unknown };
    return { webgpu: !!g.navigator?.gpu, promptApi: typeof g.LanguageModel !== "undefined" };
  }

  get ready(): boolean {
    return this.state.status === "ready";
  }

  /** Must be called from a user gesture (both backends may start a large download). */
  async loadGemma(): Promise<void> {
    if (!LocalModel.capabilities().webgpu) {
      this.set({ backend: "gemma-litert", status: "unavailable", detail: "WebGPU is not available in this browser" });
      return;
    }
    this.set({ backend: "gemma-litert", status: "loading", detail: "Downloading Gemma 4 E2B (~2.3 GB, cached afterwards)…" });
    try {
      let mod: { Engine: { create(settings: object): Promise<LiteRtEngine> } };
      try {
        mod = (await import("@litert-lm/core")) as unknown as typeof mod;
      } catch {
        mod = (await import(/* @vite-ignore */ LITERT_CDN)) as typeof mod;
      }
      this.engine = await mod.Engine.create({ model: GEMMA_MODEL, mainExecutorSettings: { maxNumTokens: 8192 } });
      this.set({ status: "ready", detail: "Gemma 4 E2B running on this device (WebGPU)" });
    } catch (err) {
      this.set({ status: "error", detail: `Gemma failed to load: ${(err as Error).message}` });
    }
  }

  async loadPromptApi(): Promise<void> {
    const LM = (globalThis as unknown as { LanguageModel?: LanguageModelStatic }).LanguageModel;
    if (!LM) {
      this.set({ backend: "chrome-prompt-api", status: "unavailable", detail: "Chrome built-in Prompt API not present" });
      return;
    }
    this.set({ backend: "chrome-prompt-api", status: "loading", detail: "Preparing Chrome's on-device model…" });
    try {
      if ((await LM.availability(LM_OPTIONS)) === "unavailable") {
        this.set({ status: "unavailable", detail: "This device cannot run Chrome's on-device model" });
        return;
      }
      this.session = await LM.create(LM_OPTIONS);
      this.set({ status: "ready", detail: "Chrome built-in model (Gemini Nano) on this device" });
    } catch (err) {
      this.set({ status: "error", detail: `Prompt API failed: ${(err as Error).message}` });
    }
  }

  /** Ask for a JSON object. Returns null when no model is ready or the output does not parse. */
  async json<T>(system: string, prompt: string, schema: object): Promise<T | null> {
    if (!this.ready) return null;
    try {
      if (this.state.backend === "chrome-prompt-api" && this.session) {
        const out = await this.session.prompt(`${system}\n\n${prompt}`, { responseConstraint: schema });
        return JSON.parse(out) as T;
      }
      if (this.state.backend === "gemma-litert" && this.engine) {
        const chat = await this.engine.createConversation({
          preface: { messages: [{ role: "system", content: `${system}\nReply with one JSON object only, matching this JSON Schema:\n${JSON.stringify(schema)}` }] },
        });
        const msg = await chat.sendMessage(prompt);
        return extractJson<T>(messageText(msg));
      }
    } catch {
      return null;
    }
    return null;
  }
}

function messageText(m: LiteRtMessage): string {
  if (typeof m.content === "string") return m.content;
  return (m.content ?? []).map((p) => p.text ?? "").join("");
}

/** Parse the first balanced JSON object in a model reply (models sometimes add prose or fences). */
export function extractJson<T>(text: string): T | null {
  const start = text.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === "\\") i++;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth++;
    else if (ch === "}" && --depth === 0) {
      try {
        return JSON.parse(text.slice(start, i + 1)) as T;
      } catch {
        return null;
      }
    }
  }
  return null;
}
