/**
 * "Am I still in time?" For a right that is a time limit (14 days to return, two years of guarantee), compare
 * the period the official text gives with how long ago the person says it happened ("12 days ago", "after
 * 18 months", "10 päivää sitten", "nach 26 Monaten"). Only phrases that say how long ago are read: a contract
 * "of 2 years" or a flight "3 hours late" is not elapsed time. Code only, no model; when nothing is said it
 * returns nothing rather than guess.
 */
export interface Verdict {
  periodDays: number;
  elapsedDays: number;
  within: boolean;
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
  if (!amount || amount.kind !== "duration" || !(amount.unit in DAYS)) return undefined;
  const elapsed = elapsedDays(question);
  if (elapsed === undefined) return undefined;
  const periodDays = amount.value * DAYS[amount.unit as Unit];
  const within = elapsed <= periodDays;
  const daysLeft = Math.round(periodDays - elapsed);
  const round = (d: number) => (d >= 365 ? `${(d / 365.25).toFixed(d % 365.25 < 30 ? 0 : 1)} years` : d >= 60 ? `${Math.round(d / 30.4375)} months` : `${Math.round(d)} days`);
  return {
    periodDays: Math.round(periodDays),
    elapsedDays: Math.round(elapsed),
    within,
    daysLeft,
    text: within ? `Still in time: about ${round(elapsed)} of ${round(periodDays)} used, about ${round(Math.max(0, periodDays - elapsed))} left.` : `Probably out of time: about ${round(elapsed)} have passed and the period is ${round(periodDays)}. Check whether another rule or a longer national period applies.`,
  };
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** The last day of a time-limit right counted from the event: 14 days from 5 Nov is 19 Nov; calendar months and years. */
export function lastDay(eventDate: string, amount?: { kind: string; value: number; unit: string } | null): string | undefined {
  if (!amount || amount.kind !== "duration" || !/^\d{4}-\d{2}-\d{2}$/.test(eventDate)) return undefined;
  const d = new Date(`${eventDate}T00:00:00Z`);
  if (amount.unit === "day") d.setUTCDate(d.getUTCDate() + amount.value);
  else if (amount.unit === "month" || amount.unit === "year") {
    // Calendar arithmetic that never overflows into the next month: 31 Jan + 1 month is 28 (or 29) Feb, the
    // earlier and therefore safer last day for a person who is counting down to it.
    const day = d.getUTCDate();
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + amount.value * (amount.unit === "year" ? 12 : 1));
    d.setUTCDate(Math.min(day, new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()));
  } else return undefined;
  return iso(d);
}

/** An all-day calendar event (RFC 5545) the person can open in any calendar app. Text is escaped, lines folded at 75 octets. */
export function icsEvent(o: { summary: string; date: string; description: string; uid: string; stamp: string }): string {
  const esc = (t: string) => t.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  const fold = (line: string) => (line.length <= 73 ? line : line.match(/.{1,73}/gu)!.join("\r\n "));
  const day = o.date.replace(/-/g, "");
  const next = new Date(`${o.date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Internet Butler//Then Now Next//EN", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
    `UID:${o.uid}`, `DTSTAMP:${o.stamp.replace(/[-:]/g, "").replace(/\.\d+/, "")}`, `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${iso(next).replace(/-/g, "")}`,
    fold(`SUMMARY:${esc(o.summary)}`), fold(`DESCRIPTION:${esc(o.description)}`),
    "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Last day is tomorrow", "TRIGGER:-P1D", "END:VALARM", "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
}
