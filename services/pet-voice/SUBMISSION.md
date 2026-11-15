# Pet voice — Best Use of Gemini API (Google DeepMind challenge)

34 company pets at Junction 2026 speak in 18 locales, **hear each other as audio**, answer in
persona, and a loop measures how well they were understood. Gemini does every step; there is no
speech-to-text library, no TTS engine, no script.
## 1. Problem and why it matters
Company agents all sound like one brochure-reading assistant, and voice agents usually glue
STT + LLM + TTS from three vendors and lose tone on the way. The question: can agents from
different companies hold a spoken conversation, each with its own voice, language and character,
and can we *measure* whether they actually understood each other? That is the shape of
multi-agent voice products (support lines, companions, tutors) before anyone trusts them.
## 2. How the Gemini API is integrated (all stdlib REST, no SDK; `pet_voice.py`, `scene.py`)
- **Gemini TTS** (`gemini-3.8-flash-tts`, `-lite`, `3.1-flash-tts-preview`, `2.5-flash-preview-tts`):
  one of 30 prebuilt voices per pet (`voices.json`), per-line `speech_metadata.style` direction.
- **Voice design API**: 34 pet-specific designed voices (`learned/designed-voices.json`).
- **Audio understanding**: the listener gets the previous pet's WAV as `inlineData` and returns
  JSON (`heard`, `heard_language`, `reply`) via `responseSchema` — transcript, language ID and
  in-character reply in one call (`gemini-3.5-flash`, `-flash-lite`, low `thinkingLevel`).
- **Live API** (`live:gemini-2.5-flash-native-audio-latest`, WebSocket written by hand) as a
  separate-quota voice route when TTS quota is out, with a read-aloud fidelity check.
- **Structured output** drives the scene engine: director, writer, critic, memory.
## 3. What is innovative
- **Audio-to-audio relay with a ground truth.** The speaker knows what it meant to say; the next
  pet's Gemini transcript of the WAV gives `heardAccuracy` per turn, per voice x language.
- **Learning loop** (`pet_voice.py learn`): rebuilds model order, accepted TTS request shape per
  model and weak voice/language pairs from receipts; `--adapt` swaps voices listeners mis-hear.
  Dead and quota-capped models are skipped automatically. It found e.g. Achernar/hi-IN 0.52.
- **Scene engine** (`scene.py`): director, writer that hears the previous WAV, deterministic
  checks, critic, per-pet memory and designed voices — personality is tested, not assumed.
- **Receipts, not claims**: every run writes a hash/metric receipt (`evidence/`, `scene-evidence/`).
## 4. Why Gemini is essential
One model family covers voice synthesis with style control, voice design, native audio input,
language ID, structured JSON and real-time audio. Audio understanding is what makes the relay
real: the reply comes from the *sound*, not from a passed-along string. Swapping any stage for
another vendor would break the single-API round-trip that the intelligibility score measures.
## Evidence (receipts in this folder; numbers read from the files)
| Run (14 Nov) | Turns ok | Pets spoke / replied | Locales | Mean heard acc. | Language kept | Audio |
| --- | --- | --- | --- | --- | --- | --- |
| `relay-all34-20261114` | 35/35 | 34 / 34 | 18 | 0.97 (min 0.58) | 91 % | 393 s, 5 Gemini TTS/Live models |
| `relay-all34-langrule-20261114` | 35/35 | 34 / 34 | 18 | 0.80 (min 0.04) | 97 % | 572 s, 33 of 35 turns on Live |

- **Live `--gemini-only` run, 15 Nov 08:32 EET** (`evidence/demo-live-claude-20261115.json`): Meta and
  NVIDIA talk for 2 rounds by audio, 4/4 turns ok, both listeners replied, mean heard accuracy
  0.9965, 28.9 s of audio, only `live:gemini-2.5-flash-native-audio-latest` (voice) and
  `gemini-3.5-flash-lite` (listen/answer); 67.5 s wall time. The learning loop updated `LESSONS.md`.
- `voices.json`: 34 pets, 18 locales (16 base languages), 30 distinct prebuilt voices.
- Scene engine v2 vs the earlier persona arm: v2 won 3 of 4 blind comparisons; v2 beat the strict
  rotation variant 2/2 (`scene-evidence/judge-*.json`). 10 complete text-only scene receipts.
- The judge was Claude Haiku (blind, both orders), not Gemini; 4 comparisons is a small sample.
## Honest limits
- Runs happen on the owner's Mac (key in Keychain, output copied to iCloud). No hosted demo; the
  receipts hold text, hashes and metrics, not audio.
- Free-tier quota was hit on 14-15 Nov (`gemini-3.8-flash-tts` per-day 429 x22 in `LESSONS.md`;
  ~45 TTS calls/day). Run 2 therefore used Live audio and its accuracy dropped (two off-script lines).
- Scene receipts so far are text-only; the voiced scene path exists but has no receipt yet. The
  scene demo step failed on 15 Nov with `GEMINI_ONLY_EXHAUSTED` because the free daily quota for
  `gemini-3.5-flash` / `gemini-flash-lite-latest` was used up (429, retry after ~87 min); it now
  prints that reason instead of a bare `failed`. A paid or Junction-credit Gemini key removes this.
- An OpenAI fallback (`openai:*`) exists for quota exhaustion. Neither relay receipt lists an
  OpenAI model. `--gemini-only` (or `PET_VOICE_GEMINI_ONLY=1`) removes it from every TTS, STT
  and writer order and blocks the client; when Gemini routes are exhausted the run stops with
  `GEMINI_ONLY_EXHAUSTED` instead of falling back. Director and critic fall back to rules if
  Gemini fails, never to another model.
## Demo (about 2 minutes on the owner's Mac; `cd services/pet-voice`; always `--gemini-only`)
```sh
python3 -m unittest -q                                          # 2 s   offline checks, incl. gemini-only (38 tests)
python3 pet_voice.py --gemini-only status                       # <1 s  model orders: no openai: entry
python3 pet_voice.py say rokoko "Hej alle sammen" --gemini-only --play        # ~4 s  one Gemini voice
python3 pet_voice.py talk meta nvidia --rounds 2 --reply-language heard \
  --gemini-only --no-icloud --run-id demo-live --play           # ~70 s audio in, audio out (4 turns)
python3 scene.py run demo-crash-0312 --gemini-only --text-only --tag demo     # needs text quota left
python3 -c "import json;d=json.load(open('evidence/relay-all34-20261114.json'))['summary'];print({k:d[k] for k in ('turnsOk','speakers','listenersWhoReplied','meanHeardAccuracy','languageKeptRate')})"  # the 34-pet receipt
```
Timings measured on the owner's MacBook Pro on 15 Nov (status 0.4 s, say 3.5 s, talk 67.5 s without
`--play`). Use `unittest`, not `pytest`: the Mac's Homebrew Python has no pytest.
If quota is out, the run prints `GEMINI_ONLY_EXHAUSTED` and stops: that is the intended behaviour.
