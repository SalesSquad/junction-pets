/**
 * Then · Now · Next panel: the law on the day it mattered, the law today, what changed it and what is
 * coming; a claim the person approves on this device; and the receiver's view, which re-fetches the
 * pinned official version and verifies by code.
 */
import type { ThenNowNext } from "../timetravel/timetravel.ts";
import { asTwoLane } from "../timetravel/timetravel.ts";
import { buildArtifact, generateDeviceKey, verifyArtifact, type WarrantArtifact } from "../warrant/artifact.ts";
import { Authority, type AgentGrant, type Authorization, type Proposal } from "../authority/authority.ts";
import { dictate, monthDate, relativeDate, speak, spokenDate, stopSpeaking, voiceSupport, VOICE_LANGS } from "./voice.ts";
import { copyText, dictationNote } from "./embed.ts";
import { icsEvent, lastDay, timeVerdict } from "../timetravel/verdict.ts";

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
const today = () => new Date().toISOString().slice(0, 10);
/** Links come from search results and official feeds: only http(s) may reach an href. */
const safeUrl = (u: unknown) => (/^https?:\/\//i.test(String(u ?? "")) ? String(u) : "#");

const EXAMPLES: Array<{ label: string; question: string; date: string }> = [
  { label: "US · bumped flight 2021", question: "I was bumped from an oversold US domestic flight on 2021-06-10 and the substitute flight got me there 3 hours late. How much denied boarding compensation am I owed?", date: "2021-06-10" },
  { label: "UK · minimum wage 2023", question: "I am 30 and worked in the UK in June 2023 for £10.00 an hour. What was the national living wage per hour then, and was I underpaid?", date: "2023-06-15" },
  { label: "EU · cancelled flight 2019", question: "My EU flight of 1,200 km was cancelled on 2019-03-01 without notice. How much compensation is owed under EU261?", date: "2019-03-01" },
];

interface Claim {
  recipient: string;
  letter: string;
  artifact?: WarrantArtifact;
  grant?: AgentGrant;
  proposal?: Proposal;
  approval?: Authorization;
  sent?: { status: string; reference?: string };
  receiver?: { decision: string; reasons: string[]; checked: string[] };
  dateBlind?: { decision: string; reasons: string[] };
  ledger: string[];
}
interface State {
  question: string;
  date: string;
  busy: boolean;
  error?: string;
  result?: ThenNowNext & { judge?: string; judges?: string[] };
  /** The person has read the quoted clause after the judges disagreed. */
  reviewed?: boolean;
  /** Announced, not-yet-in-force changes found on government sites (Exa). `undefined` = not searched yet. */
  announced?: Array<{ url: string; title: string; published?: string; effective: string; quote: string; amount?: { text: string }; amountFrom?: "quote" | "title" }>;
  announcedBusy?: boolean;
  announcedNote?: string;
  announcedError?: string;
  /** The claim's recipient as typed; kept in state because every render rebuilds the form. */
  recipient?: string;
  /** Voice: dictation in progress, its language, and a note (an error, or where the audio goes). */
  listening?: boolean;
  voiceLang: string;
  voiceNote?: string;
  /** Private mode: the situation goes to no hosted service; the on-device judge decides and the person reviews. */
  privateMode: boolean;
  /** The on-device judge, if the relay has one (from /api/health). */
  onDevice?: { id: string; role: string };
  /** Read the answer aloud when it arrives (set by the deep link `say=1`). */
  sayResult?: boolean;
  /** Rights search on the device (semantic catalog): the query, its hits, and a provision the person picked. */
  hasCatalog?: boolean;
  lookup: { q: string; busy?: boolean; error?: string; hits?: Array<{ kind?: string; ref: unknown; title: string; about: string; score: number }> };
  pinned?: { ref: unknown; title: string };
  /** Next steps found on the live web with Exa: where to send the claim, the time limit, what was reported that day. */
  steps?: { counterparty?: string; planned?: string; steps: Array<{ kind: "where" | "deadline" | "day"; need: string; title: string; url: string; published?: string; quote: string }> };
  stepsBusy?: boolean;
  stepsError?: string;
  /** The question is outside the dated-law engine and was handed to the general Butler (live web) below. */
  handedOff?: string;
  /** The person set the date field by hand: dates in the message no longer overwrite it. */
  dateTouched?: boolean;
  /** What has been collected for the agent to retrieve from (relay /api/knowledge). */
  knowledge?: { agent: string; collected: Array<{ id: string; title: string; count: number; unit: string; detail: string; running?: boolean; items?: Array<{ title: string; jurisdiction: string }> }>; live: Array<{ title: string; detail: string }> };
  claim?: Claim;
  radar: { watches: Array<{ label: string; ref: unknown; since: string }>; results?: Array<{ label: string; changes?: Array<{ effective: string; title: string }>; upcoming?: Array<{ effective: string; title: string }>; error?: string }>; note?: string; alerts: string[] };
}

const authority = new Authority();
let device: Awaited<ReturnType<typeof generateDeviceKey>> | undefined;
const loadWatches = () => { try { return JSON.parse(localStorage.getItem("ttn.watches") ?? "[]"); } catch { return []; } };
const saveWatches = (w: unknown) => { try { localStorage.setItem("ttn.watches", JSON.stringify(w)); } catch { /* private mode */ } };

const post = async (path: string, body: unknown) => {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error ?? `${path} ${r.status}`);
  return j;
};
const officialText = async (url: string) => (await post("/api/official", { url })).text as string;
const defaultRecipient = (title: string) =>
  /flight|boarding|air/i.test(title) ? "claims@airline.example" : /wage|pay|employment|redundan/i.test(title) ? "payroll@employer.example" : /gdpr|data/i.test(title) ? "privacy@controller.example" : /credit card|fee/i.test(title) ? "disputes@card-issuer.example" : "claims@recipient.example";

function letterFor(r: ThenNowNext, recipient: string): string {
  return [
    `To: ${recipient}`,
    `Subject: Claim under ${r.provision.title} — event on ${r.eventDate}`,
    "",
    `On ${r.eventDate}: ${r.question}`,
    "",
    `Under ${r.provision.title}, as in force on ${r.eventDate}: "${r.evidence.quote}"`,
    `Official text as of that date: ${r.evidence.url}`,
    "",
    `I therefore claim the compensation set there${r.then.amount ? (/whichever is lower|up to|not (to )?exceed|maximum|at most/i.test(r.evidence.quote) ? `, up to ${r.then.amount.text}` : `: ${r.then.amount.text}`) : ""}${r.changed && r.now.amount ? ` (the figure today, ${r.now.amount.text}, does not apply to an event on ${r.eventDate})` : ""}.`,
    "",
    "A signed Warrant is attached: it lets you verify the cited text automatically against the official version as of that date.",
  ].join("\n");
}

export function mountThenNow(root: HTMLElement): void {
  const navLang = typeof navigator !== "undefined" ? navigator.language : "en-US";
  const state: State = { question: EXAMPLES[0]!.question, date: EXAMPLES[0]!.date, busy: false, radar: { watches: loadWatches(), alerts: [] }, voiceLang: VOICE_LANGS.find((l) => l.code.slice(0, 2) === navLang.slice(0, 2))?.code ?? "en-US", privateMode: false, lookup: { q: "" } };
  const support = voiceSupport();
  let stopDictation: (() => void) | undefined;

  /** What is said aloud: the answer in two or three sentences, with the caveat when the judges did not agree. */
  function spokenSummary(r: NonNullable<State["result"]>): string {
    const short = r.provision.title.split(" — ")[0];
    const parts = [`On ${r.then.date}, under ${short}, the amount was ${r.then.amount?.text ?? "not stated as a figure"}.`];
    parts.push(r.changed ? `Today it is ${r.now.amount?.text ?? "different"}, so an answer from today's text would be wrong for that date.` : "It has not changed since.");
    if (r.agreement && !r.agreement.agreed) parts.push(r.agreement.note === "on-device judge only" ? "This was decided on this device only, so please read the quoted clause." : "The judges did not all agree, so please read the quoted clause.");
    const next = state.announced?.[0];
    if (next) parts.push(`Announced, but not law yet: ${next.amount ? `${next.amount.text} ` : "a change "}from ${next.effective}.`);
    return parts.join(" ");
  }

  /** The counterparty's own claim page, when Exa found one: the claim's real recipient. */
  const whereUrl = () => state.steps?.steps.find((x) => x.kind === "where")?.url;

  /** Search the on-device catalog by meaning. The query stays on this machine. */
  async function lookup() {
    const q = state.lookup.q.trim() || state.question.trim();
    if (q.length < 2) return;
    state.lookup = { q: state.lookup.q, busy: true };
    render();
    try {
      state.lookup = { q: state.lookup.q, hits: (await post("/api/catalog/search", { query: q, date: state.date })).hits ?? [] };
    } catch (e) {
      state.lookup = { q: state.lookup.q, error: String((e as Error).message).slice(0, 120) };
    }
    render();
  }

  function toggleDictation() {
    if (state.listening) {
      stopDictation?.();
      return;
    }
    const before = state.question.trim() === EXAMPLES.find((e) => e.question === state.question)?.question ? "" : state.question.trim();
    state.listening = true;
    state.voiceNote = undefined;
    render();
    stopDictation = dictate(
      state.voiceLang,
      (final, interim) => {
        // Update the box in place: re-rendering on every interim result would fight the person's cursor.
        state.question = [before, final, interim].filter(Boolean).join(" ");
        const box = root.querySelector<HTMLTextAreaElement>("#tt-q");
        if (box) box.value = state.question;
      },
      (error) => {
        state.listening = false;
        state.voiceNote = dictationNote(error);
        const said = spokenDate(state.question) ?? monthDate(state.question) ?? relativeDate(state.question, today());
        if (said) state.date = said;
        render();
      },
    );
  }

  async function run() {
    state.busy = true;
    state.error = undefined;
    state.result = undefined;
    state.claim = undefined;
    state.reviewed = false;
    state.announced = undefined;
    state.announcedBusy = false;
    state.announcedNote = undefined;
    state.announcedError = undefined;
    state.recipient = undefined;
    state.steps = undefined;
    state.stepsBusy = false;
    state.stepsError = undefined;
    state.handedOff = undefined;
    render();
    try {
      state.result = await post("/api/timetravel", { question: state.question, eventDate: state.date, ...(state.privateMode ? { private: true } : {}), ...(state.pinned ? { ref: state.pinned.ref, title: state.pinned.title } : {}) });
    } catch (e) {
      state.error = (e as Error).message;
    }
    state.busy = false;
    render();
    if (state.sayResult && state.result) speak(spokenSummary(state.result));
    state.sayResult = false;
    // What is still missing to act (where to send it, the time limit, what was reported that day): Exa, right away.
    // Not in private mode: there the question is sent nowhere unless the person asks for it.
    if (state.result && !state.privateMode) void workOutSteps();
    // Outside the dated-law engine (no official provision, or none in force then): the general Butler takes it
    // from the live web. In private mode the person decides.
    if (!state.result && state.error && /no official provision|not in force|no (amount-bearing|time-limit) clause|was not in force/i.test(state.error) && !state.privateMode) handOff();
  }

  /** Pass the question to the general Butler below (live Exa search, judged sources, a drafted next step). */
  function handOff() {
    const box = document.querySelector<HTMLTextAreaElement>("#errand"), go = document.querySelector<HTMLButtonElement>("#run");
    if (!box || !go) return;
    box.value = `${state.question}${/\d{4}-\d{2}-\d{2}/.test(state.question) ? "" : ` (It happened on ${state.date}.)`}`;
    state.handedOff = "No dated official text covers this, so the Butler below is answering it from the live web with Exa.";
    render();
    go.click();
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function workOutSteps() {
    const r = state.result;
    if (!r) return;
    state.stepsBusy = true;
    state.stepsError = undefined;
    render();
    let found: State["steps"], error: string | undefined;
    try {
      found = await post("/api/next-steps", { question: r.question, eventDate: r.eventDate, right: r.provision.title });
    } catch (e) {
      error = String((e as Error).message).slice(0, 120);
    }
    if (state.result !== r) return; // a newer run owns the card
    state.steps = found;
    state.stepsError = error;
    state.stepsBusy = false;
    render();
  }

  async function prepare() {
    const r = state.result!;
    const recipient = state.recipient?.trim() || whereUrl() || defaultRecipient(r.provision.title);
    device ??= await generateDeviceKey();
    const receiver = recipient.split("@").at(-1)!;
    const jti = `mandate-${Date.now()}`;
    const mandate = { subject: "person-local", recipient: receiver, purpose: `One claim: ${r.provision.title}, event ${r.eventDate}`, notBefore: new Date(Date.now() - 60_000).toISOString(), expiresAt: new Date(Date.now() + 30 * 864e5).toISOString(), jti };
    const artifact = await buildArtifact(asTwoLane(r), mandate, device, new Date(), { name: "internet-butler-warrant", version: "0.2.0", commit: "browser", dirty: true });
    const grant: AgentGrant = { jti, principal: "person-local", authorization_details: [{ type: "warrant_claim", actions: ["claim.propose", "claim.approve", "claim.execute"], locations: [receiver], purpose: mandate.purpose }], notBefore: mandate.notBefore, expiresAt: mandate.expiresAt, limits: { maxExecutions: 1 } } as AgentGrant;
    const { proposal } = await authority.propose(grant, { id: `claim-${jti}`, version: 1, receiver, body: artifact, createdAt: new Date().toISOString(), expiresAt: mandate.expiresAt } as Proposal);
    state.claim = { recipient, letter: letterFor(r, recipient), artifact, grant, proposal, ledger: authority.ledger().map((x) => x.kind) };
    render();
  }

  async function approveAndSend() {
    const c = state.claim!;
    c.approval = await authority.approve(c.grant!, c.proposal!, device!, true);
    const attempt = await authority.execute(c.grant!, c.proposal!, c.approval, `idem-${c.proposal!.id}`, async (p) => {
      // The receiver: re-fetch the pinned official version and verify by code.
      const d = await verifyArtifact(p.body as WarrantArtifact, { recipient: p.receiver, revoked: new Set(), fetch: officialText });
      c.receiver = d;
      return { status: d.decision === "ACCEPT" ? "accepted" : "rejected", reference: d.decision === "ACCEPT" ? `CASE-${Date.now().toString(36).toUpperCase()}` : undefined };
    });
    c.sent = { status: attempt.status, reference: attempt.receiverReference };
    c.ledger = authority.ledger().map((x) => x.kind);
    render();
  }

  async function dateBlindReceiver() {
    // What a receiver would conclude if it read today's page instead of the pinned version.
    const c = state.claim!;
    const nowUrl = state.result!.now.url;
    const d = await verifyArtifact(c.artifact!, { recipient: c.proposal!.receiver, revoked: new Set(), fetch: async () => officialText(nowUrl) });
    c.dateBlind = d;
    render();
  }

  async function announced() {
    const r = state.result!;
    state.announcedBusy = true;
    state.announcedError = undefined;
    render();
    let list: State["announced"], note: string | undefined, error: string | undefined;
    try {
      const a = await post("/api/announced", { title: r.provision.title, ref: r.provision.ref });
      list = a.announced ?? [];
      note = `${(a.searched ?? []).slice(0, 3).join(", ")}${a.incomplete ? " (one search failed, so this may be incomplete)" : ""}`;
    } catch (err) {
      // A failed search is not "nothing found".
      error = String((err as Error).message).slice(0, 120);
    }
    if (state.result !== r) return; // a newer run owns the card
    state.announced = list;
    state.announcedNote = note;
    state.announcedError = error;
    state.announcedBusy = false;
    render();
  }

  function watch() {
    const r = state.result!;
    state.radar.watches = [...state.radar.watches.filter((w) => JSON.stringify(w.ref) !== JSON.stringify(r.provision.ref)), { label: r.provision.title, ref: r.provision.ref, since: today() }];
    saveWatches(state.radar.watches);
    render();
  }
  async function checkRadar(since?: string) {
    try {
      const watches = state.radar.watches.map((w) => ({ ...w, since: since ?? w.since }));
      state.radar.results = (await post("/api/radar/check", { watches })).results;
      state.radar.note = undefined;
    } catch (e) {
      state.radar.note = (e as Error).message;
    }
    render();
  }
  async function monitor() {
    try {
      const m = await post("/api/radar/monitor", { topic: state.result?.provision.title ?? state.radar.watches[0]?.label ?? "consumer rights amounts" });
      state.radar.note = `Exa Monitor ${m.id} created; deliveries are verified with its signing secret.`;
    } catch (e) {
      const msg = (e as Error).message;
      // On localhost there is no public address for Exa to push to: say what works here instead of an error.
      state.radar.note = /webhook/i.test(msg)
        ? "An Exa Monitor pushes changes to a public webhook, and this demo runs on localhost. Here, use Check now or Search announced changes (both ask Exa on demand); with EXA_WEBHOOK_URL set, signed deliveries arrive in this panel live."
        : `Exa Monitor not created: ${msg}`;
    }
    render();
  }

  try {
    const es = new EventSource("/api/events");
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        state.radar.alerts = [`${d.at?.slice(11, 19) ?? ""} monitor delivery (${d.verified ? "signature verified" : "unsigned"})`, ...state.radar.alerts].slice(0, 5);
        void checkRadar();
      } catch { /* ignore */ }
    };
  } catch { /* no SSE */ }

  function moment(label: string, m: ThenNowNext["then"], extra = "") {
    return `<div class="tt-moment"><div class="tt-label">${label} · ${esc(m.date)}</div><div class="tt-amount">${esc(m.amount?.text ?? "—")}</div>${extra}<a class="small" href="${esc(safeUrl(m.url))}" target="_blank" rel="noreferrer">official text as of ${esc(m.date)}</a></div>`;
  }

  /** The clause choice is not unanimous (or a judge did not answer): the person reviews the clause before a claim is prepared. */
  const split = (r: NonNullable<State["result"]>) => !!r.agreement && !r.agreement.agreed;
  function agreementChip(r: NonNullable<State["result"]>) {
    const a = r.agreement;
    if (!a) return "";
    const n = a.votes.length;
    // The on-device judge as an advisor: shown next to the panel, never counted in it.
    const adv = (a.advisory ?? []).map((v) => `<span class="tt-chip ${v.index === a.votes[0]?.index ? "tt-ok" : "tt-warn"}">on-device Gemma ${v.index === a.votes[0]?.index ? "agrees" : "differs"} (not counted)</span>`).join("");
    if (a.agreed) return `<span class="tt-chip tt-ok">${n === 1 ? "1 judge" : `all ${n} judges agree`}${r.ruledOut ? ` · ${r.ruledOut} tier(s) ruled out by code` : ""}</span>${adv}`;
    const same = a.votes.filter((v) => v.index === a.votes[0]?.index).length;
    const why = a.note === "on-device judge only" ? "decided on this device only" : a.abstained.length ? `${a.abstained.join(", ")} did not answer` : same === n ? "the judges are unsure" : "the judges picked different clauses";
    return `<span class="tt-chip tt-warn">review needed: ${esc(why)}</span>${adv}`;
  }

  /** Who did what, in one line: the partner agents the butler asked, what code did, and what waits for the person. */
  function trace(r: NonNullable<State["result"]>): string {
    const names: Record<string, string> = { "typesafe-jev": "TypeSafe Jev", "openai-decisions": "OpenAI Luna", "nemotron-3.5-super-vl": "NVIDIA Nemotron", "gemma-on-device": "Google Gemma (on this device)" };
    const via: Record<string, string> = { exa: "Exa found the provision", registry: "built-in right matched", catalog: "EmbeddingGemma catalog found the provision (on this device)", "ecfr-search": "eCFR search found the provision", given: "provision picked by you" };
    const src = /ecfr\.gov/.test(r.then.url) ? "eCFR" : /legislation\.gov\.uk/.test(r.then.url) ? "legislation.gov.uk" : /europa\.eu/.test(r.then.url) ? "EUR-Lex" : "official source";
    const voters = (r.judges ?? []).map((j) => names[j] ?? j);
    const parts = [
      via[r.provision.via] ?? r.provision.via,
      `${src}: the text as of ${r.then.date}`,
      `code: ${[r.computed ? "computed the distance" : "", r.ruledOut ? `ruled out ${r.ruledOut} tier(s)` : "read the outline"].filter(Boolean).join(", ")}`,
      `${voters.join(", ")} ${voters.length > 1 ? "voted" : "decided"}`,
      ...((r.agreement?.advisory?.length ?? 0) > 0 ? ["Google Gemma advised from this device"] : []),
      ...(state.steps ? ["Exa found the next steps"] : state.stepsBusy ? ["Exa is finding the next steps"] : []),
      ...(state.announced?.length ? ["Exa found an announced change"] : []),
      "you approve",
    ];
    return `<div class="tt-trace small">${parts.map((x) => `<span>${esc(x)}</span>`).join('<span class="tt-arrow">→</span>')}</div>`;
  }

  function render() {
    const r = state.result;
    const c = state.claim;
    root.innerHTML = `
      <section class="tt">
        <div class="tt-head">
          <div><h2>Then · Now · Next</h2><p class="muted small">Your rights depend on the law on the day it happened. Answers come from the official text as of that date — pinned, so anyone can re-check it.</p></div>
          <div class="row">${EXAMPLES.map((e, i) => `<button data-ex="${i}">${esc(e.label)}</button>`).join("")}</div>
        </div>
        <div class="tt-form">
          <textarea id="tt-q" rows="3">${esc(state.question)}</textarea>
          <label>Date of the event <input id="tt-date" type="date" value="${esc(state.date)}" /></label>
          <button id="tt-run" class="primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Reading the law as it was…" : "Find the law on that date"}</button>
        </div>
        <div class="row tt-voice">
          ${support.dictate ? `<button id="tt-mic" class="${state.listening ? "tt-live" : ""}" aria-pressed="${state.listening ? "true" : "false"}">${state.listening ? "Stop dictation" : "Dictate"}</button><select id="tt-lang" aria-label="Dictation language">${VOICE_LANGS.map((l) => `<option value="${l.code}" ${l.code === state.voiceLang ? "selected" : ""}>${esc(l.label)}</option>`).join("")}</select>` : `<span class="small muted">Dictation is not available in this browser.</span>`}
          ${state.onDevice ? `<label class="small"><input id="tt-private" type="checkbox" ${state.privateMode ? "checked" : ""} /> Keep my situation on this device (Gemma decides; only the public law is fetched)</label>` : ""}
        </div>
        ${support.dictate ? `<p class="small muted">${state.voiceNote ? `<span class="tt-bad">${esc(state.voiceNote)}</span> · ` : ""}Dictation uses this browser's speech service: the audio goes to the browser vendor (Google in Chrome, Apple in Safari) only while you dictate. A full date said aloud fills the date field.</p>` : ""}
        ${state.hasCatalog ? `<div class="tt-lookup">
          <div class="row"><input id="tt-lookup-q" placeholder="Find a right by meaning, in any language (searched on this device) — empty: use the situation above" value="${esc(state.lookup.q)}" /><button id="tt-lookup-go" ${state.lookup.busy ? "disabled" : ""}>${state.lookup.busy ? "Searching…" : "Search rights"}</button></div>
          ${state.lookup.error ? `<p class="tt-bad small">${esc(state.lookup.error)}</p>` : ""}
          ${state.pinned ? `<p class="small">Provision chosen by you: <b>${esc(state.pinned.title)}</b> <button id="tt-unpin" class="tt-mini">clear</button></p>` : ""}
          ${state.lookup.hits ? (state.lookup.hits.length ? `<ul class="tt-list tt-hits">${state.lookup.hits.map((h, i) => `<li><button data-hit="${i}" class="tt-mini">Use</button> <b>${esc(h.title)}</b>${h.kind === "registry" ? ` <span class="tt-chip tt-ok">built-in right</span>` : ""} <span class="muted small">similarity ${h.score.toFixed(2)}</span><div class="muted small">${esc(h.about.slice(0, 180))}</div></li>`).join("")}</ul>` : `<p class="muted small">Nothing close in the catalog.</p>`) : ""}
        </div>` : ""}
        ${state.handedOff ? `<p class="tt-warn">${esc(state.handedOff)}</p>` : state.error ? `<p class="tt-bad">${esc(state.error)}</p>` : ""}
        ${r ? `
        <div class="tt-provision small muted">${support.speak ? `<button id="tt-say" class="tt-mini">Read aloud</button> ` : ""}${esc(r.provision.title)} · found via ${esc(r.provision.via)} · clause chosen by ${esc((r.judges ?? [r.judge ?? "judge"]).join(", "))} (p = ${r.then.p.toFixed(2)}) ${agreementChip(r)}${r.computed ? `<div class="small">${esc(r.computed)}</div>` : ""}</div>
        ${trace(r)}
        ${(() => { const v = timeVerdict(state.question, r.then.amount); return v ? `<p class="tt-verdict ${v.within ? "tt-ok" : "tt-warn"}"><b>${v.within ? "Still in time" : "Probably out of time"}.</b> ${esc(v.text.replace(/^(Still in time|Probably out of time)[:.]? ?/, "").replace(/^./, (c) => c.toUpperCase()))}${(() => { const last = lastDay(r.eventDate, r.then.amount); return last && v.within ? ` Last day: <b>${esc(last)}</b> <button id="tt-ics" class="tt-mini" data-last="${esc(last)}">Add to calendar</button>` : ""; })()}</p>` : ""; })()}
        <div class="tt-grid">
          ${moment("Then", r.then, `<blockquote>${esc(r.evidence.quote)}</blockquote>`)}
          ${moment("Now", r.now, r.changed ? `<div class="tt-warn">Changed since ${esc(r.eventDate)} — a date-blind answer would say ${esc(r.now.amount?.text ?? "something else")}.</div>` : `<div class="tt-ok">Unchanged since ${esc(r.eventDate)}.</div>`)}
          <div class="tt-moment"><div class="tt-label">Why it changed</div>${r.changes.length ? `<ul class="tt-list">${r.changes.map((x) => `<li><b>${esc(x.effective)}</b> <a href="${esc(safeUrl(x.url))}" target="_blank" rel="noreferrer">${esc(x.title)}</a></li>`).join("")}</ul>` : `<p class="muted small">No amending instrument in force since ${esc(r.eventDate)}.</p>`}</div>
          <div class="tt-moment"><div class="tt-label">Next</div>${r.upcoming.length ? `<ul class="tt-list">${r.upcoming.map((x) => `<li><b>${esc(x.effective)}</b> ${esc(x.title)}</li>`).join("")}</ul>` : `<p class="muted small">No published change ahead in the official feeds.</p>`}
            ${state.announcedError ? `<p class="tt-bad small">The search for announced changes failed: ${esc(state.announcedError)}</p>` : ""}
            ${state.announced ? (state.announced.length ? `<div class="tt-label">Announced, not law yet</div><ul class="tt-list">${state.announced.map((x) => `<li><b>${esc(x.effective)}</b>${x.amount ? ` · ${esc(x.amount.text)}${x.amountFrom === "title" ? " (from the title)" : ""}` : ""} <a href="${esc(safeUrl(x.url))}" target="_blank" rel="noreferrer">${esc(x.title)}</a><blockquote class="small">${esc(x.quote)}</blockquote></li>`).join("")}</ul>` : `<p class="muted small">No announced change found on ${esc(state.announcedNote ?? "government sites")}.</p>`) : ""}
            <div class="row"><button id="tt-announced" ${state.announcedBusy ? "disabled" : ""}>${state.announcedBusy ? "Searching government sites…" : "Search announced changes (Exa)"}</button><button id="tt-watch">Watch this rule</button></div></div>
        </div>
        <div class="tt-steps">
          <div class="tt-label">Next steps — found on the live web with Exa${state.steps?.counterparty ? ` · ${esc(state.steps.counterparty)}` : ""}</div>
          ${state.stepsBusy ? `<p class="muted small">Working out where to send it, the time limit and what was reported that day…</p>` : ""}
          ${state.stepsError ? `<p class="tt-bad small">The search for next steps failed: ${esc(state.stepsError)}</p>` : ""}
          ${state.steps ? (state.steps.steps.length ? `<ul class="tt-list">${state.steps.steps.map((x) => `<li><b>${x.kind === "where" ? "Where to send it" : x.kind === "deadline" ? "Time limit" : "Reported that day"}</b> · <a href="${esc(safeUrl(x.url))}" target="_blank" rel="noreferrer">${esc(x.title)}</a>${x.published ? ` <span class="muted small">published ${esc(x.published)}</span>` : ""}<blockquote class="small">${esc(x.quote)}</blockquote></li>`).join("")}</ul>` : `<p class="muted small">Nothing reliable found for the next steps.</p>`) : ""}
          ${!state.steps && !state.stepsBusy ? `<button id="tt-steps-go">Work out the next steps (Exa)${state.privateMode ? " — sends your question to Exa and the hosted judge" : ""}</button>` : ""}
        </div>
        <div class="tt-claim">
          <h3>Act on it — only with your approval</h3>
          ${!c ? `${split(r) ? `<p class="tt-warn small">${r.agreement?.note === "on-device judge only" ? "This was decided on this device only, by one small model." : "The judges did not all pick the same clause."} Read the quoted clause above before you claim under it.</p><label class="small"><input id="tt-reviewed" type="checkbox" ${state.reviewed ? "checked" : ""} /> I have read the quoted clause and it describes my case</label>` : ""}<label>Send the claim to <input id="tt-recipient" value="${esc(state.recipient ?? whereUrl() ?? defaultRecipient(r.provision.title))}" /></label><button id="tt-prepare" class="primary" ${r.then.amount && (!split(r) || state.reviewed) ? "" : "disabled"}>Prepare claim and Warrant</button>` : `
          <pre class="tt-letter">${esc(c.letter)}</pre>
          <p class="small muted">Warrant: signed on this device (${esc(c.artifact?.mandate.alg)}), recipient ${esc(c.proposal?.receiver)}, evidence pinned to ${esc(r.evidence.url)}; ${c.artifact?.judgments?.length ?? 0} judgment receipt(s).</p>
          ${!c.sent ? `<button id="tt-approve" class="primary">Approve with this device and send</button>` : `
          <div class="${c.receiver?.decision === "ACCEPT" ? "tt-ok" : "tt-bad"}"><b>Receiver: ${esc(c.receiver?.decision)}</b>${c.sent.reference ? ` · reference ${esc(c.sent.reference)}` : ""}<br/><span class="small">checked: ${esc(c.receiver?.checked.join(", "))}${c.receiver?.reasons.length ? ` · ${esc(c.receiver.reasons.join("; "))}` : ""}</span></div>
          <p class="small muted">Ledger: ${esc(c.ledger.join(" → "))}</p>
          <div class="row">${whereUrl() ? `<a class="tt-linkbtn" href="${esc(safeUrl(whereUrl()))}" target="_blank" rel="noreferrer">Open the claim page</a>` : ""}<button id="tt-copy">Copy the claim text</button><a class="tt-linkbtn" id="tt-warrant" download="warrant.json" href="data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(c.artifact ?? {}, null, 1))}">Download the Warrant</a></div>
          <p class="small muted">The receiver above is a simulation of what a counterparty can check. Nothing has been sent to the real one: you submit it yourself on their page.</p>
          ${r.changed ? `<button id="tt-blind">What if the receiver read today's page instead?</button>${c.dateBlind ? `<div class="tt-bad small"><b>${esc(c.dateBlind.decision)}</b> — ${esc(c.dateBlind.reasons.join("; "))}. Pinning the official version is what makes the claim checkable.</div>` : ""}` : ""}`}`}
        </div>` : ""}
        ${state.knowledge ? `<details class="tt-knowledge" ${r ? "" : "open"}>
          <summary><b>What this agent knows</b> <span class="muted small">— collected for retrieval, plus what it reads live</span></summary>
          ${r ? `<p class="small"><b>Used for this answer:</b> ${esc(r.provision.title)} (${esc(r.provision.via === "exa" ? "found with Exa" : r.provision.via === "catalog" ? "found in the on-device catalog" : r.provision.via === "registry" ? "a built-in right" : r.provision.via)}) · <a href="${esc(safeUrl(r.then.url))}" target="_blank" rel="noreferrer">official text as of ${esc(r.then.date)}</a>${state.steps?.steps.length ? ` · ${state.steps.steps.map((x) => `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noreferrer">${esc(new URL(x.url).hostname.replace(/^www\./, ""))}</a>`).join(", ")} (Exa)` : ""}${state.announced?.length ? ` · ${state.announced.map((x) => `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noreferrer">${esc(new URL(x.url).hostname.replace(/^www\./, ""))}</a>`).join(", ")} (Exa, announced)` : ""}</p>` : ""}
          <div class="tt-know-grid">${state.knowledge.collected.map((k) => `<div class="tt-know"><div class="tt-know-n">${k.count.toLocaleString("en-US")}</div><div class="tt-label">${esc(k.unit)}</div><div><b>${esc(k.title)}</b>${k.running === true ? ` <span class="tt-chip tt-ok">running here</span>` : k.running === false ? ` <span class="tt-chip tt-warn">not running</span>` : ""}</div><div class="muted small">${esc(k.detail)}</div>${k.items ? `<details class="small"><summary>list</summary>${k.items.map((i) => `<div>${esc(i.title)}</div>`).join("")}</details>` : ""}</div>`).join("")}</div>
          <div class="tt-label">Read live, never stored</div>
          <ul class="tt-list small">${state.knowledge.live.map((l) => `<li><b>${esc(l.title)}</b>: ${esc(l.detail)}</li>`).join("")}</ul>
        </details>` : ""}
        <div class="tt-radar">
          <h3>Rights radar</h3>
          ${state.radar.watches.length ? `<ul class="tt-list">${state.radar.watches.map((w) => `<li>${esc(w.label)} <span class="muted small">since ${esc(w.since)}</span></li>`).join("")}</ul>` : `<p class="muted small">Watch a rule to be told when it changes.</p>`}
          <div class="row"><button id="tt-check" ${state.radar.watches.length ? "" : "disabled"}>Check now</button><button id="tt-check-year" ${state.radar.watches.length ? "" : "disabled"}>Changes in the last year</button><button id="tt-monitor">Create Exa Monitor</button></div>
          ${state.radar.note ? `<p class="small muted">${esc(state.radar.note)}</p>` : ""}
          ${state.radar.alerts.map((a) => `<p class="small tt-warn">${esc(a)}</p>`).join("")}
          ${state.radar.results ? `<ul class="tt-list">${state.radar.results.map((x) => `<li><b>${esc(x.label)}</b>: ${x.error ? esc(x.error) : `${(x.changes ?? []).map((c) => `${esc(c.effective)} ${esc(c.title)}`).join("; ") || "no change in force"}${x.upcoming?.length ? ` · <span class="tt-warn">coming: ${x.upcoming.map((c) => `${esc(c.effective)} ${esc(c.title)}`).join("; ")}</span>` : ""}`}</li>`).join("")}</ul>` : ""}
        </div>
      </section>`;
    root.querySelectorAll<HTMLButtonElement>("[data-ex]").forEach((b) => b.addEventListener("click", () => { const e = EXAMPLES[Number(b.dataset["ex"])]!; state.question = e.question; state.date = e.date; state.result = undefined; state.claim = undefined; state.reviewed = false; state.announced = undefined; state.announcedBusy = false; state.announcedNote = undefined; state.announcedError = undefined; state.recipient = undefined; state.pinned = undefined; state.lookup = { q: "" }; state.steps = undefined; state.stepsBusy = false; state.stepsError = undefined; state.handedOff = undefined; state.error = undefined; state.dateTouched = false; stopSpeaking(); render(); }));
    root.querySelector("#tt-q")?.addEventListener("input", (ev) => {
      state.question = (ev.target as HTMLTextAreaElement).value;
      // A date written in the message ("on 10 June 2021", "yesterday", "viime viikolla") fills the date field, until the person sets the field by hand.
      // A new question with no date in it is about now: today, not the date left over from an example.
      const fromExample = EXAMPLES.some((e) => state.question.slice(0, 24) === e.question.slice(0, 24));
      const d = state.dateTouched ? undefined : (spokenDate(state.question) ?? relativeDate(state.question, today()) ?? (fromExample ? undefined : today()));
      const field = root.querySelector<HTMLInputElement>("#tt-date");
      if (d && field) { state.date = d; field.value = d; }
    });
    root.querySelector("#tt-date")?.addEventListener("input", (ev) => { state.date = (ev.target as HTMLInputElement).value; state.dateTouched = true; });
    root.querySelector("#tt-run")?.addEventListener("click", () => void run());
    root.querySelector("#tt-steps-go")?.addEventListener("click", () => void workOutSteps());
    root.querySelector("#tt-ics")?.addEventListener("click", (ev) => {
      const last = (ev.currentTarget as HTMLElement).dataset.last;
      if (!last || !r) return;
      const ics = icsEvent({ summary: `Last day: ${r.provision.title.slice(0, 80)}`, date: last, description: `${r.then.amount?.text ?? ""} from ${r.eventDate}. Official text: ${r.then.url}`, uid: `${r.eventDate}-${last}@internet-butler`, stamp: new Date().toISOString() });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
      a.download = `last-day-${last}.ics`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    });
    root.querySelector("#tt-copy")?.addEventListener("click", () => { if (state.claim) void copyText(state.claim.letter); });
    root.querySelector("#tt-lookup-q")?.addEventListener("input", (ev) => (state.lookup.q = (ev.target as HTMLInputElement).value));
    root.querySelector("#tt-lookup-q")?.addEventListener("keydown", (ev) => { if ((ev as KeyboardEvent).key === "Enter") void lookup(); });
    root.querySelector("#tt-lookup-go")?.addEventListener("click", () => void lookup());
    root.querySelector("#tt-unpin")?.addEventListener("click", () => { state.pinned = undefined; render(); });
    root.querySelectorAll<HTMLButtonElement>("[data-hit]").forEach((b) => b.addEventListener("click", () => { const h = state.lookup.hits?.[Number(b.dataset["hit"])]; if (h) { state.pinned = { ref: h.ref, title: h.title }; void run(); } }));
    root.querySelector("#tt-mic")?.addEventListener("click", () => toggleDictation());
    root.querySelector("#tt-lang")?.addEventListener("change", (ev) => (state.voiceLang = (ev.target as HTMLSelectElement).value));
    root.querySelector("#tt-private")?.addEventListener("change", (ev) => (state.privateMode = (ev.target as HTMLInputElement).checked));
    root.querySelector("#tt-say")?.addEventListener("click", () => { if (state.result) speak(spokenSummary(state.result)); });
    root.querySelector("#tt-recipient")?.addEventListener("input", (ev) => (state.recipient = (ev.target as HTMLInputElement).value));
    root.querySelector("#tt-reviewed")?.addEventListener("change", (ev) => { state.reviewed = (ev.target as HTMLInputElement).checked; render(); });
    root.querySelector("#tt-prepare")?.addEventListener("click", () => void prepare());
    root.querySelector("#tt-approve")?.addEventListener("click", () => void approveAndSend());
    root.querySelector("#tt-blind")?.addEventListener("click", () => void dateBlindReceiver());
    root.querySelector("#tt-watch")?.addEventListener("click", () => watch());
    root.querySelector("#tt-announced")?.addEventListener("click", () => void announced());
    root.querySelector("#tt-check")?.addEventListener("click", () => void checkRadar());
    root.querySelector("#tt-check-year")?.addEventListener("click", () => void checkRadar(new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10)));
    root.querySelector("#tt-monitor")?.addEventListener("click", () => void monitor());
  }
  render();
  // What the agent has to retrieve from (shown under the answer).
  fetch("/api/knowledge").then((r) => (r.ok ? r.json() : null)).then((k) => { if (k?.collected) { state.knowledge = k; render(); } }).catch(() => { /* optional */ });
  // Is there an on-device judge? Then offer private mode.
  fetch("/api/health").then((r) => r.json()).then((h) => { if (h?.onDevice || h?.catalog) { state.onDevice = h.onDevice; state.hasCatalog = !!h.catalog; render(); } }).catch(() => { /* the relay may be down; the panel says so on the first run */ });
  // Deep link, so a launcher can start a question (Siri Shortcuts "Open URL", Raycast, a browser search keyword):
  //   /?q=<situation>&date=YYYY-MM-DD&run=1&say=1&private=1     (the date may also be said inside q)
  const link = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const q = link.get("q")?.trim().slice(0, 2000);
  if (q && q.length >= 5) {
    state.question = q;
    const d = link.get("date");
    const date = d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : (spokenDate(q) ?? monthDate(q) ?? relativeDate(q, today()) ?? today());
    state.date = date;
    state.privateMode = link.get("private") === "1";
    state.sayResult = link.get("say") === "1";
    render();
    if (link.get("run") === "1" && date) void run();
  }
}
