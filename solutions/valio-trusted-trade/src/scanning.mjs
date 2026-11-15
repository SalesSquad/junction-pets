/**
 * Valio-only observation boundary. A scan is a candidate observation, never
 * proof of product origin, allergen suitability, delivery or spending rights.
 * Synthetic GTINs are fixture identifiers, not issued GS1 registrations.
 */
import { spawn } from 'node:child_process';

export class ScanFault extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'ScanFault';
    this.code = code;
    this.status = status;
  }
}

export function validateGtin(raw) {
  if (typeof raw !== 'string' || !/^(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})$/.test(raw.trim())) {
    throw new ScanFault('INVALID_GTIN', 'Enter an EAN-8, UPC-A, EAN-13 or GTIN-14 with ASCII digits only.');
  }
  const gtin = raw.trim();
  let sum = 0;
  for (let i = gtin.length - 2, weight = 3; i >= 0; i--, weight = weight === 3 ? 1 : 3) {
    sum += Number(gtin[i]) * weight;
  }
  if ((10 - sum % 10) % 10 !== Number(gtin.at(-1))) {
    throw new ScanFault('GTIN_CHECKSUM_FAILED', 'The barcode check digit is invalid.');
  }
  return gtin;
}

export function resolveGtin(catalog, raw) {
  const gtin = validateGtin(raw);
  const matches = catalog.filter((item) => item.gtin === gtin);
  if (matches.length > 1) throw new ScanFault('AMBIGUOUS_GTIN', 'Multiple products share this code; refuse to guess.', 409);
  if (!matches.length) throw new ScanFault('PRODUCT_NOT_FOUND', 'Valid barcode, but no verified match in this synthetic catalog.', 404);
  const item = matches[0];
  return { gtin, sku: item.sku, name: item.name, family: item.family,
    unitsAvailable: item.unitsAvailable, priceCents: item.priceCents,
    stockVersion: item.version, mode: 'INVENTED_FIXTURE_EXACT_GTIN',
    observation: 'CHECK_DIGIT_AND_EXACT_CATALOG_MATCH_ONLY',
    authority: 'NONE_SCAN_CANNOT_AUTHORIZE_TRADE' };
}

/** Extract only two explicitly supported demo needs. No allergen inference. */
export function parseRecipeObservation(raw) {
  if (typeof raw !== 'string' || raw.length > 8_192) {
    throw new ScanFault('INVALID_OCR_TEXT', 'OCR text must be at most 8192 characters.');
  }
  const candidates = [];
  const patterns = [
    { family: 'dairy-milk', re: /^\s*([0-9]{1,5})\s*(?:l|liters?|litres?)\s+(?:of\s+)?(?:lactose[- ]free\s+(?:dairy\s+)?milk|laktoositon(?:ta)?\s+maito(?:a)?)\s*$/i },
    { family: 'oat-drink', re: /^\s*([0-9]{1,5})\s*(?:l|liters?|litres?)\s+(?:of\s+)?(?:oat\s+(?:milk|drink)|kaurajuoma(?:a)?)\s*$/i },
  ];
  for (const line of raw.split(/\r?\n/).slice(0, 80)) {
    for (const pattern of patterns) {
      const match = line.match(pattern.re);
      if (!match) continue;
      const quantityLitres = Number(match[1]);
      if (quantityLitres > 0 && quantityLitres <= 10_000) {
        candidates.push({ family: pattern.family, quantityLitres, lactoseFree: true, sourceLine: line.trim(), requiresHumanReview: true });
      }
    }
  }
  const duplicateFamilies = [...new Set(candidates.map((c) => c.family).filter((family) => candidates.filter((c) => c.family === family).length > 1))];
  return { candidates, duplicateFamilies, rawExcerpt: raw.slice(0, 1200),
    evidence: 'OCR_TEXT_UNTRUSTED_REQUIRES_USER_REVIEW',
    warning: 'Only two synthetic product families supported. OCR text never grants purchase rights or proves allergen safety.' };
}

/** Optional Tesseract on the app server. Input stays ephemeral in server memory. */
export async function recognizeImage(buffer, mediaType, { binary = 'tesseract', timeoutMs = 6000 } = {}) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 8 || buffer.length > 1_500_000) {
    throw new ScanFault('INVALID_IMAGE', 'An image must be 8 bytes–1.5 MB.');
  }
  const png = mediaType === 'image/png' && buffer.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
  const jpeg = mediaType === 'image/jpeg' && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff;
  if (!png && !jpeg) throw new ScanFault('INVALID_IMAGE', 'Only valid PNG or JPEG images are accepted.');
  return new Promise((resolve, reject) => {
    const child = spawn(binary, ['stdin', 'stdout', '-l', 'eng', '--psm', '6'], { stdio: ['pipe', 'pipe', 'ignore'], shell: false });
    let result = '';
    let finished = false;
    const finish = (error, value) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (error) reject(error); else resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      finish(new ScanFault('OCR_TIMED_OUT', 'Local image recognition timed out.', 503));
    }, timeoutMs);
    child.on('error', () => finish(new ScanFault('OCR_UNAVAILABLE', 'Local Tesseract OCR is not installed; use a typed observation.', 503)));
    child.stdout.on('data', (chunk) => {
      result += chunk.toString('utf8');
      if (result.length > 8_192) {
        child.kill('SIGKILL');
        finish(new ScanFault('OCR_LIMIT_EXCEEDED', 'Recognized text exceeded the local review limit.', 413));
      }
    });
    child.on('close', (code) => {
      if (code !== 0) finish(new ScanFault('OCR_FAILED', 'Local image recognition failed; review manually.', 422));
      else finish(null, { text: result.trim(), ...parseRecipeObservation(result) });
    });
    child.stdin.on('error', () => { /* handled by close/error */ });
    child.stdin.end(buffer);
  });
}
