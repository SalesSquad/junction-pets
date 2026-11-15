// Pre-registered source classifier for the citation-completion benchmark.
// Fixed before the first run (see git history); do not tune it on results.

/** Databases that publish the text of legislation, regulations or court decisions. */
const PRIMARY_LEGAL_HOSTS = [
  "eur-lex.europa.eu", "curia.europa.eu",
  "legislation.gov.uk",
  "gesetze-im-internet.de",
  "legifrance.gouv.fr",
  "finlex.fi",
  "ecfr.gov", "govinfo.gov", "uscode.house.gov", "federalregister.gov", "congress.gov",
  "leginfo.legislature.ca.gov",
  "nysenate.gov",
  "legislation.nsw.gov.au", "legislation.vic.gov.au", "legislation.gov.au",
  "ontario.ca/laws", "laws-lois.justice.gc.ca", "gazette.gc.ca",
  "irishstatutebook.ie",
  "japaneselawtranslation.go.jp", "elaws.e-gov.go.jp",
];
// Non-official but full-text legal databases (free legal information institutes).
const LEGAL_DB_HOSTS = ["law.cornell.edu", "austlii.edu.au", "canlii.org", "bailii.org", "lawplayer.com", "codes.findlaw.com", "law.justia.com"];

/** Government, regulator, court or EU-institution hosts (official, possibly secondary explanations). */
const OFFICIAL_SUFFIXES = [
  "europa.eu", ".gov", ".gov.uk", ".gov.au", ".gc.ca", "canada.ca", "ontario.ca", ".gouv.fr", "service-public.fr",
  ".bund.de", "bundesregierung.de", ".fi" /* checked below against a list */, ".gov.ie", "citizensinformation.ie",
  "ccpc.ie", ".go.jp", "nyc.gov", "ny.gov", "ca.gov", "nsw.gov.au", "vic.gov.au",
];
const FI_OFFICIAL = ["finlex.fi", "suomi.fi", "kela.fi", "vero.fi", "kkv.fi", "oikeus.fi", "ym.fi", "valtioneuvosto.fi", "edilex.fi"];

function hostPath(url) {
  try {
    const u = new URL(url);
    return { host: u.hostname.replace(/^www\./, "").toLowerCase(), path: u.pathname.toLowerCase() };
  } catch {
    return { host: "", path: "" };
  }
}

const matches = (host, path, entry) => {
  const [h, p] = entry.includes("/") ? [entry.split("/")[0], `/${entry.split("/").slice(1).join("/")}`] : [entry, ""];
  return (host === h || host.endsWith(`.${h}`)) && (!p || path.startsWith(p));
};

export function classify(url) {
  const { host, path } = hostPath(url);
  const primaryLegal = PRIMARY_LEGAL_HOSTS.some((e) => matches(host, path, e));
  const legalDb = LEGAL_DB_HOSTS.some((e) => matches(host, path, e));
  let official = primaryLegal;
  if (!official) {
    if (host.endsWith(".fi")) official = FI_OFFICIAL.some((e) => matches(host, path, e));
    else official = OFFICIAL_SUFFIXES.filter((s) => s !== ".fi").some((s) => (s.startsWith(".") ? host.endsWith(s) : host === s || host.endsWith(`.${s}`)));
  }
  return { host, primaryLegal, legalText: primaryLegal || legalDb, official };
}

/** Anchors: every group must match; any alternative within a group may match. */
export function anchorHit(highlights, anchors) {
  const text = highlights.join(" \n ").normalize("NFKC").replace(/ /g, " ").replace(/\s+/g, " ").toLowerCase();
  return anchors.every((group) => group.some((alt) => text.includes(alt.toLowerCase())));
}
