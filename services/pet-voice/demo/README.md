# Pet voice — demo video

`junction-pets-demo.mp4` — 2:05, 1920×1080, 30 fps, English on-screen text, no narration.
It was built on 15 Nov 2026 from the night listening page media.

| Time | Section | Audio |
| --- | --- | --- |
| 0:00 | Title: 34 pets, 17 languages, built on the Gemini API | — |
| 0:06 | Before: Bahn's company-copy line ("transport margin and handover list") | baseline relay persona, Gemini Live voice |
| 0:15 | After: the 03:12 crashed-demo scene, 10 lines in de / en / fi / da / ja with English subtitles | scene engine v2 text, Gemini Live native audio |
| 1:20 | How a spoken turn works: hear, direct, write, check, voice, learn | — |
| 1:31 | Gemini Voice design: description → voice (Bahn de, Featherless ja, DeepMind en-GB) | design previews |
| 1:50 | Measured: 34/34 pets answered by audio, 0.97 heard accuracy, 86 % → 0 template lines, critic 6/12 → 0 | — |
| 1:59 | End card, AI-voice disclosure | — |

Honest limits:
- The scene is voiced with the pets' prebuilt voices through the Live API; designed voices in scenes
  need the daily TTS quota.
- Most Voice design previews speak English whatever the voice's language, so only the three
  previews in the pet's own language are shown.
- The judge in the "measured" slide is a blind LLM judge (Claude Haiku), not people.

Rebuild (≈30 s): `python3 build.py --audio <listen page audio folder> --out /tmp/junction-pets-demo`
— see the docstring in `build.py` for the tools it needs.
