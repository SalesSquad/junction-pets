/** Hosts that publish the text of legislation, regulations or court decisions (official or full-text legal databases). */
const LEGAL_TEXT_HOSTS = [
  "eur-lex.europa.eu", "curia.europa.eu", "legislation.gov.uk", "gesetze-im-internet.de", "legifrance.gouv.fr", "finlex.fi",
  "ecfr.gov", "govinfo.gov", "uscode.house.gov", "federalregister.gov", "congress.gov", "leginfo.legislature.ca.gov",
  "nysenate.gov", "legislation.nsw.gov.au", "legislation.vic.gov.au", "legislation.gov.au", "ontario.ca/laws",
  "laws-lois.justice.gc.ca", "gazette.gc.ca", "irishstatutebook.ie", "japaneselawtranslation.go.jp", "elaws.e-gov.go.jp",
  "law.cornell.edu", "austlii.edu.au", "canlii.org", "bailii.org", "lawplayer.com", "law.justia.com",
];

/**
 * Pages on legal hosts that explain the law instead of stating it. Found by a typed judge
 * (bench/DECISIONS-EVAL.md): all 16 allowlist false positives were EUR-Lex summaries or a GovInfo
 * publication. The rule lives in code; the judge only pointed at it.
 */
const NOT_LEGAL_TEXT = [/^\/[a-z]{2}\/legal-content\/summary\//, /\/legal-content\/[a-z]{2}\/lsu\//, /\/content\/pkg\/govpub-/];
const NOT_LEGAL_QUERY = /[?&]uri=legissum[:%]/i;

export function isLegalTextUrl(url: string): boolean {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    const path = u.pathname.toLowerCase();
    if (NOT_LEGAL_TEXT.some((re) => re.test(path)) || NOT_LEGAL_QUERY.test(u.search)) return false;
    return LEGAL_TEXT_HOSTS.some((e) => {
      const [h, ...p] = e.split("/");
      const prefix = p.length ? `/${p.join("/")}` : "";
      return (host === h || host.endsWith(`.${h}`)) && (!prefix || path.startsWith(prefix));
    });
  } catch {
    return false;
  }
}
