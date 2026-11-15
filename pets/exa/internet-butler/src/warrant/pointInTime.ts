/**
 * Official point-in-time legal text.
 *
 * A live page can change after a warrant is signed; Exa's snapshotAsOf is best-effort. Official
 * point-in-time endpoints are different: the text of a provision as it stood on a past date never
 * changes, so a quote pinned to such a URL can be re-checked by the receiver against exactly the same
 * version. They also answer the temporal question directly: which amount applied on the date of the
 * flight, the dismissal or the sale (bench/timelaw: date-blind checking accepts 9 % of historically
 * true claims; point-in-time checking 100 %).
 *
 *   eCFR versioner          https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{t}.xml?part={p}&section={s}
 *   legislation.gov.uk      https://www.legislation.gov.uk/{type}/{year}/{number}/{section path}/{date}/data.xml
 *   EUR-Lex (CELLAR)        http://publications.europa.eu/resource/celex/0{YYYY}{T}{NNNN}-{YYYYMMDD} (consolidated
 *                           version in force on that date, found by SPARQL), else the act as adopted (3{YYYY}{T}{NNNN})
 */
export type OfficialRef =
  | { source: "ecfr"; title: number; part: number | string; section: string }
  | { source: "ukleg"; path: string }
  | { source: "eurlex"; celex: string; article?: string };

export function pointInTimeUrl(ref: OfficialRef, date: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error(`date must be YYYY-MM-DD: ${date}`);
  if (ref.source === "eurlex") throw new Error("EUR-Lex needs the consolidated version list: use eurlexUrlOn()");
  return ref.source === "ecfr"
    ? `https://www.ecfr.gov/api/versioner/v1/full/${date}/title-${ref.title}.xml?part=${ref.part}&section=${encodeURIComponent(ref.section)}`
    : `https://www.legislation.gov.uk/${ref.path.replace(/^\/|\/$/g, "")}/${date}/data.xml`;
}

/** Is this URL an official point-in-time endpoint (and therefore immutable for past dates)? */
export function isPointInTimeUrl(url: string): boolean {
  return /^https?:\/\/publications\.europa\.eu\/resource\/celex\/[03]\d{4}[A-Z]\d{4}(-\d{8})?$/.test(url) || /^https:\/\/www\.ecfr\.gov\/api\/versioner\/v1\/full\/\d{4}-\d{2}-\d{2}\//.test(url) || /^https:\/\/www\.legislation\.gov\.uk\/.+\/\d{4}-\d{2}-\d{2}\/data\.xml$/.test(url);
}

/**
 * The date a pinned official URL speaks for. eCFR and legislation.gov.uk name the exact date ("exact");
 * a CELLAR consolidated version names the date it took effect, so it covers that date and later ("from").
 * The act as adopted (base CELEX) carries no date.
 */
export function pointInTimeDate(url: string): { date: string; kind: "exact" | "from" } | null {
  let m = url.match(/ecfr\.gov\/api\/versioner\/v1\/full\/(\d{4}-\d{2}-\d{2})\//) ?? url.match(/legislation\.gov\.uk\/.+\/(\d{4}-\d{2}-\d{2})\/data\.xml$/);
  if (m) return { date: m[1]!, kind: "exact" };
  m = url.match(/celex\/0\d{4}[A-Z]\d{4}-(\d{4})(\d{2})(\d{2})$/);
  return m ? { date: `${m[1]}-${m[2]}-${m[3]}`, kind: "from" } : null;
}

/** Text of an official XML response: legislation.gov.uk keeps the law in <Body>/<Schedules> (<EUBody> for retained EU law), eCFR in the section. */
export function officialText(url: string, xml: string): string {
  const scope = url.includes("legislation.gov.uk") ? (xml.match(/<(Body|EUBody|Schedules)[\s>][\s\S]*<\/(Body|EUBody|Schedules)>/)?.[0] ?? "") : xml;
  return scope
    .replace(/<(CommentaryRef|FootnoteRef)[^>]*\/>/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#163;|&pound;/g, "£").replace(/&#x2019;|&#8217;/g, "’")
    .replace(/&[a-z#0-9]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

type RawFetch = (url: string, init?: RequestInit) => Promise<Response>;

/** A FetchFn for the compiler and the receiver: point-in-time URLs come back as plain official text. */
export function officialFetch(raw: RawFetch = fetch, fallback?: (url: string) => Promise<string>): (url: string) => Promise<string> {
  return async (url) => {
    if (!isPointInTimeUrl(url)) {
      if (!fallback) throw new Error(`not an official point-in-time URL: ${url}`);
      return fallback(url);
    }
    const eu = url.includes("publications.europa.eu");
    // Official endpoints rate-limit (eCFR answers 429 under load): wait as told, or back off, up to 3 times.
    const get = async (accept?: string) => {
      for (let i = 0; ; i++) {
        const r = await raw(url, { headers: { "user-agent": "internet-butler-warrant/0.1", "accept-encoding": "gzip", ...(accept ? { accept, "accept-language": "eng" } : {}) } });
        if ((r.status !== 429 && r.status < 500) || i >= 3) return r;
        const wait = Number(r.headers?.get?.("retry-after")) * 1000 || 1000 * 2 ** i;
        await new Promise((res) => setTimeout(res, Math.min(wait, 15_000)));
      }
    };
    let res = await get(eu ? "application/xhtml+xml" : undefined);
    // CELLAR serves newer acts as XHTML and older ones as HTML only.
    if (eu && res.status === 404) res = await get("text/html");
    if (!res.ok) throw new Error(`${res.status} from ${url}`);
    return officialText(url, await res.text());
  };
}

// Point-in-time texts never change, and a version list changes at most daily: memoise per fetch function,
// so one Then · Now · Next answer does not ask the same endpoint three times. Failures are not kept.
const memo = new WeakMap<RawFetch, Map<string, { at: number; p: Promise<unknown> }>>();
function remember<T>(raw: RawFetch, key: string, ttlMs: number, make: () => Promise<T>): Promise<T> {
  let m = memo.get(raw);
  if (!m) memo.set(raw, (m = new Map()));
  const hit = m.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.p as Promise<T>;
  const p = make();
  m.set(key, { at: Date.now(), p });
  if (m.size > 64) m.delete(m.keys().next().value!);
  p.catch(() => m!.delete(key));
  return p;
}

/** Consolidated versions of an EU act (base CELEX like 32016R0679), oldest first, from the CELLAR SPARQL endpoint. */
export function eurlexVersions(celex: string, raw: RawFetch = fetch): Promise<Array<{ celex: string; date: string }>> {
  return remember(raw, `versions:${celex}`, 3_600_000, () => eurlexVersionsUncached(celex, raw));
}
async function eurlexVersionsUncached(celex: string, raw: RawFetch): Promise<Array<{ celex: string; date: string }>> {
  const m = celex.match(/^3(\d{4}[A-Z]\d{4})$/);
  if (!m) throw new Error(`base CELEX expected (e.g. 32016R0679): ${celex}`);
  const q = `PREFIX cdm: <http://publications.europa.eu/ontology/cdm#> SELECT DISTINCT ?celex ?date WHERE { ?w cdm:resource_legal_id_celex ?celex . FILTER(STRSTARTS(STR(?celex), "0${m[1]}-")) OPTIONAL { ?w cdm:act_consolidated_date ?date } } ORDER BY ?celex`;
  const res = await raw(`https://publications.europa.eu/webapi/rdf/sparql?query=${encodeURIComponent(q)}`, { headers: { accept: "application/sparql-results+json" } });
  if (!res.ok) throw new Error(`SPARQL ${res.status}`);
  const d = (await res.json()) as { results: { bindings: Array<{ celex: { value: string }; date?: { value: string } }> } };
  return d.results.bindings
    .map((b) => ({ celex: b.celex.value, date: b.date?.value ?? `${b.celex.value.slice(-8, -4)}-${b.celex.value.slice(-4, -2)}-${b.celex.value.slice(-2)}` }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** The URL of the EU act's text in force on `date`: the newest consolidated version on or before it, else the act as adopted. */
export async function eurlexUrlOn(celex: string, date: string, raw: RawFetch = fetch): Promise<string> {
  // An act cannot apply before the year it was adopted (CELEX 3YYYY…). Without this, the "act as adopted"
  // fallback answered a 2004 question with the 2007 Rail Passengers' Rights Regulation. Entry into force
  // can be later still; a date inside the adoption year is not caught here.
  const adopted = celex.match(/^3(\d{4})/)?.[1];
  if (adopted && date < `${adopted}-01-01`) throw new Error(`404 not in force: ${celex} was adopted in ${adopted}, after ${date}`);
  // If the version list is unavailable (the SPARQL endpoint has outages), the act as adopted is used.
  const v = (await eurlexVersions(celex, raw).catch(() => [] as Array<{ celex: string; date: string }>)).filter((x) => x.date <= date).at(-1);
  return `http://publications.europa.eu/resource/celex/${v ? v.celex : celex}`;
}

/** The provision's text on `date` (the law that applied to an event on that day), with its pinned URL. */
export async function lawOn(ref: OfficialRef, date: string, raw: RawFetch = fetch): Promise<{ url: string; date: string; text: string }> {
  let url = ref.source === "eurlex" ? await eurlexUrlOn(ref.celex, date, raw) : pointInTimeUrl(ref, date);
  let text: string;
  const get = (u: string) => remember(raw, `text:${u}`, 3_600_000, () => officialFetch(raw)(u));
  try {
    text = await get(url);
  } catch (err) {
    // Some listed consolidated versions are not served; the act as adopted is the documented fallback.
    if (ref.source !== "eurlex" || url.endsWith(ref.celex)) throw err;
    url = `http://publications.europa.eu/resource/celex/${ref.celex}`;
    text = await get(url);
  }
  if (ref.source === "eurlex" && ref.article) {
    // Keep the article: from its heading ("Article 7 Right to compensation", not a cross-reference such as
    // "in accordance with Article 7, unless") to the next article heading.
    const heading = (n: string) => new RegExp(`\\bArticle ${n}\\s+(?!of\\b)(?=[A-Z])`, "g");
    const starts = [...text.matchAll(heading(ref.article))].map((m) => m.index!);
    const i = starts.find((k) => !/\b(with|under|to|in|of|and)\s*$/i.test(text.slice(Math.max(0, k - 20), k))) ?? starts[0];
    if (i !== undefined) {
      const next = text.slice(i + 12).search(/\bArticle \d+[a-z]?\s+(?!of\b)(?=[A-Z])/);
      text = text.slice(i, next >= 0 ? i + 12 + next : undefined);
    }
  }
  return { url, date, text };
}
