# Playbook — give any agent a voice and let agents talk to each other

Read this before adding speech to a Junction pet, a Chibi agent, a Taimi agent or any other
companion. It is short on purpose; the evidence lives in `evidence/`, the learned state in
`learned/voice-scores.json`, and the running lessons in [LESSONS.md](LESSONS.md).

## 1. Five-minute path (Junction pets)

All commands run on the owner's **MacBook Pro** (the Gemini key lives only in its Keychain),
reached through Remote Desktop Commander. Long runs go in a named tmux session
(`~/.agents/skills/remote-desktop-commander/scripts/session.py create <name> --cwd …`),
because a remote call returns after ~3 s.

```sh
cd services/pet-voice
python3 pet_voice.py status                                  # 34 profiles, key present (value never shown)
python3 pet_voice.py say google-deepmind "Hei Junction!" --play
python3 pet_voice.py talk aiven bahn-express --rounds 2       # two pets, by audio, Finnish ↔ German
python3 pet_voice.py relay                                    # all pets in a ring; each hears and answers
python3 pet_voice.py learn                                    # scores, model order, LESSONS.md, registry
```

`relay` and `talk` resume from the last good turn when rerun with the same `--run-id`.

## 2. Add a voice to a new agent

1. Add a profile to `voices.json`: one of the 30 prebuilt Gemini voices, a BCP-47 language
   and a short delivery style. (Outside this repo, copy the same three fields into the agent's
   own config; `pet_voice.py` only needs `name`, `display`, `tagline`, `introduction`.)
2. `say <agent> "<line>"` to hear it; `talk <agent> <existing-pet>` to prove it can hear and
   answer another agent.
3. `learn`. If its voice/language pair is mis-heard (`<0.75`), rerun with `--adapt` or change
   the voice in the profile.

## 3. How a spoken turn works

`speaker text → Gemini TTS (speaker voice) → WAV → listener receives the WAV → Gemini audio
understanding returns {heard, heard_language, reply} in the listener's persona → Gemini TTS
(listener voice)`. Agents never pass text to each other: the listener only gets audio, so the
`heard` transcript measures how intelligible the speaker's voice was (`heardAccuracy`).

Languages: each pet has a default language; `--reply-language heard` makes listeners answer
in the language they heard, `--reply-language sv-SE` forces one language.

## 4. Provider notes (checked 14 Nov 2026)

**Google / DeepMind (primary)** — [Speech generation](https://ai.google.dev/gemini-api/docs/speech-generation),
[Live API](https://ai.google.dev/gemini-api/docs/live-api).
- TTS models visible to this key: `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`,
  `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`.
- `POST /v1beta/models/{model}:generateContent`, `responseModalities:["AUDIO"]`, voice in
  `speechConfig.voiceConfig`; per-turn style in `speech_metadata.style`. Language is detected
  from the text (130+ languages on 3.8 Flash TTS).
- 3.8 returns a complete 24 kHz mono WAV; 3.1 returned headerless L16 PCM. `normalize_audio`
  handles both.
- Multi-speaker in one request is limited to **2 speakers**, so N-agent conversations are
  synthesized turn by turn (what `relay` does).
- `GET /v1beta/voices` lists the extended voice library; custom/cloned voices exist but are not
  used here.
- Real-time duplex: Live API models `gemini-3.8-live`, `gemini-3.1-flash-live-preview`,
  `gemini-3.5-live-translate-preview` (bidiGenerateContent, 16 kHz in / 24 kHz out PCM).
  Use ephemeral tokens for browsers — never ship the key.

**OpenAI (secondary, not wired in)** — [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech),
[Realtime / voice agents](https://developers.openai.com/api/docs/guides/realtime).
- `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts` are deprecated and shut down **6 Jan 2027**; migrate to
  `gpt-realtime-2.1-mini` via the Realtime API (not `/v1/audio/speech`).
- 13 built-in voices (alloy … marin, cedar; marin/cedar recommended). Usage policy requires
  telling listeners the voice is AI-generated.
- An OpenAI adapter would only need a `speak()` twin; keep receipts in the same format so
  `learn` can compare providers.

## 5. Boundaries

- Synthetic companion dialogue on the owner's Mac. It is **not** a Chibi-authorized transport,
  grants nothing and touches no private data (see `docs/INTER_PET_COLLABORATION.md`).
- The key stays in the MBP Keychain (`com.salessquad.junction.gemini`); `pet_voice.py` reads it
  into memory per process and never prints, logs or forwards it. Other hosts need their own
  provider-authorized key.
- Pets are independent companions, not company-endorsed voices. Say so when demoing.
