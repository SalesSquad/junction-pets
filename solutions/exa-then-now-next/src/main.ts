import { approveAction, rejectAction, runErrand, type ButlerRun } from "./lib/butler.ts";
import { Council, type Receipt } from "./lib/council.ts";
import { createEgress, relayHealth, type RelayHealth } from "./lib/egress.ts";
import { SYNTHETIC_DOCUMENT, SYNTHETIC_ERRAND } from "./lib/fixtures.ts";
import { LocalModel } from "./lib/localModel.ts";
import { openLocalStores, wipeLocalData } from "./lib/store.ts";
import type { Capability, GrantMode, Provenance, TimelineEvent } from "./lib/types.ts";
import { embedded } from "./ui/embed.ts";
import { mountThenNow } from "./ui/thenNow.ts";

// Inside the Chibi.pet app view the host shows the name: the page drops its own title and tightens (styles.css).
if (embedded) document.documentElement.classList.add("embed");

const ttRoot = document.querySelector<HTMLElement>("#tt");
if (ttRoot) mountThenNow(ttRoot);

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
const pct = (x?: number) => (x === undefined ? "–" : x.toFixed(2));
const badge = (p: Provenance) => `<span class="prov prov-${p.toLowerCase()}" title="How this was produced">${p.replace("_", " ")}</span>`;

const CAPABILITIES: Array<{ id: Capability; label: string; egress: boolean }> = [
  { id: "exa.search", label: "Search the web (Exa)", egress: true },
  { id: "exa.contents", label: "Read web pages (Exa)", egress: true },
  { id: "typesafe.judge", label: "Judgments (TypeSafe Jev)", egress: true },
  { id: "writer.hosted", label: "Hosted writer (NVIDIA Nemotron): question and public sources only", egress: true },
  { id: "action.send", label: "Send on my behalf", egress: false },
];

interface UiState {
  health: RelayHealth;
  timeline: TimelineEvent[];
  run?: ButlerRun;
  busy: boolean;
  chain: string;
  notice?: { kind: "ok" | "blocked" | "info"; text: string };
  persistent: boolean;
}

async function main() {
  const root = document.querySelector<HTMLDivElement>("#app")!;
  const { councilStore, outcomes, persistent } = await openLocalStores();
  const council = new Council(councilStore);
  await council.init();
  const model = new LocalModel();
  const egress = createEgress(council);
  const state: UiState = { health: await relayHealth(), timeline: [], busy: false, chain: "checking…", persistent };

  const verify = async () => {
    const broken = await council.verifyChain();
    state.chain = broken === null ? `intact · ${council.getReceipts().length} receipts` : `BROKEN at #${broken}`;
    render();
  };
  council.onChange(() => void verify());
  model.onChange(() => render());

  function render() {
    const caps = LocalModel.capabilities();
    const run = state.run;
    const receipts = [...council.getReceipts()].reverse();
    const egressReceipts = council.getReceipts().filter((r) => r.kind === "allowed");
    const sentBytes = egressReceipts.reduce((n, r) => n + (r.bytes ?? 0), 0);
    root.innerHTML = `
      <header>
        <div>
          <h1>Internet Butler</h1>
          <p class="tag">Local-first. Your documents stay on this device; only the questions leave it, and only with your permission.</p>
        </div>
        <div class="status">
          <span class="pill ${state.health.exa ? "on" : "off"}">Exa ${state.health.exa ? (state.health.exaMode === "mcp-keyless" ? "live · keyless MCP" : "live · API") : "not configured"}</span>
          <span class="pill ${state.health.typesafe ? "on" : "off"}">TypeSafe ${state.health.typesafe ? esc(state.health.model) : "not configured"}</span>
          <span class="pill ${model.ready ? "on" : "off"}" title="${esc(model.state.detail)}">On-device: ${esc(model.state.backend === "none" ? "none" : model.state.backend)} · ${esc(model.state.status)}</span>
        </div>
      </header>
      <main>
        <section class="col">
          <h2>Errand</h2>
          <textarea id="errand" rows="4" placeholder="e.g. My flight Helsinki → Berlin landed 4 hours late. Can I get money back?">${esc((document.querySelector("#errand") as HTMLTextAreaElement | null)?.value ?? "")}</textarea>
          <details ${((document.querySelector("#doc") as HTMLTextAreaElement | null)?.value ?? "") ? "open" : ""}>
            <summary>Add a document (stays on this device)</summary>
            <textarea id="doc" rows="6" placeholder="Paste a lease, booking confirmation, letter…">${esc((document.querySelector("#doc") as HTMLTextAreaElement | null)?.value ?? "")}</textarea>
          </details>
          <div class="row">
            <button id="run" class="primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Working…" : "Take care of it"}</button>
            <button id="demo" ${state.busy ? "disabled" : ""}>Load synthetic demo</button>
          </div>
          <div class="model">
            <h3>On-device model</h3>
            <p class="muted">${esc(model.state.detail)}</p>
            <div class="row">
              <button id="gemma" ${!caps.webgpu || model.state.status === "loading" ? "disabled" : ""}>Load Gemma 4 E2B (~2.3 GB)</button>
              <button id="nano" ${!caps.promptApi || model.state.status === "loading" ? "disabled" : ""}>Use Chrome built-in model</button>
            </div>
            <p class="muted small">WebGPU ${caps.webgpu ? "available" : "missing"} · Prompt API ${caps.promptApi ? "available" : "missing"}. Without a model the butler uses deterministic extraction and templates.</p>
          </div>
          <h3>Timeline</h3>
          <ol class="timeline">${state.timeline
            .map((e) => `<li class="ev ev-${e.status}"><b>${esc(e.step)}</b> ${badge(e.provenance)}<div>${esc(e.detail)}</div></li>`)
            .join("") || '<li class="muted">Nothing yet.</li>'}</ol>
        </section>

        <section class="col wide">
          ${state.notice ? `<div class="notice notice-${state.notice.kind}">${esc(state.notice.text)}</div>` : ""}
          ${run?.stoppedReason ? `<div class="notice notice-blocked">${esc(run.stoppedReason)}</div>` : ""}
          ${run?.draft ? renderDraft(run) : '<p class="muted">Describe an errand. The butler finds current sources, checks them, drafts the next step and waits for your approval.</p>'}
          ${run?.evidence.length ? `<h2>Sources</h2>${run.evidence.map((e, i) => `
            <article class="card">
              <div class="card-h"><span class="n">${i + 1}</span><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a> ${badge(e.provenance)}</div>
              <div class="muted small">${esc(e.domain)}${e.publishedDate ? ` · ${esc(e.publishedDate.slice(0, 10))}` : ""}</div>
              ${e.highlights.map((h) => `<blockquote>${esc(h)}</blockquote>`).join("")}
              <div class="scores small">usable ${pct(e.judgment?.usable)} · authoritative ${pct(e.judgment?.primary)} · new info ${pct(e.judgment?.novel)} · injection ${pct(e.judgment?.injection)} ${e.judgment ? badge(e.judgment.provenance) : ""}</div>
            </article>`).join("")}` : ""}
          ${run?.dropped.length ? `<details><summary>${run.dropped.length} source(s) dropped</summary>${run.dropped.map((d) => `<div class="small"><a href="${esc(d.evidence.url)}" target="_blank" rel="noopener noreferrer">${esc(d.evidence.domain)}</a>: ${esc(d.reason)}</div>`).join("")}</details>` : ""}
        </section>

        <section class="col">
          <h2>Permission council</h2>
          <p class="muted small">Every outbound call and action passes here. Revoke a grant and the next call is blocked, with a receipt.</p>
          ${CAPABILITIES.map((c) => `
            <label class="grant">
              <span>${esc(c.label)}</span>
              <select data-cap="${c.id}">
                ${(["allow", "ask", "deny"] as GrantMode[]).map((m) => `<option value="${m}" ${council.getGrants()[c.id] === m ? "selected" : ""} ${c.egress && m === "ask" ? "disabled" : ""}>${m}</option>`).join("")}
              </select>
            </label>`).join("")}
          <p class="small">Receipt chain: <b class="${state.chain.startsWith("BROKEN") ? "bad" : "good"}">${esc(state.chain)}</b>${state.persistent ? "" : " (memory only)"}</p>
          <h3>What left this device</h3>
          <p class="small">${egressReceipts.length} calls · ${sentBytes.toLocaleString()} bytes · field names below, values never stored.</p>
          <ol class="receipts">${receipts.slice(0, 40).map(renderReceipt).join("")}</ol>
          <button id="wipe" class="link">Delete all local data</button>
        </section>
      </main>`;
    bind();
  }

  function renderDraft(run: ButlerRun) {
    const d = run.draft!;
    const idx = new Map(run.evidence.map((e, i) => [e.id, i + 1]));
    return `
      <h2>Draft ${badge(d.provenance)}</h2>
      <p>${esc(d.summary)}</p>
      <ul class="claims">${d.claims
        .map((c) => `<li class="claim v-${c.verdict}"><span>${esc(c.text)}</span> <sup>[${idx.get(c.sourceId) ?? "?"}]</sup>
          <span class="verdict" title="Citation check">${esc(c.verdict ?? "unchecked")}${c.probability !== undefined ? ` ${pct(c.probability)}` : ""}${c.needsReview ? " · review" : ""}</span></li>`)
        .join("")}</ul>
      <div class="action">
        <h3>Next step: message</h3>
        <label>To <input id="to" value="${esc(d.action.to ?? "")}" placeholder="recipient@example.com" /></label>
        <label>Subject <input id="subject" value="${esc(d.action.subject ?? "")}" /></label>
        <textarea id="body" rows="10">${esc(d.action.body)}</textarea>
        ${run.risk ? `<p class="small">Side effect ${pct(run.risk.sideEffect)} · hard to undo ${pct(run.risk.blastRadius)}/3 ${badge(run.risk.provenance)} — informative only; sending always needs your click.</p>` : ""}
        <div class="row">
          <button id="approve" class="primary">Approve and send</button>
          <button id="reject">Reject</button>
        </div>
      </div>`;
  }

  function renderReceipt(r: Receipt) {
    return `<li class="rc rc-${r.kind}"><b>#${r.seq} ${esc(r.kind)}</b> <code>${esc(r.capability)}</code><div class="small">${esc(r.subject)}${r.fields?.length ? ` · fields: ${esc(r.fields.join(", "))}` : ""}${r.bytes ? ` · ${r.bytes} B` : ""}</div><div class="hash small">${esc(r.hash.slice(0, 16))}…</div></li>`;
  }

  function bind() {
    root.querySelector("#run")?.addEventListener("click", () => void go());
    root.querySelector("#demo")?.addEventListener("click", () => {
      (root.querySelector("#errand") as HTMLTextAreaElement).value = SYNTHETIC_ERRAND;
      (root.querySelector("#doc") as HTMLTextAreaElement).value = SYNTHETIC_DOCUMENT;
      root.querySelector("details")?.setAttribute("open", "");
    });
    root.querySelector("#gemma")?.addEventListener("click", () => void model.loadGemma());
    root.querySelector("#nano")?.addEventListener("click", () => void model.loadPromptApi());
    root.querySelectorAll<HTMLSelectElement>("select[data-cap]").forEach((s) =>
      s.addEventListener("change", async () => {
        const r = await council.setGrant(s.dataset.cap as Capability, s.value as GrantMode);
        state.notice = { kind: "info", text: `${s.dataset.cap} set to ${s.value} (receipt #${r.seq}).` };
        render();
      }),
    );
    // Keep the user's edits to the message across re-renders: what they approve is what is sent.
    for (const [id, key] of [["#to", "to"], ["#subject", "subject"], ["#body", "body"]] as const) {
      root.querySelector<HTMLInputElement | HTMLTextAreaElement>(id)?.addEventListener("input", (ev) => {
        const action = state.run?.draft?.action;
        if (!action) return;
        const value = (ev.target as HTMLInputElement).value;
        if (key === "to") action.to = value.trim() || undefined;
        else action[key] = value;
      });
    }
    root.querySelector("#approve")?.addEventListener("click", () => void approve());
    root.querySelector("#reject")?.addEventListener("click", async () => {
      if (!state.run) return;
      const r = await rejectAction({ council, outcomes }, state.run);
      state.notice = { kind: "info", text: `Rejected (receipt #${r.seq}). The cited sources get a small penalty in future rankings on this device.` };
      render();
    });
    root.querySelector("#wipe")?.addEventListener("click", async () => {
      if (!confirm("Delete grants, receipts and learned source preferences from this browser?")) return;
      await wipeLocalData();
      location.reload();
    });
  }

  async function go() {
    const errand = (root.querySelector("#errand") as HTMLTextAreaElement).value.trim();
    const doc = (root.querySelector("#doc") as HTMLTextAreaElement).value;
    if (!errand) return;
    state.busy = true;
    state.timeline = [];
    state.run = undefined;
    state.notice = undefined;
    state.health = await relayHealth();
    render();
    try {
      state.run = await runErrand({ council, egress, model, health: state.health, outcomes, emit: (e) => { state.timeline.push(e); render(); } }, errand, doc);
    } catch (err) {
      state.notice = { kind: "blocked", text: (err as Error).message };
    } finally {
      state.busy = false;
      render();
    }
  }

  async function approve() {
    const run = state.run;
    if (!run?.draft) return;
    const result = await approveAction({ council, outcomes }, run);
    if (!result.allowed) {
      state.notice = { kind: "blocked", text: `Blocked: "Send on my behalf" is revoked (receipt #${result.receipt.seq}). Nothing was sent.` };
      render();
      return;
    }
    state.notice = { kind: "ok", text: `Approved (receipt #${result.receipt.seq}). Opening your mail app with the message; you press send there.` };
    render();
    if (result.mailto) window.location.href = result.mailto;
  }

  await verify();
  render();
}

void main();
