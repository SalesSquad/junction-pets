# Pet voice — Junction pets speak (Gemini) and answer each other by audio

Every one of the 34 Junction companion pets has a Google DeepMind Gemini TTS voice and a
default language (`voices.json`, 17 languages). Pets talk **by audio**: the listener gets the
speaker's WAV, transcribes it with Gemini audio understanding, answers in its own persona
(from `pets/<company>/pet.json`) and speaks the answer with its own voice.

- `pet_voice.py` — stdlib-only CLI: `status`, `say`, `talk` (two pets), `relay` (all pets in a
  ring, each hears the previous one and replies), `learn`.
- `PLAYBOOK.md` — how to give any agent a voice; Google and OpenAI speech notes.
- `LESSONS.md` + `learned/voice-scores.json` — the learning loop (see below).
- `evidence/<run>.json` — text/hash/metric receipts of real runs (no audio).
- `experiments/` — the same runs recorded with the shared
  [experiment registry](../experiment-registry/README.md) CLI (`--root services/pet-voice/experiments`).
- `test_pet_voice.py` — offline checks (`python3 -m unittest services/pet-voice/test_pet_voice.py`).

## Run (owner's MacBook Pro)

```sh
cd services/pet-voice
python3 pet_voice.py relay                       # all 34 pets + closing turn, ~70 Gemini calls
python3 pet_voice.py talk meta nvidia --rounds 3 --reply-language heard
python3 pet_voice.py say rokoko "Hej alle sammen" --play
```

Audio, `index.html` player and `transcript.md` go to
`~/Library/Application Support/JunctionPetVoice/runs/<run>/` and are copied to iCloud Drive
`Events/Junction-2026/pet-voice/<run>/`. The receipt goes to `evidence/`; then `learn` runs.

## Learning loop

Each turn records models, request shape, latency, provider errors, `heardAccuracy`
(how closely the listener's transcript matched what the speaker meant to say) and whether a
pet that had to hand over actually named the next pet. `learn`:

1. rebuilds `learned/voice-scores.json` — model order (reliability × named-next rate, then
   speed; timeouts, 403/404 and per-day quota count as failures), the TTS
   request shape each model accepts, intelligibility per voice×language and per language;
2. rewrites the generated block of `LESSONS.md`;
3. records each run in the experiment registry format.

The next `talk`/`relay` reads that file, so dead or rate-limited models are skipped and
`--adapt` replaces voices that listeners keep mis-hearing. New manual lessons go in the
curated section of `LESSONS.md`.

## Boundaries

Synthetic companion dialogue; not a Chibi-authorized transport (no grants, no private
context, no external effects — each turn's `envelope` says so). Key stays in the MBP Keychain.
Pets are not company-endorsed. Tell listeners the voices are AI-generated.
