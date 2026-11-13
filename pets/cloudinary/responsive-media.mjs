/** Offline media specification only: no Cloudinary syntax, account or network operations. */
const WIDTHS = new Set([160, 320, 640, 960, 1280, 1920]);
const FORMATS = new Set(['avif', 'webp', 'jpeg']);
const fail = message => { throw new TypeError(message); };
function exact(record, fields) {
  if (record === null || typeof record !== 'object' || Array.isArray(record)) fail('expected record');
  for (const key of Object.keys(record)) if (!fields.includes(key)) fail('unknown field');
  for (const key of fields) if (!Object.hasOwn(record, key)) fail('missing field');
}
function integer(value, min, max) {
  if (!Number.isSafeInteger(value) || value < min || value > max) fail('invalid integer range');
}
function label(value, max) {
  if (typeof value !== 'string' || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) fail('invalid text label');
}

export function planResponsiveMedia(jsonText) {
  if (typeof jsonText !== 'string' || jsonText.length > 16384) fail('expected bounded JSON text');
  let data;
  try { data = JSON.parse(jsonText); } catch { fail('invalid JSON text'); }
  exact(data, ['asset', 'variants']);
  const a = data.asset;
  exact(a, ['id', 'width', 'height', 'visibility', 'decorative', 'alt', 'metadata']);
  if (typeof a.id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(a.id)) fail('invalid local asset identifier');
  integer(a.width, 1, 16384); integer(a.height, 1, 16384);
  if (a.visibility !== 'public') fail('only declared public assets may be planned');
  if (typeof a.decorative !== 'boolean') fail('decorative must be boolean');
  label(a.alt, 500);
  if (a.decorative ? a.alt !== '' : !a.alt.trim()) fail('invalid alternative text for image purpose');
  exact(a.metadata, ['credit']); label(a.metadata.credit, 200);
  if (!Array.isArray(data.variants) || data.variants.length < 1 || data.variants.length > 18) fail('invalid variant count');
  const seen = new Set();
  const variants = data.variants.map(v => {
    exact(v, ['width', 'format', 'quality']);
    if (!WIDTHS.has(v.width)) fail('unsupported responsive width');
    if (!FORMATS.has(v.format)) fail('unsupported format');
    integer(v.quality, 1, 100);
    if (v.width > a.width) fail('upscale is not permitted');
    const height = Math.max(1, Math.round(v.width * a.height / a.width));
    if (height > 4096) fail('output height exceeds bound');
    const key = `${v.width}:${v.format}`;
    if (seen.has(key)) fail('duplicate width-format pair');
    seen.add(key);
    return {width:v.width, height, format:v.format, quality:v.quality, fit:'contain'};
  });
  variants.sort((x, y) => x.width - y.width || (x.format < y.format ? -1 : x.format > y.format ? 1 : 0));
  return {
    status:'planned', assetId:a.id, variants,
    publicMetadata:{alt:a.alt, credit:a.metadata.credit},
    transformationExecuted:false, deliveryVerified:false, pixelsInspected:false, rightsVerified:false,
  };
}
