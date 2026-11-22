import {exportPacket} from '../src/packet.mjs';
const Base = globalThis.HTMLElement ?? class {};
const labels = {source_observed: 'Source observed', derived: 'Derived', geometry_measured: 'Geometry measured', cross_checked: 'Cross-checked', unavailable: 'Evidence insufficient'};
export class EvidenceReviewElement extends Base {
  #context = null;
  #version = 0;
  #busy = false;
  constructor() {
    super();
    if (this.attachShadow) this.attachShadow({mode: 'open'});
  }
  set context(value) { this.#context = value ? Object.freeze({...value}) : null; this.#version++; this.#busy = false; this.render(); }
  get context() { return this.#context; }
  connectedCallback() { this.render(); }
  render() {
    if (!this.shadowRoot) return;
    const root = this.shadowRoot;
    root.replaceChildren();
    const make = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
    const style = make('style', ':host{display:block;color:#183d34;font:15px system-ui}section{border:1px solid #adc5bb;border-radius:12px;padding:20px;background:#f8faf6}h2{margin-top:0}label{display:block;margin:12px 0}input,textarea{display:block;box-sizing:border-box;width:100%;font:inherit;padding:9px;border:1px solid #95afa4;border-radius:5px}button{font:inherit;padding:9px 14px;margin:4px;border:1px solid #668a7b;border-radius:6px;background:#eaf1e8;color:#173b32;cursor:pointer}button:disabled{opacity:.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2eb;padding:10px;border-radius:6px}li,p{overflow-wrap:anywhere;line-height:1.5}.actions{display:flex;flex-wrap:wrap}input[type=checkbox]{display:inline;width:auto;margin-right:8px}.badge{font-weight:700;color:#285a46}');
    root.appendChild(style);
    const section = make('section'); root.appendChild(section);
    if (!this.#context) { section.appendChild(make('p', 'Select a source to inspect its evidence.')); return; }
    const {dataset, claim, review} = this.#context;
    const version = this.#version, snapshot = review.snapshot();
    section.append(make('h2', claim.value ?? 'No supported answer'), make('p', labels[claim.level] ?? claim.level));
    section.lastChild.className = 'badge';
    const manifest = dataset.manifest();
    section.append(make('p', claim.reason), make('p', `${manifest.source.filename} · source ${manifest.source.sha256.slice(0, 12)} · generation ${manifest.generation.slice(0, 12)}`));
    section.appendChild(make('p', snapshot.current ? `Reviewer ${snapshot.current.reviewer}: ${snapshot.current.value}. Original engine result is unchanged.` : 'No human review recorded.'));
    const refs = make('fieldset'); refs.appendChild(make('legend', 'Original source evidence / correction citations'));
    for (const ref of claim.refs) {
      const e = dataset.resolve(ref), label = make('label'), check = make('input');
      check.type = 'checkbox'; check.value = ref.id; check.name = 'citation'; check.checked = true;
      label.append(check, document.createTextNode(`${ref.id} · ${e.kind}`));
      refs.append(label, make('pre', JSON.stringify({locator: e.locator, data: e.data}, null, 2)));
    }
    section.appendChild(refs);
    const field = (title, name, tag = 'input') => {
      const label = make('label', title), input = make(tag); input.name = name; input.maxLength = name === 'note' ? 1000 : 400;
      if (tag === 'input') input.type = 'text';
      label.appendChild(input); section.appendChild(label); return input;
    };
    const actor = field('Reviewer name (locally declared)', 'reviewer');
    actor.value = snapshot.current?.reviewer ?? snapshot.events.at(-1)?.command.reviewer ?? '';
    const note = field('Review note', 'note', 'textarea');
    const correction = field('Manual correction', 'correction');
    const message = make('p', 'Reviews are declarations. Export a packet to preserve this local history.'); message.role = 'status';
    const actions = make('div'); actions.className = 'actions'; section.appendChild(actions);
    const buttons = [];
    const button = (name, handler, disabled = false) => {
      const b = make('button', name); b.type = 'button'; b.disabled = this.#busy || disabled; b.dataset.unavailable = String(disabled);
      b.addEventListener('click', handler); actions.appendChild(b); buttons.push(b);
    };
    const apply = kind => async () => {
      if (this.#busy) return;
      this.#busy = true; buttons.forEach(b => b.disabled = true);
      try {
        const selected = [...root.querySelectorAll('input[name=citation]:checked')].map(e => dataset.ref(e.value));
        await review.apply({id: crypto.randomUUID(), expectedHead: snapshot.head, kind, reviewer: actor.value,
          note: note.value, value: kind === 'correct' ? correction.value : null, refs: kind === 'correct' ? selected : []});
        if (version !== this.#version) return;
        this.#busy = false; this.render();
        this.dispatchEvent(new CustomEvent('review-change', {detail: {generation: manifest.generation, claimSha256: claim.claimSha256, review: review.snapshot()}, bubbles: true}));
      } catch (e) {
        if (version === this.#version) { this.#busy = false; buttons.forEach(b => b.disabled = b.dataset.unavailable === 'true'); message.textContent = e.message; }
      }
    };
    button('Confirm engine answer', apply('confirm'), claim.status !== 'supported');
    button('Record correction', apply('correct'), !claim.refs.length);
    button('Undo', apply('undo'), !snapshot.canUndo);
    button('Redo', apply('redo'), !snapshot.canRedo);
    button('Export packet', async () => {
      try {
        const packet = await exportPacket(dataset, claim, review);
        if (version !== this.#version) return;
        const event = new CustomEvent('evidence-export', {detail: packet, cancelable: true, bubbles: true});
        if (!this.dispatchEvent(event)) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(packet, null, 2)], {type: 'application/json'}));
        const a = make('a'); a.href = url; a.download = `evidence-${packet.integrity.sha256.slice(0, 12)}.json`; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) { if (version === this.#version) message.textContent = e.message; }
    });
    const history = make('ol');
    for (const event of snapshot.events.slice(-10)) history.appendChild(make('li', `${event.sequence}: ${event.command.kind} · ${event.command.reviewer}`));
    section.append(history, message);
  }
}
if (globalThis.customElements && !customElements.get('evidence-review')) customElements.define('evidence-review', EvidenceReviewElement);
