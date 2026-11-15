/**
 * Voice in and out, with the browser's own speech services (Web Speech API).
 *
 *   dictate   speech -> text in the situation box. In Chrome the audio is transcribed by Google's speech
 *             service, in Safari by Apple's dictation; nothing is recorded until the person presses the button,
 *             and the panel says where the audio goes.
 *   speak     the answer read aloud by the device's own voices (speech synthesis runs locally).
 *   spoken    a date said or typed in words ("the tenth of June 2021", "10. kesäkuuta 2021", "10. Juni 2021")
 *             as an ISO date, so a spoken question can fill the date field.
 */
const pad = (n: number | string) => String(n).padStart(2, "0");
const MONTHS: Array<[RegExp, number]> = [
  [/^(jan(uary|uar)?|tammikuu(ta|n|ssa)?)$/, 1], [/^(feb(ruary|ruar)?|helmikuu(ta|n|ssa)?)$/, 2], [/^(mar(ch)?|märz|maerz|maaliskuu(ta|n|ssa)?)$/, 3],
  [/^(apr(il)?|huhtikuu(ta|n|ssa)?)$/, 4], [/^(may|mai|toukokuu(ta|n|ssa)?)$/, 5], [/^(june?|juni|kesäkuu(ta|n|ssa)?)$/, 6],
  [/^(july?|juli|heinäkuu(ta|n|ssa)?)$/, 7], [/^(aug(ust)?|elokuu(ta|n|ssa)?)$/, 8], [/^(sep(t|tember)?|syyskuu(ta|n|ssa)?)$/, 9],
  [/^(oct(ober)?|okt(ober)?|lokakuu(ta|n|ssa)?)$/, 10], [/^(nov(ember)?|marraskuu(ta|n|ssa)?)$/, 11], [/^(dec(ember)?|dez(ember)?|joulukuu(ta|n|ssa)?)$/, 12],
];
const monthOf = (w: string) => MONTHS.find(([re]) => re.test(w.toLowerCase()))?.[1];
const ORDINALS: Record<string, number> = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10, eleventh: 11, twelfth: 12, thirteenth: 13, fourteenth: 14, fifteenth: 15, sixteenth: 16, seventeenth: 17, eighteenth: 18, nineteenth: 19, twentieth: 20, thirtieth: 30 };
const valid = (y: number, m: number, d: number) => y >= 1900 && y <= 2100 && m >= 1 && m <= 12 && d >= 1 && d <= 31 && new Date(Date.UTC(y, m - 1, d)).getUTCDate() === d;

/** The first full date in a text, as YYYY-MM-DD. Day-first for dotted and slashed numbers (10.6.2021, 10/06/2021). */
export function spokenDate(text: string): string | undefined {
  const iso = text.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
  if (iso && valid(+iso[1]!, +iso[2]!, +iso[3]!)) return iso[0];
  const dotted = text.match(/\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b/);
  if (dotted && valid(+dotted[3]!, +dotted[2]!, +dotted[1]!)) return `${dotted[3]}-${pad(dotted[2]!)}-${pad(dotted[1]!)}`;
  const words = text.replace(/[,]/g, " ").split(/\s+/).filter(Boolean);
  const dayOf = (w: string | undefined) => {
    if (!w) return undefined;
    const n = w.toLowerCase().replace(/\.$/, "").replace(/^(\d{1,2})(st|nd|rd|th)$/, "$1");
    if (/^\d{1,2}$/.test(n)) return +n;
    const twenty = n.match(/^(twenty|thirty)[- ]?(\w+)$/);
    if (twenty && ORDINALS[twenty[2]!]) return (twenty[1] === "twenty" ? 20 : 30) + ORDINALS[twenty[2]!]!;
    return ORDINALS[n];
  };
  for (let i = 0; i < words.length; i++) {
    const m = monthOf(words[i]!.replace(/[.]$/, ""));
    if (!m) continue;
    // The year is the first four-digit number within three words after the month.
    const yi = [i + 1, i + 2, i + 3].find((k) => /^\d{4}\.?$/.test(words[k] ?? ""));
    if (yi === undefined) continue;
    const y = +words[yi]!.replace(".", "");
    // "10 June 2021", "10. kesäkuuta 2021", "the tenth of June 2021" (day before); "June 10 2021", "June 10th, 2021" (day after).
    const before = dayOf(words[i - 1]) ?? (/^(of|den|der)$/i.test(words[i - 1] ?? "") ? dayOf(words[i - 2]) : undefined);
    const after = yi > i + 1 ? dayOf(words[i + 1]) : undefined;
    const d = before ?? after;
    if (d && valid(y, m, d)) return `${y}-${pad(m)}-${pad(d)}`;
  }
  return undefined;
}

/**
 * Only a month and a year ("in March 2024", "maaliskuussa 2024"): the middle of that month, or undefined.
 * Kept apart from spokenDate, which never guesses a day: a form field is left to the person, but a caller
 * with no field (another agent asking over the API) must not silently fall back to today. Rates change on the
 * first or last day of a period, so the 15th is the safest single day to read the law on.
 */
export function monthDate(text: string): string | undefined {
  const words = text.replace(/[,]/g, " ").split(/\s+/).filter(Boolean);
  for (let i = 0; i < words.length; i++) {
    const m = monthOf(words[i]!.replace(/[.]$/, ""));
    const y = m && /^\d{4}[.;:?!]?$/.test(words[i + 1] ?? "") ? parseInt(words[i + 1]!, 10) : undefined;
    if (m && y && valid(y, m, 15)) return `${y}-${pad(m)}-15`;
  }
  return undefined;
}

/** A date said relative to today ("yesterday", "viime viikolla", "vor 3 Tagen") as YYYY-MM-DD; "last week" means seven days ago. */
export function relativeDate(text: string, today: string): string | undefined {
  const t = text.toLowerCase();
  const back = (n: number) => new Date(Date.parse(`${today}T00:00:00Z`) - n * 864e5).toISOString().slice(0, 10);
  const n = t.match(/\b(\d{1,3})\s+days?\s+ago\b/) ?? t.match(/(\d{1,3})\s+päivää\s+sitten/) ?? t.match(/\bvor\s+(\d{1,3})\s+tagen\b/);
  if (n) return back(Number(n[1]));
  if (/day before yesterday|toissapäivänä|vorgestern/.test(t)) return back(2);
  if (/\byesterday\b|\beilen\b|\bgestern\b/.test(t)) return back(1);
  if (/\btoday\b|tänään|\bheute\b|this morning|tänä aamuna/.test(t)) return back(0);
  if (/last week|a week ago|viime viikolla|viikko sitten|letzte woche|vorige woche|vor einer woche/.test(t)) return back(7);
  if (/last month|a month ago|viime kuussa|kuukausi sitten|letzten monat|vor einem monat/.test(t)) return back(30);
  return undefined;
}

type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start(): void; stop(): void; onresult: ((e: any) => void) | null; onerror: ((e: any) => void) | null; onend: (() => void) | null };
const recognitionCtor = (): (new () => Recognition) | undefined => (globalThis as any).SpeechRecognition ?? (globalThis as any).webkitSpeechRecognition;

export const voiceSupport = () => ({ dictate: !!recognitionCtor(), speak: typeof (globalThis as any).speechSynthesis !== "undefined" });
export const VOICE_LANGS: Array<{ code: string; label: string }> = [
  { code: "en-US", label: "English" },
  { code: "fi-FI", label: "Suomi" },
  { code: "de-DE", label: "Deutsch" },
];

/** Start dictation. `onText(final, interim)` gets the text so far; returns a function that stops it. */
export function dictate(lang: string, onText: (final: string, interim: string) => void, onEnd: (error?: string) => void): () => void {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    onEnd("this browser has no speech recognition");
    return () => {};
  }
  const rec = new Ctor();
  rec.lang = lang;
  rec.continuous = true;
  rec.interimResults = true;
  let final = "";
  let failed: string | undefined;
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = String(e.results[i][0]?.transcript ?? "");
      if (e.results[i].isFinal) final = `${final} ${t}`.trim();
      else interim += t;
    }
    onText(final, interim.trim());
  };
  rec.onerror = (e) => { failed = e?.error === "not-allowed" ? "microphone permission was not given" : String(e?.error ?? "speech recognition failed"); };
  rec.onend = () => onEnd(failed);
  rec.start();
  return () => rec.stop();
}

/** Read a text aloud with a voice of the given language, if the device has one. */
export function speak(text: string, lang = "en-US"): boolean {
  const synth = (globalThis as any).speechSynthesis;
  const Utterance = (globalThis as any).SpeechSynthesisUtterance;
  if (!synth || !Utterance) return false;
  synth.cancel();
  const u = new Utterance(text);
  u.lang = lang;
  u.rate = 1;
  synth.speak(u);
  return true;
}
export const stopSpeaking = () => (globalThis as any).speechSynthesis?.cancel();
