/**
 * Compare a quoted duration to an approximate elapsed time. This is arithmetic,
 * not a legal deadline or an eligibility determination: starting events,
 * national rules, exceptions and the source provision still need checking.
 */
export interface Verdict {
  periodDays: number;
  elapsedDays: number;
  arithmeticWithin: boolean;
  daysLeft: number;
  text: string;
}

const DAYS = { day: 1, week: 7, month: 30.4375, year: 365.25 } as const;
type Unit = keyof typeof DAYS;
const UNIT_WORDS: Array<[RegExp, Unit]> = [
  [/^(days?|päivää|päivän|päivä|tage[n]?|tag)$/i, "day"],
  [/^(weeks?|viikkoa|viikon|viikko|wochen?)$/i, "week"],
  [/^(months?|kuukautta|kuukauden|kuukausi|monate[n]?|monat)$/i, "month"],
  [/^(years?|vuotta|vuoden|vuosi|jahre[n]?|jahr)$/i, "year"],
];
const NUMBER_WORDS: Record<string, number> = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, yksi: 1, kaksi: 2, kolme: 3, neljä: 4, viisi: 5, kuusi: 6, seitsemän: 7, kahdeksan: 8, yhdeksän: 9, kymmenen: 10, ein: 1, eine: 1, einem: 1, einer: 1, zwei: 2, drei: 3, vier: 4, fünf: 5, sechs: 6, sieben: 7, acht: 8, neun: 9, zehn: 10 };
const N = "(\\d{1,3}|[a-zäöüß]{1,10})";
const U = "([a-zäöüß]{3,10})";
const PATTERNS = [
  new RegExp(`\\b${N}\\s+${U}\\s+(?:ago|sitten|später|her)\\b`, "iu"), // 9 days ago, 10 päivää sitten
  new RegExp(`\\b(?:after|nach|vor)\\s+${N}\\s+${U}\\b`, "iu"), // after 18 months, nach 26 Monaten, vor 10 Tagen
  new RegExp(`\\b${N}\\s+${U}\\s+(?:jälkeen|after|since)\\b`, "iu"), // 14 kuukauden jälkeen
  new RegExp(`\\b(?:about|around|almost|over)\\s+${N}\\s+${U}\\s+(?:ago|ago)\\b`, "iu"),
];

function toDays(n: string, u: string): number | undefined {
  const value = /^\d+$/.test(n) ? Number(n) : NUMBER_WORDS[n.toLowerCase()];
  const unit = UNIT_WORDS.find(([re]) => re.test(u))?.[1];
  return value === undefined || !unit ? undefined : value * DAYS[unit];
}

export function elapsedDays(question: string): number | undefined {
  for (const re of PATTERNS) {
    const m = re.exec(question);
    const d = m ? toDays(m[1]!, m[2]!) : undefined;
    if (d !== undefined) return d;
  }
  return undefined;
}

export function timeVerdict(question: string, amount?: { kind: string; value: number; unit: string } | null): Verdict | undefined {
  if (!amount || amount.kind !== "duration" || !Object.hasOwn(DAYS, amount.unit) || !Number.isFinite(amount.value) || amount.value <= 0 || amount.value > 1000) return undefined;
  const elapsed = elapsedDays(question);
  if (elapsed === undefined) return undefined;
  const periodDays = amount.value * DAYS[amount.unit as Unit];
  const within = elapsed <= periodDays;
  const daysLeft = Math.round(periodDays - elapsed);
  const round = (d: number) => (d >= 365 ? `${(d / 365.25).toFixed(d % 365.25 < 30 ? 0 : 1)} years` : d >= 60 ? `${Math.round(d / 30.4375)} months` : `${Math.round(d)} days`);
  return {
    periodDays: Math.round(periodDays),
    elapsedDays: Math.round(elapsed),
    arithmeticWithin: within,
    daysLeft,
    text: `Approximate arithmetic: ${round(elapsed)} elapsed versus a stated period of ${round(periodDays)}. This does not determine a legal deadline or eligibility. Check the actual starting event, applicable law and exceptions before relying on it.`,
  };
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Calendar arithmetic from a supplied date, not a verified legal deadline. */
export function lastDay(eventDate: string, amount?: { kind: string; value: number; unit: string } | null): string | undefined {
  if (!amount || amount.kind !== "duration" || !Number.isSafeInteger(amount.value) || amount.value <= 0 || amount.value > 1000 || !/^\d{4}-\d{2}-\d{2}$/.test(eventDate)) return undefined;
  const d = new Date(`${eventDate}T00:00:00Z`);
  if (!Number.isFinite(d.getTime()) || d.toISOString().slice(0, 10) !== eventDate || d.getUTCFullYear() < 1900) return undefined;
  if (amount.unit === "day") d.setUTCDate(d.getUTCDate() + amount.value);
  else if (amount.unit === "month" || amount.unit === "year") {
    // Calendar arithmetic that never overflows into the next month: 31 Jan + 1 month is 28 (or 29) Feb, the
    // earlier calendar date; this is not a verified legal deadline.
    const day = d.getUTCDate();
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + amount.value * (amount.unit === "year" ? 12 : 1));
    d.setUTCDate(Math.min(day, new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()));
  } else return undefined;
  return Number.isFinite(d.getTime()) && d.getUTCFullYear() <= 9999 ? iso(d) : undefined;
}

/** An all-day calendar event (RFC 5545) the person can open in any calendar app. Text is escaped, lines folded at 75 octets. */
export function icsEvent(o: { summary: string; date: string; description: string; uid: string; stamp: string }): string {
  if ([o.summary, o.description].some(text => typeof text !== "string" || text.length > 4000 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text))) throw new TypeError("Invalid calendar text");
  const esc = (t: string) => t.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r\n|\r|\n/g, "\\n");
  const fold = (line: string) => {
    const encoder = new TextEncoder(); let result = "", used = 0;
    for (const character of line) {
      const bytes = encoder.encode(character).length;
      if (used + bytes > 75) { result += "\r\n "; used = 1; }
      result += character; used += bytes;
    }
    return result;
  };
  if (typeof o.uid !== "string" || typeof o.stamp !== "string" || !/^[A-Za-z0-9._@-]{1,150}$/.test(o.uid) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(o.stamp) || !Number.isFinite(Date.parse(o.stamp))) throw new TypeError("Invalid calendar identity or timestamp");
  const d = new Date(`${o.date}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(o.date) || !Number.isFinite(d.getTime()) || iso(d) !== o.date) throw new TypeError("Invalid calendar date");
  const day = o.date.replace(/-/g, "");
  const next = new Date(`${o.date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  if (next.getUTCFullYear() > 9999) throw new TypeError("Calendar date is out of range");
  return [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Internet Butler//Then Now Next//EN", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
    fold(`UID:${o.uid}`), fold(`DTSTAMP:${o.stamp.replace(/[-:]/g, "").replace(/\.\d+/, "")}`), `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${iso(next).replace(/-/g, "")}`,
    fold(`SUMMARY:${esc(o.summary)}`), fold(`DESCRIPTION:${esc(o.description)}`),
    "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Verify the estimated date and applicable rules", "TRIGGER:-P1D", "END:VALARM", "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
}
