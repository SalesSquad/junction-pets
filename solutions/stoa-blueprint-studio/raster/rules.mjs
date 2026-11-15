/**
 * Deterministic counting from OCR tokens on Finnish architectural floor plans.
 * Door tags carry a ~2 m height (e.g. "9x21/O", "8x19", "PO/O 9x21"); window tags
 * use other WxH decimetre sizes (e.g. "13x12", "6x6"). Room types come from the
 * standard abbreviations (MH, KH, WC, S, K ...). Every count lists its token boxes.
 */
const SIZE_TAG = /(?<![\d,.])(\d{1,2})\s*[xX×х]\s*(\d{1,2})(?![\d,])/;

export function classifyTag(text) {
  const m = String(text).match(SIZE_TAG);
  if (!m) return null;
  const w = Number(m[1]), h = Number(m[2]);
  if (h >= 19 && h <= 24 && w >= 5 && w <= 30) return 'door';
  if (h >= 3 && h <= 18 && w >= 3 && w <= 40) return 'window';
  return null;
}

const ROOMS = {
  bedroom: ['MH', 'MAKUUHUONE', 'MAKUUH'],
  bathroom: ['KH', 'PH', 'KPH', 'PESUH', 'SH', 'KYLPYH', 'PESUHUONE', 'KYLPYHUONE', 'SUIHKUH'],
  wcRoom: ['WC'],
  sauna: ['S', 'SAUNA', 'LH', 'LÖYLYH'],
  kitchen: ['K', 'KK', 'KT', 'AK', 'TUPAK', 'KEITTIÖ', 'KEITTOKOMERO', 'TUPAKEITTIÖ', 'KEITTIÖTILA', 'AVOK', 'AVOKEITTIÖ'],
  balcony: ['PARV', 'PARVEKE', 'LASITETTU', 'LASIT', 'LP', 'RANSKALAINEN'],
};
const WORD_TO_ROOM = new Map(Object.entries(ROOMS).flatMap(([k, ws]) => ws.map(w => [w, k])));

/** Room categories named by a token: the label must lead the token (e.g. "MH", "MH/TYÖH", "S 3,8 m²"). */
export function roomCategories(text) {
  const words = String(text).toUpperCase().replace(/0(?=[A-ZÅÄÖ])/g, 'O').split(/[^A-ZÅÄÖ]+/).filter(Boolean);
  if (!words.length || words.length > 3) return [];
  const lead = WORD_TO_ROOM.get(words[0]);
  if (!lead) return [];
  // Single-letter labels (S, K) must stand alone or be followed only by an area value.
  if (words[0].length === 1 && !/^\s*[SK]\s*(\d|$)/i.test(String(text).trim())) return [];
  const cats = new Set([lead]);
  for (const w of words.slice(1)) { const c = WORD_TO_ROOM.get(w); if (c && w.length > 1) cats.add(c); }
  // "LASITETTU PARVEKE" is one balcony.
  return [...cats];
}

const FLOOR_TITLE = /\b([1-9])\s*\.?\s*(KRS|KERROS)\b|\bKELLARI(KERROS)?\b|\bPOHJAKERROS\b|\bULLAKKO(KERROS)?\b/i;

/** Map an (English or Finnish) sponsor question to a deterministic counting rule. */
export function ruleFor(question) {
  const q = question.toLowerCase();
  if (/\bdoors?\b|\bovi|ovia|ovien/.test(q)) return 'door';
  if (/\bwindows?\b|ikkun/.test(q)) return 'window';
  if (/toilet bowls?|wc seats?|wc-istu/.test(q)) return null;               // symbol: vision model
  if (/sinks?|wash basins?|pesualla|tiskialla|pesu- ja tiski/.test(q)) return null;
  if (/showers?|bathtubs?|suihku|kylpyamme/.test(q)) return null;
  // Bathroom questions mention "not counting separate WC rooms", so test them first.
  if (/bathrooms?|washrooms?|kylpyhuone|pesuhuone/.test(q)) return 'bathroom';
  if (/separate wc rooms?|toilet rooms?|erillis/.test(q)) return 'wcRoom';
  if (/bedrooms?|makuuhuone/.test(q)) return 'bedroom';
  if (/saunas?/.test(q)) return 'sauna';
  if (/kitchens?|keitti/.test(q)) return 'kitchen';
  if (/balcon|parvek/.test(q)) return 'balcony';
  if (/floors? \(storeys\)|storeys|kerros/.test(q)) return 'floors';
  return null;
}

export function countByRule(rule, tokens) {
  let evidence;
  if (rule === 'door' || rule === 'window') evidence = tokens.filter(t => classifyTag(t.text) === rule);
  else if (rule === 'floors') {
    const titles = tokens.filter(t => FLOOR_TITLE.test(t.text));
    const distinct = new Map(titles.map(t => [t.text.toUpperCase().replace(/\s|\./g, ''), t]));
    evidence = [...distinct.values()];
    return { answer: Math.max(1, evidence.length), evidence };
  } else evidence = tokens.filter(t => roomCategories(t.text).includes(rule));
  return { answer: evidence.length, evidence };
}
