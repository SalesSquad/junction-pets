# Pet voice — Junction pets speak (Gemini) and answer each other by audio

**Google DeepMind "Best Use of Gemini API" submission: [SUBMISSION.md](SUBMISSION.md)** — problem, Gemini integration, evidence, 2-minute demo (`--gemini-only`).

Every one of the 34 Junction companion pets has a Google DeepMind Gemini TTS voice and a
default language (`voices.json`, 18 locales / 16 languages). Pets talk **by audio**: the listener gets the
speaker's WAV, transcribes it with Gemini audio understanding, answers in its own persona
(from `pets/<company>/pet.json`) and speaks the answer with its own voice.

- `pet_voice.py` — stdlib-only CLI: `status`, `say`, `talk` (two pets), `relay` (all pets in a
  ring, each hears the previous one and replies), `learn`.
- `PLAYBOOK.md` — how to give any agent a voice; Google and OpenAI speech notes.
- `LESSONS.md` + `learned/voice-scores.json` — the learning loop (see below).
- `evidence/<run>.json` — text/hash/metric receipts of real runs (no audio).
- `experiments/` — the same runs recorded with the shared
  [experiment registry](../experiment-registry/README.md) CLI (`--root services/pet-voice/experiments`).
- `demo/` — 2-minute demo video (`junction-pets-demo.mp4`, the scene in each pet's designed voice) and the
  script that builds it.
- `test_pet_voice.py` — offline checks (`python3 -m unittest services/pet-voice/test_pet_voice.py`).

## Run (owner's MacBook Pro)

```sh
cd services/pet-voice
python3 pet_voice.py relay                       # all 34 pets + closing turn, ~70 Gemini calls
python3 pet_voice.py talk meta nvidia --rounds 3 --reply-language heard
python3 pet_voice.py say rokoko "Hej alle sammen" --play
python3 pet_voice.py relay --gemini-only         # never call OpenAI; stops with GEMINI_ONLY_EXHAUSTED if Gemini is out
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

## Evidence (14 Nov 2026, owner's MBP, free-tier personal Gemini key)

| Run | Turns | Pets spoke / replied | Languages | Heard accuracy | Language kept | Voices |
| --- | --- | --- | --- | --- | --- | --- |
| `relay-all34-20261114` | 35/35 | 34 / 34 | 18 | 0.97 | 91 % | Gemini TTS; last 3 turns Live (TTS daily quota out) |
| `relay-all34-langrule-20261114` | 35/35 | 34 / 34 | 18 | 0.80 | 97 % | Live native audio (TTS in cooldown); 2 off-script turns |

Run 2 added the explicit language rule learned from run 1 (91 % → 97 %). Its lower heard
accuracy came from the Live voice paraphrasing two lines, which led to the script-fidelity
check now in `speak()`. An independent read-only verifier confirmed run 1's receipt, hashes,
durations and iCloud copies.

## Persona lab (personality, not just a voice)

`persona_lab.py` A/B-tests the same scene (`scenes.json`) with the current company-copy persona
versus a character bible (`characters.json`, now all 34 pets) plus craft rules against AI slop.
It is text-only, so it works while the TTS quota is out.

```sh
python3 persona_lab.py audit evidence/relay-all34-20261114.json   # slop signals of an old run
python3 persona_lab.py ab --tag my-test                          # both arms, all scenes
```

Outputs per scene: both transcripts, slop metrics (template rate, question endings, praise
openers, buzzwords, length variation, acting tags) and a blind X/Y packet for a judge or a
human. Pilot result: `persona-evidence/pilot-20261115.json` (bible arm won 4/4 blind).

## Scene engine (v2): characters that play off each other

`scene.py` runs a scene from `scenes.json` (7 scenes, every pet in at least one) as a small
production line per turn:

1. **Director** picks who speaks next and the move (tease, push back, short reaction, …).
   Rules first: opener, everyone speaks once, an argument may run A-B-A-B before a third voice
   has to enter, nobody past three lines while someone is still silent; then an LLM director
   for the most natural next speaker. A pet's first line must come in on the line before it.
2. **Writer** gets the character bible (`characters.json`: core, want, flaw, speech, humour,
   opinions, relationships, own-language anchors, catchphrases, never-list, vocal delivery),
   the scene beat, memory notes and the owner's taste, hears the previous WAV and writes one
   line plus a vocal direction (pace, volume, pitch, emotion).
3. **Checks** (`check_line`, `check_reply`): length, reused or lifted example lines (4 words,
   or 3 distinctive ones), catchphrase budget per scene, same opener as last time, a second
   one-word exclamation opener (any word — "Fascinating." after "Interesting."), reheating your
   own earlier idea, one voice tag max, stage directions, praise openers, buzzwords, question
   streaks, body-movement directions, native script, and **non-sequiturs**: the writer must
   copy the words it answers (`responds_to`), which have to be in the last two lines or beat.
4. **Critic** must fix every listed problem (a second round when a hard one survives); the
   version with fewer problems wins.
5. **Voice**: the pet's designed Gemini voice (`design-voices`, Voice design API,
   `learned/designed-voices.json`) with the per-line direction as `speech_metadata.style`;
   prebuilt voice or Live audio as fallback, then OpenAI as the last, paid fallback (also for
   the text steps — see PLAYBOOK).
6. **Memory** (`~/Library/Application Support/JunctionPetVoice/memory/pets.json`, local, not
   in git): after a scene each pet keeps up to 6 short notes, so running jokes and grudges carry
   over. A pet gets at most one callback per scene (`callback` field) and a note retires after
   two callbacks. Habits are tracked too: repeated line openings and content words a pet used in
   two of its last four scenes come back as "start differently" / "find a fresh image" hints.
   `scene.py memory --rebuild` drops near-duplicate notes and replays `scene-evidence/`.

```sh
python3 scene.py design-voices --pets rokoko,bahn-express  # one designed voice per pet
python3 scene.py run demo-crash-0312                       # audio scene, ~4 Gemini calls/turn
python3 scene.py run all --text-only --tag test            # text only, no TTS quota
python3 scene.py voice-script script.json --run-id base-x --prebuilt   # voice a fixed transcript (baselines)
python3 scene.py design-voices --disliked                 # redesign voices the owner rated 👎, with their notes
python3 listen.py build --spec spec.json --out /tmp/listen  # blind A/B listening page
python3 listen.py ingest --ratings ratings.json --key /tmp/listen/key.json --manifest-dir /tmp/listen
```

**Blind listening → taste.** `listen.py build` pairs two systems per scene (X/Y in random
order) and prebuilt vs designed voice per pet (A/B), writes `index.html` and a private
`key.json`. The owner's ratings (winner, reasons, 👍/👎 per line, free note) are read back with
`ingest` into `learned/taste.json`: system wins/losses, liked and disliked lines per pet,
voice preference and notes. `scene.py` puts liked/disliked lines and notes into every writer
prompt and uses the preferred voice type, so each listening round steers the next scene.
The page also plays every pet's designed-voice sample (👍/👎 + note): a 👎 sends that pet back
to its prebuilt voice until `design-voices --disliked` redesigns it with the note. Audio is
MP3 (artifact pages refuse `.m4a`); `key.json` stays private until the ratings are ingested.
Voice A/B pairs are voiced on one pinned TTS model (`voice-script --models`) so only the voice
differs. `ingest` skips ratings it has already counted (`taste.json` → `ingested`), because the
page db returns every old rating on each read.
Scene receipts (text, metrics, director decisions, no audio) go to `scene-evidence/`.

## Boundaries

Synthetic companion dialogue; not a Chibi-authorized transport (no grants, no private
context, no external effects — each turn's `envelope` says so). Key stays in the MBP Keychain.
Pets are not company-endorsed. Tell listeners the voices are AI-generated.
