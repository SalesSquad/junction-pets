/**
 * Deterministic data minimisation applied to every string before it leaves the device.
 * It removes identifiers that search and judgment never need, while keeping the dates and
 * amounts an errand depends on. It cannot remove names or street addresses reliably, so raw
 * documents are never sent: only the errand text and typed facts extracted on the device.
 */

const digitsOf = (s: string) => s.replace(/\D/g, "");

function luhnValid(num: string): boolean {
  let sum = 0;
  let double = false;
  for (let i = num.length - 1; i >= 0; i--) {
    let d = Number(num[i]);
    if (double) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    double = !double;
  }
  return sum % 10 === 0;
}

const DATE_LIKE = /^(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})$/;

interface Rule {
  label: string;
  pattern: RegExp;
  /** Return false to keep the match (a date or an amount, not an identifier). */
  accept?: (match: string) => boolean;
}

const RULES: Rule[] = [
  { label: "EMAIL", pattern: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g },
  { label: "IBAN", pattern: /\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b/g },
  {
    label: "CARD",
    pattern: /\b\d(?:[ -]?\d){12,18}\b/g,
    accept: (m) => luhnValid(digitsOf(m)),
  },
  // Nordic-style personal identity codes (DDMMYY-NNNC) and US social security numbers.
  { label: "ID", pattern: /\b\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]\b/g },
  { label: "ID", pattern: /\b\d{3}-\d{2}-\d{4}\b/g },
  {
    label: "PHONE",
    pattern: /(?:\+|\b)\d[\d ()-]{6,}\d\b/g,
    accept: (m) => {
      const t = m.trim();
      if (DATE_LIKE.test(t)) return false;
      const n = digitsOf(t).length;
      return t.startsWith("+") ? n >= 8 : n >= 9;
    },
  },
];

export interface Redaction {
  text: string;
  removed: Record<string, number>;
}

export function redact(input: string): Redaction {
  const removed: Record<string, number> = {};
  let text = input;
  for (const { label, pattern, accept } of RULES) {
    text = text.replace(pattern, (match) => {
      if (accept && !accept(match)) return match;
      removed[label] = (removed[label] ?? 0) + 1;
      return `[${label}]`;
    });
  }
  return { text, removed };
}

/** Recursively redact every string in a JSON-like value. */
export function redactDeep<T>(value: T): { value: T; removed: Record<string, number> } {
  const removed: Record<string, number> = {};
  const walk = (v: unknown): unknown => {
    if (typeof v === "string") {
      const r = redact(v);
      for (const [k, n] of Object.entries(r.removed)) removed[k] = (removed[k] ?? 0) + n;
      return r.text;
    }
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)]));
    return v;
  };
  return { value: walk(value) as T, removed };
}
