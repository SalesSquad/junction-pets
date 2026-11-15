/**
 * Byte-range reader for the public Stoa Junction preview ZIP.
 * Reads only the central directory and the requested entries; CRC-checks each
 * entry. Nothing is written to git; callers store files in a local cache.
 */
import { crc32, inflateRawSync } from 'node:zlib';

export const PREVIEW_URL = 'https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset-preview.zip';
export const PREFIX = 'junction-dataset-preview/';
const MAX_ENTRY = 160 * 1024 * 1024; // IFC models reach ~75 MB

async function range(url, start, end) {
  if (!(Number.isSafeInteger(start) && Number.isSafeInteger(end) && end >= start && end - start < MAX_ENTRY + 65536)) {
    throw new Error('Unbounded archive range.');
  }
  const res = await fetch(url, { headers: { Range: `bytes=${start}-${end}` }, redirect: 'follow', signal: AbortSignal.timeout(120_000) });
  if (res.status !== 206) throw new Error(`Range request failed: HTTP ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

export async function openPreview(url = PREVIEW_URL) {
  const head = await fetch(url, { method: 'HEAD', signal: AbortSignal.timeout(30_000) });
  const size = Number(head.headers.get('content-length'));
  if (!Number.isSafeInteger(size) || size < 100_000) throw new Error('Cannot determine archive size.');
  const tail = await range(url, size - 65536, size - 1);
  let eocd = -1;
  for (let i = tail.length - 22; i >= 0; i--) if (tail.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw new Error('ZIP directory footer missing.');
  const dirLength = tail.readUInt32LE(eocd + 12), dirOffset = tail.readUInt32LE(eocd + 16);
  const central = await range(url, dirOffset, dirOffset + dirLength - 1);
  const entries = new Map();
  for (let o = 0; o < central.length;) {
    if (central.readUInt32LE(o) !== 0x02014b50) throw new Error('Malformed ZIP directory.');
    const n = central.readUInt16LE(o + 28), x = central.readUInt16LE(o + 30), c = central.readUInt16LE(o + 32);
    const name = central.subarray(o + 46, o + 46 + n).toString('utf8');
    entries.set(name, {
      name, method: central.readUInt16LE(o + 10), crc: central.readUInt32LE(o + 16),
      compressed: central.readUInt32LE(o + 20), size: central.readUInt32LE(o + 24), localOffset: central.readUInt32LE(o + 42),
    });
    o += 46 + n + x + c;
  }
  async function read(name) {
    const e = entries.get(name.startsWith(PREFIX) ? name : PREFIX + name);
    if (!e) throw new Error(`Not in preview: ${name}`);
    if (e.size > MAX_ENTRY) throw new Error(`Entry exceeds ${MAX_ENTRY} bytes: ${name}`);
    const h = await range(url, e.localOffset, e.localOffset + 29);
    if (h.readUInt32LE(0) !== 0x04034b50) throw new Error('Malformed local header.');
    const start = e.localOffset + 30 + h.readUInt16LE(26) + h.readUInt16LE(28);
    const packed = await range(url, start, start + e.compressed - 1);
    const data = e.method === 0 ? packed : e.method === 8 ? inflateRawSync(packed) : null;
    if (!data) throw new Error(`Unsupported compression ${e.method}`);
    if ((crc32(data) >>> 0) !== e.crc) throw new Error(`CRC mismatch: ${name}`);
    return data;
  }
  return { size, entries, read };
}
