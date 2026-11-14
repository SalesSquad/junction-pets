/**
 * Fetch exactly one LICENSE-permitted sponsor DXF by HTTP byte ranges.
 * No full archive download, no sample checked into git, source SHA pinned.
 * Requires curl. Intended for competition evaluation and private/local demo.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { inflateRawSync } from 'node:zlib';

const URL = 'https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset-preview.zip';
const TARGET = 'junction-dataset-preview/data/swiss_dwellings/site1102_bldg2242_floor10281.dxf';
const EXPECTED_SHA256 = '4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d';
const output = resolve(process.argv[2] || join(tmpdir(), 'stoa-verified-sponsor-sample.dxf'));

function requestRange(start, end, cap = 1024 * 1024) {
  if (!(Number.isSafeInteger(start) && Number.isSafeInteger(end) && end >= start && end - start < cap)) throw new Error('Unbounded archive range.');
  return execFileSync('curl', ['-fLsS', '--max-time', '30', '-r', `${start}-${end}`, '--max-filesize', String(cap), URL], { maxBuffer: cap });
}
function findEntry(central, name) {
  let offset = 0;
  while (offset < central.length) {
    if (central.readUInt32LE(offset) !== 0x02014b50) throw new Error('Malformed ZIP directory.');
    const method = central.readUInt16LE(offset + 10);
    const compressed = central.readUInt32LE(offset + 20);
    const nameBytes = central.readUInt16LE(offset + 28);
    const extras = central.readUInt16LE(offset + 30);
    const comment = central.readUInt16LE(offset + 32);
    const localOffset = central.readUInt32LE(offset + 42);
    if (central.subarray(offset + 46, offset + 46 + nameBytes).toString('utf8') === name) return { method, compressed, localOffset };
    offset += 46 + nameBytes + extras + comment;
  }
  throw new Error(`Sponsor preview does not include ${name}.`);
}
function readEntry(entry) {
  const header = requestRange(entry.localOffset, entry.localOffset + 29, 64);
  if (header.readUInt32LE(0) !== 0x04034b50) throw new Error('Malformed ZIP source header.');
  const start = entry.localOffset + 30 + header.readUInt16LE(26) + header.readUInt16LE(28);
  const packed = requestRange(start, start + entry.compressed - 1, 512 * 1024);
  if (entry.method === 0) return packed;
  if (entry.method === 8) return inflateRawSync(packed);
  throw new Error(`ZIP compression ${entry.method} unsupported.`);
}

const headers = execFileSync('curl', ['-fsSI', '--max-time', '25', URL], { encoding: 'utf8', maxBuffer: 32 * 1024 });
const size = Number([...headers.matchAll(/^content-length:\s*(\d+)\s*$/gim)].at(-1)?.[1]);
if (!Number.isSafeInteger(size) || size < 100000) throw new Error('Cannot determine sponsor ZIP byte length.');
const tail = requestRange(size - 65536, size - 1);
let eocd = -1;
for (let i = tail.length - 22; i >= 0; i--) if (tail.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
if (eocd < 0) throw new Error('ZIP directory footer missing.');
const dirLength = tail.readUInt32LE(eocd + 12);
const dirOffset = tail.readUInt32LE(eocd + 16);
const central = requestRange(dirOffset, dirOffset + dirLength - 1);
const drawing = readEntry(findEntry(central, TARGET));
if (drawing.length > 6 * 1024 * 1024) throw new Error('Sponsor sample exceeds DXF engine limit.');
const digest = createHash('sha256').update(drawing).digest('hex');
if (digest !== EXPECTED_SHA256) throw new Error('Sponsor sample changed; verify licence and evaluation evidence before use.');
const license = readEntry(findEntry(central, 'junction-dataset-preview/data/swiss_dwellings/LICENSE.md')).toString('utf8');
if (!license.includes('CC BY 4.0')) throw new Error('Swiss Dwellings licence changed: manual review required.');
await writeFile(output, drawing, { flag: 'wx', mode: 0o600 });
console.info(`Verified sponsor ASCII DXF: ${output}`);
console.info(`SHA256: ${digest}`);
console.info(`Source: ${TARGET}`);
console.info('Credit: Swiss Dwellings v3.0.0 (Archilyse AG contributors), CC BY 4.0, doi:10.5281/zenodo.7788422; sponsor-rendered derivative.');
console.info('For local Junction evaluation only. No source file committed or redistributed.');
