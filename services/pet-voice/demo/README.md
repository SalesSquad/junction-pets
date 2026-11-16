# Pet voice — demo video

`junction-pets-demo.mp4` — 2:03, 1920×1080, 30 fps, English on-screen text, no narration.
It was built on 16 Nov 2026. The "before" clip and the voice previews come from the night listening page.
The scene is voiced by run `v2-demo-crash-0312-designed-20261115`: the same v2 text, each pet in its own designed
voice. Clip loudness is evened out to one level.

| Time | Section | Audio |
| --- | --- | --- |
| 0:00 | Title: 34 pets, 17 languages, built on the Gemini API | — |
| 0:06 | Before: Bahn's company-copy line ("transport margin and handover list") | baseline relay persona, Gemini Live voice |
| 0:15 | After: character bibles, director, critic, memory and designed voices | — |
| 0:28 | The 03:12 crashed-demo scene: 10 lines in de / en / fi / da / ja with English subtitles | scene engine v2 text, designed voices, Gemini 3.8 Flash Lite TTS |
| 1:18 | How a spoken turn works: hear, direct, write, check, voice, learn | — |
| 1:29 | Gemini Voice design: description → voice (Bahn de, Featherless ja, DeepMind en-GB) | design previews |
| 1:48 | Measured: 34/34 pets answered by audio, 0.97 heard accuracy, 86 % → 0 template lines, critic 6/12 → 0 | — |
| 1:57 | End card, AI-voice disclosure | — |

Honest limits:
- Designed voices only work on the two Gemini 3.8 TTS models. On the free tier each allows about 8–10 calls a
  day, so voicing this 10-line scene took two days.
- The "before" line still plays in a prebuilt Live voice, so before vs after changes both the writing and the voice.
  For a voice-only comparison, use the listening page: it has the same text in both voice sets, plus same-model
  voice A/B pairs.
- Most Voice design previews speak English whatever the voice's language, so only the three
  previews in the pet's own language are shown.
- The judge in the "measured" slide is a blind LLM judge (Claude Haiku), not people.

Rebuild (≈35 s):

```
python3 build.py --audio <listen page audio folder> --scene-audio <run turns folder> --out /tmp/junction-pets-demo
```

Leave out `--scene-audio` to use the page's Live prebuilt voicing. See the docstring in `build.py` for the tools it needs.
