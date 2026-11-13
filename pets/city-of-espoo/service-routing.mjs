/** Fictional, offline public-service routing worksheet. No network or resident data.
 * Executable objects/Proxies are outside this plain-JSON contract, not sandboxed.
 */
const fail = () => {throw Error('malformed-or-unsupported-input');};

// Inspect descriptors before reading values. Never call caller getters, hooks,
// iterators, coercions or overridden array methods. Only private copies are used.
function snapshot(value, depth = 0, path = new Set(), budget = {nodes: 0}) {
  if (depth > 12 || ++budget.nodes > 10000) fail();
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') {if (value.length > 2000) fail(); return value;}
  if (typeof value === 'number') {if (!Number.isFinite(value)) fail(); return value;}
  if (typeof value !== 'object' || path.has(value)) fail();
  const array = Array.isArray(value);
  if (Object.getPrototypeOf(value) !== (array ? Array.prototype : Object.prototype)) fail();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some(key => typeof key !== 'string')) fail();
  for (const key of keys) if (!Object.hasOwn(descriptors[key], 'value')) fail();
  path.add(value);
  let result;
  if (array) {
    const length = descriptors.length.value;
    if (length > 30 || keys.length !== length + 1) fail();
    result = [];
    for (let i = 0; i < length; i++) {
      const descriptor = descriptors[String(i)];
      if (!descriptor || !descriptor.enumerable) fail();
      result.push(snapshot(descriptor.value, depth + 1, path, budget));
    }
  } else {
    if (keys.length > 20) fail();
    result = Object.create(null);
    for (const key of keys) {
      if (!descriptors[key].enumerable) fail();
      result[key] = snapshot(descriptors[key].value, depth + 1, path, budget);
    }
  }
  path.delete(value);
  return result;
}

function shape(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) fail();
}
function text(value) {if (typeof value !== 'string' || value.trim().length === 0 || value.length > 2000) fail();}
function list(value) {if (!Array.isArray(value) || value.length === 0 || value.length > 30) fail();}
function identifier(value, service = false) {
  if (typeof value !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) || value.length > 80
    || (service && !value.startsWith('fictional-'))) fail();
}
function instant(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) fail();
  const ms = Date.parse(value);
  if (!Number.isFinite(ms) || new Date(ms).toISOString() !== value) fail();
  return ms;
}
function sourceUrl(value) {
  if (value === null) return;
  text(value);
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.hostname !== 'fixtures.example.invalid' || url.username || url.password
    || url.port || url.search || url.hash || url.href !== value || !/^\/[a-z0-9/-]+$/.test(url.pathname)) fail();
}
function bilingual(value, inspect) {
  shape(value, ['fi', 'en']);
  for (const language of ['fi', 'en']) inspect(value[language], language);
}
function serviceCard(service, asOf) {
  shape(service, ['id', 'source', 'localizations', 'channels']);
  identifier(service.id, true);
  shape(service.source, ['kind', 'url', 'checkedAt']);
  if (service.source.kind !== 'invented-fixture') fail();
  sourceUrl(service.source.url);
  if (service.source.checkedAt !== null && instant(service.source.checkedAt) > asOf) fail();
  bilingual(service.localizations, (localized, language) => {
    shape(localized, ['language', 'serviceId', 'title', 'summary', 'nextSteps', 'unknowns']);
    if (localized.language !== language || localized.serviceId !== service.id) fail();
    text(localized.title); text(localized.summary);
    list(localized.nextSteps); localized.nextSteps.forEach(text);
    shape(localized.unknowns, ['availability', 'eligibility', 'accessibility']);
    Object.values(localized.unknowns).forEach(text);
  });
  list(service.channels);
  const ids = new Set();
  for (const channel of service.channels) {
    shape(channel, ['id', 'kind', 'accessibleText']); identifier(channel.id);
    if (ids.has(channel.id) || !['text', 'image', 'audio', 'video'].includes(channel.kind)) fail();
    ids.add(channel.id);
    bilingual(channel.accessibleText, value => {if (value !== null) text(value);});
  }
}
function fallbackCard(fallback) {
  shape(fallback, ['action', 'serviceId', 'localizations']);
  if (fallback.action !== 'ask-for-service-detail' || fallback.serviceId !== null) fail();
  bilingual(fallback.localizations, (localized, language) => {
    shape(localized, ['language', 'serviceId', 'title', 'message', 'nextStep']);
    if (localized.language !== language || localized.serviceId !== null) fail();
    text(localized.title); text(localized.message); text(localized.nextStep);
  });
}

export function checkServiceRouting(input) {
  const result = {
    status: 'invalid', language: null, serviceId: null, card: null, fallback: null,
    sourceAgeHours: null, issues: ['malformed-or-unsupported-input'], synthetic: true,
    realServiceAvailabilityVerified: false, accessibilityCertified: false,
    sourceFetched: false, authorization: false, companyEndorsed: false,
  };
  try {
    const x = snapshot(input);
    shape(x, ['schemaVersion', 'dataKind', 'request', 'asOf', 'maxSourceAgeHours', 'services', 'unknownFallback']);
    if (x.schemaVersion !== 1 || x.dataKind !== 'fictional-fixture') fail();
    shape(x.request, ['language', 'serviceId']); identifier(x.request.serviceId, true);
    if (!['fi', 'en'].includes(x.request.language)) fail();
    const asOf = instant(x.asOf);
    if (!Number.isSafeInteger(x.maxSourceAgeHours) || x.maxSourceAgeHours < 0 || x.maxSourceAgeHours > 720) fail();
    list(x.services);
    const ids = new Set();
    for (const service of x.services) {
      serviceCard(service, asOf);
      if (ids.has(service.id)) fail();
      ids.add(service.id);
    }
    fallbackCard(x.unknownFallback);
    const language = x.request.language;
    const service = x.services.find(candidate => candidate.id === x.request.serviceId);
    if (!service) {
      const localized = x.unknownFallback.localizations[language];
      return {...result, status: 'unknown-service', language, issues: ['service-not-in-fictional-catalog'],
        fallback: {action: 'ask-for-service-detail', serviceId: null,
          title: localized.title, message: localized.message, nextStep: localized.nextStep}};
    }
    const issues = [];
    if (service.source.url === null) issues.push('unknown-source-url');
    const ageMs = service.source.checkedAt === null ? null : asOf - instant(service.source.checkedAt);
    if (ageMs === null) issues.push('unknown-source-time');
    else if (ageMs > x.maxSourceAgeHours * 3600000) issues.push('stale-source');
    const sourceAgeHours = ageMs === null ? null : ageMs / 3600000;
    const channel = service.channels.find(candidate => candidate.accessibleText.fi !== null && candidate.accessibleText.en !== null);
    if (!channel) issues.push('no-accessible-text-channel');
    if (issues.length) return {...result, status: 'needs-review', language, sourceAgeHours, issues,
      fallback: {action: 'verify-official-guidance', serviceId: null,
        message: language === 'fi'
          ? 'Harjoituskortti ei riitä reititykseen. Tarkista oikea ajantasainen ohje ja saavutettava tekstivaihtoehto virallisesta lähteestä.'
          : 'The practice card is not sufficient for routing. Verify current actual guidance and an accessible text alternative in an official source.'}};
    const localized = service.localizations[language];
    return {...result, status: 'routed-fictional', language, serviceId: service.id, sourceAgeHours, issues,
      card: {title: localized.title, summary: localized.summary, nextSteps: [...localized.nextSteps],
        unknowns: {...localized.unknowns}, channelId: channel.id, accessibleText: channel.accessibleText[language],
        source: {...service.source}}};
  } catch {
    return result;
  }
}
