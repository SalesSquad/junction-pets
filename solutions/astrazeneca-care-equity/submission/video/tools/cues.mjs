// Canonical voice-over / caption cues for the SAMA video.
// Lines are verbatim from submission/VIDEO_SCRIPT.md (segment text split into caption chunks).
// Timing: each segment has a fixed window; inside it, cues get time in proportion to word count.
// Run from submission/video:  node tools/cues.mjs
// It rewrites the CUES block in index.html and writes VOICEOVER.md, so captions and the recording
// script always share one set of timecodes.
import fs from "node:fs";

export const TOTAL = 119; // seconds; the deliverable must stay at or under 120 s

export const segments = [
  {
    id: "s1", start: 0, end: 19.5, screen: "Title, then lung survival 17.9% vs 31.1% with the 1980-2024 line, then the map of the 23 areas",
    lines: [
      "Five years after a lung cancer diagnosis, relative survival for Finnish men is 17.9 percent.",
      "The Sweden and Norway average is 31.1.",
      "Finland's lung programme says curable cases are mostly found by chance, on other scans.",
      "What happens next decides how early treatment starts.",
    ],
  },
  {
    id: "s2", start: 19.5, end: 43, screen: "Who, how and where: regions vs education vs entry route",
    lines: [
      "Where you live is not the clearest gap.",
      "Survival does not differ significantly between regions.",
      "It does differ by education, and by how you enter care.",
      "In one Finnish lymphoma study, the median from first symptom to treatment was 127 days through a public health centre appointment,",
      "and 76 through occupational or private care.",
    ],
  },
  {
    id: "s3", start: 43, end: 72.5, screen: "Six weeks vs six months, stage 42%, the two-dates clock, then 23 SYNTHETIC FLARE sites and the comparability gate",
    lines: [
      "The OECD reports a six-week target from suspected-cancer referral to treatment.",
      "The law allows up to six months after the need is established.",
      "We found no county showing whether it meets either, and stage is recorded for only 42 percent of cancers.",
      "SAMA asks for two dates and an end reason per patient.",
      "On synthetic data, NVIDIA FLARE computed each county's figures locally.",
      "A county is compared only when it can see itself.",
    ],
  },
  {
    id: "s4", start: 72.5, end: 95, screen: "SYNTHETIC overdue list for Satakunta (counts, three rows), then a SYNTHETIC referral note read by Gemma",
    lines: [
      "Measuring is not enough.",
      "Since June, a county may identify patients whose care does not follow recommendations;",
      "whether that covers pathway timing is unconfirmed.",
      "SAMA turns that into a nurse's list of overdue referrals, lung follow-ups first.",
      "Gemma reads the note on an ordinary computer, code counts the days, a nurse confirms and calls.",
    ],
  },
  {
    id: "s5", start: 95, end: 115.5, screen: "Nemotron county plan with numbers checked, then the Satakunta pilot card",
    lines: [
      "Nemotron drafts each county's plan, and code checks every number.",
      "Our ask: Satakunta, lung follow-up first, a 2027 pilot, no new budget line.",
      "The county owns it; in the pilot, patient data stays in the county by design.",
      "The same pathway, wherever they live, whoever they are, however they enter care.",
    ],
  },
  { id: "s6", start: 115.5, end: TOTAL, screen: "End card", lines: [] },
];

const LEAD = 0.3; // silence at the start of each segment
const TAIL = 0.35; // silence at the end of each segment
const words = (s) => s.trim().split(/\s+/).length;

export function cues() {
  const out = [];
  for (const seg of segments) {
    if (!seg.lines.length) continue;
    const total = seg.lines.reduce((n, l) => n + words(l), 0);
    const span = seg.end - seg.start - LEAD - TAIL;
    let t = seg.start + LEAD;
    for (const line of seg.lines) {
      const d = (span * words(line)) / total;
      out.push({ seg: seg.id, start: +t.toFixed(2), end: +(t + d).toFixed(2), text: line });
      t += d;
    }
  }
  return out;
}

const tc = (s) => {
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
};

// When tools/vo-timing.json exists (written by tools/voiceover.py from the narration's character
// timestamps), captions follow the recorded voice instead of the word-count estimate.
function spokenCues() {
  const f = new URL("./vo-timing.json", import.meta.url);
  if (!fs.existsSync(f)) return null;
  const t = JSON.parse(fs.readFileSync(f, "utf8"));
  const expected = cues().map((c) => c.text).join("|");
  if (t.cues.map((c) => c.text).join("|") !== expected) throw new Error("vo-timing.json lines differ from the script: rerun tools/voiceover.py");
  return t.cues;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const list = spokenCues() || cues();
  const html = fs.readFileSync("index.html", "utf8");
  const block = `/*CUES*/ ${JSON.stringify(list)} /*END CUES*/`;
  const next = html.replace(/\/\*CUES\*\/[\s\S]*?\/\*END CUES\*\//, block);
  if (next === html && !html.includes(block)) throw new Error("CUES markers not found in index.html");
  fs.writeFileSync("index.html", next);

  const allWords = list.reduce((n, c) => n + words(c.text), 0);
  let md = `# SAMA video: voice-over script with timecodes\n\n`;
  md += `Generated by \`node tools/cues.mjs\` from the same cue list that drives the burned-in captions in\n`;
  md += `\`SAMA-video.mp4\`. Lines are verbatim from \`submission/VIDEO_SCRIPT.md\`. ${allWords} spoken words in\n`;
  md += `${TOTAL} s (${(allWords / (TOTAL - 3.5)).toFixed(2)} words per second over the spoken part); the last 3.5 s are silent.\n\n`;
  md += `**Narration.** The current track is a synthetic voice (ElevenLabs), made by \`python3 tools/voiceover.py\`; the in/out times below are where each line is actually spoken. To record a human voice instead:\n`;
  md += `**How to record.** Read each line so it starts at its "in" time and is finished by its "out" time\n`;
  md += `(a slightly faster read is fine; never run past "out", or the voice drifts from the captions). Record\n`;
  md += `one take as mono WAV, 48 kHz, and put it in that slot.\n\n`;
  md += `**How to put the voice in.** Either:\n\n`;
  md += `1. Replace \`assets/voiceover-slot.m4a\` with the recording (same file name, ${TOTAL} s long, encoded as\n`;
  md += `   AAC), then re-render: \`npx --yes hyperframes@0.7.28 render . --quality high --workers 2 --output SAMA-video.mp4\`; or\n`;
  md += `2. Keep the picture and swap only the audio (no re-render, takes seconds):\n\n`;
  md += "```bash\nffmpeg -i SAMA-video.mp4 -i voiceover.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 160k \\\n  -af apad -t " + TOTAL + " SAMA-video-voiced.mp4\n```\n\n";
  md += `Captions stay burned in either way, so the video also works with the sound off.\n\n`;
  md += `| # | In | Out | Screen | Line |\n| --- | --- | --- | --- | --- |\n`;
  list.forEach((c, i) => {
    const seg = segments.find((s) => s.id === c.seg);
    md += `| ${i + 1} | ${tc(c.start)} | ${tc(c.end)} | ${seg.screen} | ${c.text} |\n`;
  });
  md += `| - | ${tc(segments.at(-1).start)} | ${tc(TOTAL)} | End card | (silence) |\n`;
  fs.writeFileSync("VOICEOVER.md", md);
  console.log(JSON.stringify(list.map((c) => [c.seg, c.start, c.end, c.text.slice(0, 40)])));
  console.log("words", allWords);
}
