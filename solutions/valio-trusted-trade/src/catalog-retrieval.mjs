/**
 * Valio Aimo retrieval port. Discovery is advisory: only the existing trade
 * core is allowed to decide SKU eligibility, price, inventory and mandates.
 * The local implementation is deliberately lexical, never a fake embedding.
 */
import { createHash } from 'node:crypto';

export class RetrievalFault extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'RetrievalFault';
    this.code = code;
    this.status = status;
  }
}

const aliases = new Map([
  ['laktoositon', ['lactose', 'free']], ['laktoositonta', ['lactose', 'free']],
  ['maito', ['milk']], ['maitoa', ['milk']], ['maitojuoma', ['milk']],
  ['kaurajuoma', ['oat', 'drink']], ['kaurajuomaa', ['oat', 'drink']],
  ['kauramaito', ['oat', 'drink']], ['kaura', ['oat']],
  ['juoma', ['drink']],
  ['beverage', ['drink']], ['organic', ['organic']], ['luomu', ['organic']],
]);
const stop = new Set(['a', 'an', 'the', 'with', 'for', 'to', 'of', 'and', 'ja', 'tai', 'sekä', 'tarvitsen', 'haluan', 'etsin']);

export function validateCatalogQuery(raw) {
  if (typeof raw !== 'string' || raw.length < 2 || raw.length > 160 || /[\u0000-\u001f\u007f]/.test(raw)) {
    throw new RetrievalFault('INVALID_SEARCH_QUERY', 'Provide a 2–160 character product search without control characters.');
  }
  const query = raw.normalize('NFKC').trim();
  if (query.length < 2) throw new RetrievalFault('INVALID_SEARCH_QUERY', 'Product search is empty.');
  return query;
}

const tokenize = (input) => input.toLocaleLowerCase('fi').match(/[\p{L}\p{N}]+/gu) ?? [];
const expand = (input) => [...new Set(tokenize(input).filter((term) => !stop.has(term))
  .flatMap((term) => aliases.get(term) ?? [term]))];

/** Only known, source-backed fields may constrain a dietary search. */
export function resolveSearchConstraints(query) {
  const lower = query.toLocaleLowerCase('fi');
  const unsupported = /(?:^|[^\p{L}])(?:maidoton|maidotonta|gluteeniton|gluteenitonta|pähkinätön|pähkinätöntä|munaton|munatonta|allergiaton|allergiavapaa|vegan|vegaani|dairy[ -]free|gluten[ -]free|nut[ -]free|egg[ -]free|allergen[ -]free|non[ -]?dairy|dairy[ -]less|milk[ -]free|ei[ -]maitoa)(?=$|[^\p{L}])/iu;
  // This is not a general natural-language safety parser. Explicitly abstain
  // from negation/allergy/intolerance and unrecognized "-free" claims. Keep
  // one supported positive claim (lactose-free) for the typed fixture field.
  const withoutKnownLactoseClaim = lower.replace(/lactose[ -]free/giu, 'lactosefree')
    .replace(/laktoositon(?:ta)?/giu, 'lactosefree');
  const unverifiedTokens = tokenize(withoutKnownLactoseClaim);
  const unsafeWords = new Set(['no', 'not', 'without', 'avoid', 'avoiding', 'ei', 'ilman',
    'välttää', 'välttävä', 'allergy', 'allergies', 'allergic', 'allergia', 'allerginen',
    'non', 'nondairy', 'intolerance', 'intolerant', 'intoleranssi', 'celiac', 'keliakia']);
  const unknownClaim = unverifiedTokens.some((term) => unsafeWords.has(term) ||
    /allerg|intoler|keliaki|celiac|anafyl|free|(?:ton|tön|tonta|töntä)$/u.test(term) && term !== 'lactosefree');
  if (unsupported.test(lower) || unknownClaim) {
    return { abstainReason: 'UNVERIFIED_DIETARY_CONSTRAINT', requiredFamily: null, requiredLactoseFree: null };
  }
  const oat = /(?:^|[^\p{L}])(?:oat|kaura|kauramaito|kaurajuoma|kaurajuomaa)(?=$|[^\p{L}])/iu.test(lower);
  const milk = /(?:^|[^\p{L}])(?:milk|maito|maitoa|maitojuoma)(?=$|[^\p{L}])/iu.test(lower);
  const lactoseFree = /(?:^|[^\p{L}])(?:lactose[ -]free|laktoositon|laktoositonta)(?=$|[^\p{L}])/iu.test(lower);
  return { abstainReason: null, requiredFamily: oat ? 'oat-drink' : milk ? 'dairy-milk' : null,
    requiredLactoseFree: lactoseFree ? true : null };
}

export function createFixtureCatalogSearch(catalogProvider) {
  if (typeof catalogProvider !== 'function') throw new TypeError('A read-only catalog provider is required.');
  return Object.freeze({
    async search({ query: raw, buyerId, limit = 5 } = {}) {
      if (buyerId !== 'helsinki-hotel-demo') throw new RetrievalFault('SCOPE_REFUSED', 'Only the fictional demo buyer is in this search scope.', 403);
      const query = validateCatalogQuery(raw);
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10) throw new RetrievalFault('INVALID_SEARCH_LIMIT', 'Limit must be 1–10.');
      const constraints = resolveSearchConstraints(query);
      if (constraints.abstainReason) {
        return { query, mode: 'FIXTURE_LEXICAL_NO_EMBEDDINGS', candidates: [],
          reason: constraints.abstainReason, requiresTradeCoreValidation: true };
      }
      // A GTIN is a product *identity*, never a fuzzy search input.
      if (/^(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})$/.test(query)) {
        return { query, mode: 'FIXTURE_LEXICAL_NO_EMBEDDINGS', candidates: [],
          reason: 'EXACT_GTIN_ROUTE_REQUIRED', requiresTradeCoreValidation: true };
      }
      const needle = query.toLocaleLowerCase('fi');
      const terms = expand(query);
      const candidates = catalogProvider().filter((product) =>
        (!constraints.requiredFamily || product.family === constraints.requiredFamily) &&
        (constraints.requiredLactoseFree === null || product.lactoseFree === constraints.requiredLactoseFree))
        .map((product) => {
        const productTerms = new Set(expand(`${product.name} ${product.family} ${product.certification ?? ''}`));
        const termMatches = terms.filter((term) => productTerms.has(term)).length;
        const skuExact = product.sku.toLocaleLowerCase('en') === needle;
        const nameExact = product.name.toLocaleLowerCase('en') === needle;
        const score = (skuExact ? 100 : 0) + (nameExact ? 60 : 0) + (terms.length ? termMatches / terms.length * 40 : 0);
        const snapshot = { sku: product.sku, name: product.name, family: product.family,
          version: product.version, gtin: product.gtin, certification: product.certification };
        return { sku: product.sku, name: product.name, family: product.family,
          lexicalScore: Math.round(score * 100) / 100,
          provenance: { sourceKind: 'INVENTED_FIXTURE', sourceRef: `fixture:aimo/${product.sku}`,
            sourceVersion: product.version, sourceSha256: createHash('sha256').update(JSON.stringify(snapshot)).digest('hex') },
          requiresTradeCoreValidation: true };
      }).filter((item) => item.lexicalScore > 0)
        .sort((a, b) => b.lexicalScore - a.lexicalScore || a.sku.localeCompare(b.sku))
        .slice(0, limit);
      return { query, mode: 'FIXTURE_LEXICAL_NO_EMBEDDINGS', candidates,
        reason: candidates.length ? 'RANKED_ADVISORY_CANDIDATES' : 'NO_SUPPORTED_MATCH',
        requiresTradeCoreValidation: true };
    },
  });
}
