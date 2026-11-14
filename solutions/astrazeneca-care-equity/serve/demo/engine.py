"""Offline demo engine: Gemma 3 270M + the C-270m-all-v2data LoRA adapter on CPU, then the frozen date resolver.

"Gemma reads, code counts." The model writes the events it read (absolute format, as trained); the frozen rule in
scribe/v3/resolve.py re-dates events whose date is not written in the note from the note's relative phrases. Every
event is a proposal: a person confirms every event. SYNTHETIC notes only were used to build and measure this.

Two halves:
  - pure functions (no torch): provenance, resolver arm, date-phrase highlights, post-processing of a raw model
    answer into the screen payload. serve/demo/tests/test_engine.py covers them without a model.
  - Engine: loads the pinned base (scribe/v2/config.py BASES["270m"]) and the PEFT adapter in one process, merges the
    LoRA weights, and decodes greedily on CPU in float32 with the generation cap the run was evaluated with.

Mirrors the GPU evaluation of the run (scribe/v2/evaluate.py generate/predict): v1 prompt (scribe/prompts.py
messages), chat template with generation prompt, no special tokens added again, greedy, stop on <eos> or
<end_of_turn>, special tokens skipped when decoding. Differences, stated: CPU float32 with merged LoRA weights instead
of CUDA bfloat16 with an unmerged adapter, and batch size 1 instead of 16. Greedy outputs can therefore differ where
two tokens are nearly tied (in practice: the model's own guesses of relative dates, which the resolver replaces).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = "C-270m-all-v2data"
ADAPTER = ROOT / "scribe" / "v3" / "artifacts" / RUN / "adapter"
RUN_RESULT = ROOT / "data" / "scribe" / "v3" / "student" / RUN / "result.json"
CONFIG = ROOT / "scribe" / "v2" / "config.py"
FREEZE = ROOT / "data" / "scribe" / "v4" / "resolver" / "freeze.json"
CLIENT = ROOT / "serve" / "client.py"

SCHEMA = "sama-scribe-demo-v1"
PERSON_CONFIRMS = "a person confirms every event"
PREFILLED = "pre-filled for one-click confirmation"
NEEDS_EDITING = "needs editing"
DEFAULT_MAX_NEW_TOKENS = 134  # result.json max_new_tokens of the run; read from the file when present
MAX_NOTE_CHARS = 6000
# Words the product never uses about extraction (NVIDIA_OPTIONS.md section 3 rules); tests check the payload.
BANNED = ("auto-confirmed", "skips review", "skip review", "clinically accurate", "works on real notes", "hospital-grade")


def _load_module(path, name):
    path = pathlib.Path(path).resolve()
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


def client():
    """serve/client.py: prompts loader, schema, decode_output and the resolver loader (standard library only)."""
    return _load_module(CLIENT, "sama_serve_client_for_demo")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def base_model():
    """(repo, revision) of the 270M base, pinned in scribe/v2/config.py and recorded in the run's result.json."""
    bases = _load_module(CONFIG, "sama_scribe_v2_config_for_demo").BASES["270m"]
    repo, revision = bases["repo"], bases["revision"]
    if RUN_RESULT.is_file():
        recorded = json.loads(RUN_RESULT.read_text(encoding="utf-8")).get("base") or {}
        if recorded and (recorded.get("repo"), recorded.get("revision")) != (repo, revision):
            raise RuntimeError(f"base in {RUN_RESULT.name} differs from scribe/v2/config.py: {recorded}")
    return repo, revision


def max_new_tokens():
    if RUN_RESULT.is_file():
        value = json.loads(RUN_RESULT.read_text(encoding="utf-8")).get("max_new_tokens")
        if isinstance(value, int) and value > 0:
            return value
    return DEFAULT_MAX_NEW_TOKENS


def resolver_arm(freeze_path=FREEZE, root=ROOT):
    """Arm A' when every file named in the freeze record still has its frozen sha256; otherwise arm A.

    Returns {"arm", "frozen", "freeze_file", "files": {path: {"frozen": sha, "now": sha}}, "reason"}.
    """
    freeze_path = pathlib.Path(freeze_path)
    out = {"arm": "A", "frozen": False, "freeze_file": None, "files": {}, "reason": ""}
    if not freeze_path.is_file():
        out["reason"] = "no freeze record; arm A (digits only)"
        return out
    record = json.loads(freeze_path.read_text(encoding="utf-8"))
    out["freeze_file"] = str(freeze_path.relative_to(root)) if freeze_path.is_relative_to(root) else str(freeze_path)
    out["frozen_at_utc"] = record.get("frozen_at_utc")
    ok = bool(record.get("files")) and "A'" in (record.get("arms") or [])
    for rel, frozen in (record.get("files") or {}).items():
        path = pathlib.Path(root) / rel
        now = sha256_file(path) if path.is_file() else None
        out["files"][rel] = {"frozen": frozen, "now": now}
        ok = ok and now == frozen
    if ok:
        out.update(arm="A'", frozen=True, reason="frozen arm A' (digits plus the Finnish lexicon); hashes match the freeze record")
    else:
        out["reason"] = "freeze record does not match the files on disk; fell back to arm A (digits only)"
    return out


# --------------------------------------------------------------------------- #
# Pure post-processing
# --------------------------------------------------------------------------- #


def _iso(value):
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def absolute_spans(note_text, note_date, resolver):
    """Dates written in the note in an absolute form, with character spans.

    Same patterns and arithmetic as resolver.written_dates (scribe/v3/resolve.py), kept per span for highlighting.
    """
    note = _iso(note_date)
    out = []
    for m in resolver.NUM.finditer(note_text):
        x = resolver.safe(m.group(3) or note.year, m.group(2), m.group(1))
        if x:
            out.append(dict(start=m.start(), end=m.end(), phrase=m.group(0), kind="absolute", date=x.isoformat(), precision="DAY"))
    for m in resolver.LONG.finditer(note_text):
        x = resolver.safe(m.group(3) or note.year, resolver.MONTHS.index(m.group(2)) + 1, m.group(1))
        if x:
            out.append(dict(start=m.start(), end=m.end(), phrase=m.group(0), kind="absolute", date=x.isoformat(), precision="DAY"))
    for m in resolver.MON.finditer(note_text):
        x = dt.date(int(m.group(2)), resolver.MONTHS.index(m.group(1)) + 1, 1)
        out.append(dict(start=m.start(), end=m.end(), phrase=m.group(0), kind="absolute", date=x.isoformat(), precision="MONTH"))
    return out


def highlights(note_text, note_date, resolver, arm):
    """Every date phrase in the note, in text order, without overlaps.

    kind "relative": a relative phrase the resolver places on one day (date = computed by code);
    kind "needs_person": a relative phrase with no single exact day (a person sets the date);
    kind "absolute": a date written out in the note (birth dates and other distractors included).
    """
    relative = [dict(start=s["start"], end=s["end"], phrase=s["phrase"], kind="relative", date=s["date"], precision="DAY",
                     days_before_note=s["days"], source=s["source"]) for s in resolver.relative_spans(note_text, note_date, arm)]
    person = [dict(start=s["start"], end=s["end"], phrase=s["phrase"], kind="needs_person", date=None, precision=None,
                   reason=s["reason"]) for s in resolver.needs_person_spans(note_text, arm)]
    taken, out = [], []
    for span in relative + person + absolute_spans(note_text, note_date, resolver):
        if any(span["start"] < b and a < span["end"] for a, b in taken):
            continue
        taken.append((span["start"], span["end"]))
        out.append(span)
    return sorted(out, key=lambda s: s["start"])


def _events_with_evidence(canonical, model_canonical, changes, spans):
    """Resolved events, each with the model's own date and the note phrase that carries its date."""
    used = set()
    out = []
    for event in canonical["events"]:
        change = next((i for i, c in enumerate(changes) if i not in used and c["type"] == event["type"] and c["to_date"] == event["date"]), None)
        if change is not None:
            used.add(change)
            c = changes[change]
            model_date, model_precision, by_code = c["from_date"], c["from_precision"], True
        else:
            model_date, model_precision, by_code = event["date"], event["precision"], False
        match = [s for s in spans if s["date"] == event["date"] and s["kind"] in ("relative", "absolute")
                 and (s["precision"] == event["precision"] or s["kind"] == "relative")]
        if by_code:
            match = [s for s in match if s["phrase"] == changes[change]["phrase"]] or match
        span = match[0] if match else None
        out.append(dict(
            type=event["type"], date=event["date"], precision=event["precision"],
            model_date=model_date, model_precision=model_precision, date_computed_by_code=by_code,
            phrase=span["phrase"] if span else None, phrase_kind=span["kind"] if span else None,
            phrase_start=span["start"] if span else None,
            status="proposed; " + PERSON_CONFIRMS,
        ))
    return out


def postprocess(raw_text, note_text, note_date, arm, prompts=None, resolver=None, schema=None):
    """Raw model answer -> screen payload (without timing and provenance).

    Uses serve/client.py decode_output twice: relative dates off (what the model itself proposed) and with the frozen
    resolver arm (what the screen proposes). Errors (not JSON, schema, calendar) or flags mean "needs editing".
    """
    c = client()
    prompts = prompts or c.load_prompts()
    resolver = resolver or c.load_date_resolver()
    schema = schema or c.load_schema("absolute")
    model = c.decode_output(raw_text, "absolute", note_date, prompts.canonicalise, schema, relative_dates="off")
    final = c.decode_output(raw_text, "absolute", note_date, prompts.canonicalise, schema, note_text=note_text,
                            relative_dates=arm, date_resolver=resolver)
    spans = highlights(note_text, note_date, resolver, arm)
    resolution = final["date_resolution"] or {"rule": resolver.RULE, "arm": arm, "changes": [], "needs_person": []}
    events = []
    if final["canonical"] is not None:
        events = _events_with_evidence(final["canonical"], model["canonical"], resolution.get("changes") or [], spans)
    usable = final["canonical"] is not None and not final["errors"]
    review = PREFILLED if usable and not final["flags"] else NEEDS_EDITING
    return {
        "highlights": spans,
        "model": {
            "raw": raw_text,
            "parsed": model["canonical"],
            "errors": model["errors"],
        },
        "resolved": {
            "entry_route": final["canonical"]["entry_route"] if final["canonical"] else None,
            "events": events,
            "prediction": final["canonical"],
        },
        "date_resolution": resolution,
        "flags": final["flags"],
        "errors": final["errors"],
        "review": review,
        "person_confirms": PERSON_CONFIRMS,
    }


def check_note(note_text, note_date):
    """Validate one request; raises ValueError with a short reason."""
    if not isinstance(note_text, str) or not note_text.strip():
        raise ValueError("note_text must be a non-empty string")
    if len(note_text) > MAX_NOTE_CHARS:
        raise ValueError(f"note_text is longer than {MAX_NOTE_CHARS} characters")
    if not isinstance(note_date, str) or _iso(note_date) is None or len(note_date) != 10:
        raise ValueError("note_date must be an ISO date YYYY-MM-DD")


def stop_token_ids(tok, model=None):
    """Same rule as scribe/v2/evaluate.py stop_token_ids: generation-config eos, tokenizer eos and <end_of_turn>."""
    ids = set()
    eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if eos is not None:
        ids |= set(eos if isinstance(eos, (list, tuple)) else [eos])
    if tok.eos_token_id is not None:
        ids.add(tok.eos_token_id)
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    if isinstance(eot, int) and eot >= 0 and eot != tok.unk_token_id:
        ids.add(eot)
    return sorted(int(i) for i in ids)


# --------------------------------------------------------------------------- #
# The model (torch)
# --------------------------------------------------------------------------- #


class Engine:
    """One loaded model. Not thread-safe; the worker serves one request at a time."""

    def __init__(self, threads=None, merge=True, dtype="float32"):
        import torch
        import transformers
        import peft
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        started = time.monotonic()
        self.threads = int(threads or os.environ.get("SAMA_SCRIBE_THREADS") or 8)
        torch.set_num_threads(self.threads)
        self.torch = torch
        self.repo, self.revision = base_model()
        self.arm_info = resolver_arm()
        self.arm = self.arm_info["arm"]
        c = client()
        self.prompts = c.load_prompts()
        self.resolver = c.load_date_resolver()
        self.schema = c.load_schema("absolute")
        self.max_new_tokens = max_new_tokens()
        self.dtype_name = dtype
        torch_dtype = {"float32": torch.float32, "bfloat16": torch.bfloat16}[dtype]
        self.tok = AutoTokenizer.from_pretrained(self.repo, revision=self.revision)
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(self.repo, revision=self.revision, dtype=torch_dtype, attn_implementation="sdpa")
        model = PeftModel.from_pretrained(model, str(ADAPTER))
        self.merged = bool(merge)
        if merge:
            model = model.merge_and_unload()
        model.to("cpu").eval()
        self.model = model
        self.stop = stop_token_ids(self.tok, model)
        self.stop_set = set(self.stop)
        self.load_seconds = time.monotonic() - started
        self.provenance = {
            "synthetic_training_data": True,
            "base_model": {"repo": self.repo, "revision": self.revision},
            "adapter": {"run": RUN, "path": str(ADAPTER.relative_to(ROOT)), "format": "PEFT LoRA r16",
                        "sha256": sha256_file(ADAPTER / "adapter_model.safetensors")},
            "decoding": {"strategy": "greedy", "max_new_tokens": self.max_new_tokens, "device": "cpu", "dtype": dtype,
                         "lora_merged": self.merged, "threads": self.threads, "batch_size": 1,
                         "prompt": "scribe/prompts.py messages (v1, absolute format)", "stop_token_ids": self.stop},
            "resolver": {"rule": self.resolver.RULE, "arm": self.arm, "frozen": self.arm_info["frozen"],
                         "lexicon": self.resolver.LEX.VERSION if self.arm == "A'" else None,
                         "freeze_file": self.arm_info["freeze_file"], "reason": self.arm_info["reason"]},
            "versions": {"python": sys.version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__,
                         "peft": peft.__version__},
            "gpu": None,
            "load_seconds": round(self.load_seconds, 3),
        }

    def warm_up(self):
        """One short generation so the first real request does not pay for lazy initialisation. Returns seconds."""
        started = time.monotonic()
        self.generate("Lähete lähetettiin eilen.", "2025-01-02", max_new_tokens=8)
        seconds = round(time.monotonic() - started, 3)
        self.provenance["warm_up_seconds"] = seconds
        return seconds

    def generate(self, note_text, note_date, max_new_tokens=None):
        torch = self.torch
        row = {"note_text": note_text, "note_date": note_date}
        prompt = self.tok.apply_chat_template(self.prompts.messages(row), tokenize=False, add_generation_prompt=True)
        enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False)
        started = time.monotonic()
        with torch.inference_mode():
            out = self.model.generate(**enc, do_sample=False, top_k=None, top_p=None, temperature=None,
                                      max_new_tokens=max_new_tokens or self.max_new_tokens, eos_token_id=self.stop,
                                      pad_token_id=self.tok.pad_token_id, use_cache=True)
        seconds = time.monotonic() - started
        ids = out[0, enc["input_ids"].shape[1]:].tolist()
        cut = next((k for k, t in enumerate(ids) if t in self.stop_set), None)
        text = self.tok.decode(ids[: cut if cut is not None else len(ids)], skip_special_tokens=True)
        return {"raw": text, "prompt_tokens": int(enc["input_ids"].shape[1]), "new_tokens": len(ids),
                "stopped": cut is not None, "generate_seconds": round(seconds, 3)}

    def extract(self, note_text, note_date, note_id=None, synthetic=None):
        check_note(note_text, note_date)
        started = time.monotonic()
        gen = self.generate(note_text, note_date)
        payload = postprocess(gen["raw"], note_text, note_date, self.arm, self.prompts, self.resolver, self.schema)
        total = time.monotonic() - started
        return {
            "schema": SCHEMA,
            "synthetic_note": synthetic,  # True for the SYNTHETIC demo notes; None when the caller does not say
            "note": {"id": note_id, "note_date": note_date, "note_text": note_text},
            **payload,
            "timing": {"generate_seconds": gen["generate_seconds"], "total_seconds": round(total, 3),
                       "prompt_tokens": gen["prompt_tokens"], "new_tokens": gen["new_tokens"], "stopped": gen["stopped"],
                       "load_average_1m": round(os.getloadavg()[0], 2), "cpu_count": os.cpu_count()},
            "provenance": self.provenance,
            "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
