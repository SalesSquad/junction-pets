/** No retries, redirects, full ZIPs, automatic label creation, or unpinned extraction. */
import { inflateRawSync } from 'node:zlib';
import { open } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { boundedRead, sha256, PREVIEW_SHA, tempPath } from './run.mjs';
export const ARCHIVE = 'https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset-preview.zip';
export const MAX_RANGE = 1024 * 1024 - 1;
export const MAX_RAW = 6 * 1024 * 1024;
const LICENSE = 'junction-dataset-preview/data/swiss_dwellings/LICENSE.md';
const OLD = 'junction-dataset-preview/data/swiss_dwellings/site1102_bldg2242_floor10281.dxf';
const allowed = path => path === LICENSE || /^junction-dataset-preview\/data\/swiss_dwellings\/site\d+_bldg\d+_floor\d+\.dxf$/.test(path) && path !== OLD;
const fail = message => { throw new Error(message); };
import { spawnSync } from 'node:child_process';
export function range(start, end) {
  const suffix = start === null, length = suffix ? end : end-start+1;
  if (!Number.isSafeInteger(length) || length < 1 || length > MAX_RANGE || !suffix && (!Number.isSafeInteger(start) || start < 0)) fail('Unbounded range');
  const r = spawnSync('curl',['-fSs','--max-time','25','--max-filesize',String(length),'-r',suffix ? `-${length}` : `${start}-${end}`,'-D','-','-o','/dev/stderr',ARCHIVE],{maxBuffer:MAX_RANGE+32768});
  if (r.status !== 0 || r.error) fail(`Archive range unavailable (no retry): ${r.error?.message || r.stderr.toString().slice(0,300)}`);
  const headers = r.stdout.toString();
  const match = [...headers.matchAll(/^content-range:\s*bytes (\d+)-(\d+)\/(\d+)\s*$/gim)].at(-1);
  if (!/^HTTP\/\S+ 206\b/m.test(headers) || !match) fail('Server did not honor byte range');
  const [a,b,total] = match.slice(1).map(Number);
  if (b-a+1 !== length || r.stderr.length !== length || (suffix ? b !== total-1 : a !== start || b !== end)) fail('Range response mismatch');
  return { bytes:r.stderr, total };
}
export function parseDirectory(bytes) {
  const entries = []; let offset=0;
  while (offset < bytes.length) {
    if (offset+46 > bytes.length || bytes.readUInt32LE(offset)!==0x02014b50) fail('Malformed directory');
    const n=bytes.readUInt16LE(offset+28), extra=bytes.readUInt16LE(offset+30), comment=bytes.readUInt16LE(offset+32), next=offset+46+n+extra+comment;
    if (next > bytes.length) fail('Truncated directory');
    const path=bytes.subarray(offset+46,offset+46+n).toString('utf8');
    if (entries.some(e=>e.path===path)) fail('Duplicate ZIP entry');
    entries.push({path, flags:bytes.readUInt16LE(offset+8), method:bytes.readUInt16LE(offset+10), crc:bytes.readUInt32LE(offset+16), compressed:bytes.readUInt32LE(offset+20), raw:bytes.readUInt32LE(offset+24), disk:bytes.readUInt16LE(offset+34), localOffset:bytes.readUInt32LE(offset+42)});
    offset=next;
  }
  return entries;
}
export function validateEntry(e) {
  if (!e || !allowed(e.path) || e.disk || (e.flags & ~0x808) || ![0,8].includes(e.method) || !Number.isSafeInteger(e.compressed) || e.compressed < 1 || e.compressed > MAX_RANGE || !Number.isSafeInteger(e.raw) || e.raw < 1 || e.raw > (e.path===LICENSE ? 65536:MAX_RAW) || e.raw/e.compressed > 200) fail('Unsafe ZIP entry/path/size/compression');
}
export function crc32(bytes) {
  let crc=0xffffffff;
  for (const b of bytes) { crc ^= b; for(let i=0;i<8;i++) crc=(crc>>>1)^((crc&1)?0xedb88320:0); }
  return (crc^0xffffffff)>>>0;
}
export function unpack(e, bytes) {
  validateEntry(e);
  if(bytes.length!==e.compressed) fail('Packed length mismatch');
  const raw=e.method===0 ? bytes : inflateRawSync(bytes,{maxOutputLength:e.raw});
  if(raw.length!==e.raw || crc32(raw)!==e.crc) fail('ZIP size/CRC mismatch');
  return raw;
}
export function readEntry(e, request) {
  validateEntry(e);
  // Two requests maximum per entry: local fixed header, then name+extra+payload.
  const h=request(e.localOffset,e.localOffset+29).bytes;
  if(h.readUInt32LE(0)!==0x04034b50 || h.readUInt16LE(6)!==e.flags || h.readUInt16LE(8)!==e.method) fail('Local ZIP header mismatch');
  const nameLength=h.readUInt16LE(26), extra=h.readUInt16LE(28), size=nameLength+extra+e.compressed;
  if(size>MAX_RANGE) fail('Entry range too large');
  const body=request(e.localOffset+30,e.localOffset+29+size).bytes;
  if(body.subarray(0,nameLength).toString('utf8')!==e.path) fail('Local entry name mismatch');
  return unpack(e,body.subarray(nameLength+extra));
}
export function inspect(request=range) {
  const tail=request(null,65536); let at=-1;
  for(let i=tail.bytes.length-22;i>=0;i--) if(tail.bytes.readUInt32LE(i)===0x06054b50 && i+22+tail.bytes.readUInt16LE(i+20)===tail.bytes.length){at=i;break;}
  if(at<0) fail('ZIP footer unavailable');
  const t=tail.bytes;
  if(t.readUInt16LE(at+4)||t.readUInt16LE(at+6)||t.readUInt16LE(at+8)!==t.readUInt16LE(at+10)) fail('Multi-disk ZIP unsupported');
  const length=t.readUInt32LE(at+12), start=t.readUInt32LE(at+16);
  if(length<1 || length>MAX_RANGE || start+length!==tail.total-tail.bytes.length+at) fail('Directory too large/ZIP64/malformed');
  const entries=parseDirectory(request(start,start+length-1).bytes);
  if(entries.length!==t.readUInt16LE(at+10)) fail('Directory count mismatch');
  return entries;
}
export async function fetchHoldout(args) {
  if(args.length===1 && args[0]==='--inspect') {
    const entries=inspect();
    console.log(JSON.stringify({ candidates:entries.filter(e=>allowed(e.path)), note:'Discovery only; review a distinct source and pin its original SHA in the manifest before extraction.' },null,2)); return;
  }
  if(args.length!==4 || args[0]!=='--manifest' || args[2]!=='--output') fail('Usage: --inspect OR --manifest reviewed.json --output /private/tmp/distinct.dxf');
  const manifest=JSON.parse(await boundedRead(args[1],1024*1024));
  if(manifest.status==='NO_REAL_HELDOUT_SOURCE') fail('NO_REAL_HELDOUT_SOURCE: no selected verified path/SHA');
  const s=manifest.source;
  if(!s || !allowed(s.archivePath) || s.archivePath===LICENSE || !/^[a-f0-9]{64}$/.test(s.sha256) || s.sha256===PREVIEW_SHA || s.license!=='CC BY 4.0' || !s.attribution) fail('Exact reviewed source path, SHA and license required');
  const output=await tempPath(args[3]);
  const entries=inspect();
  const license=readEntry(entries.find(e=>e.path===LICENSE),range).toString('utf8');
  if(!license.includes('CC BY 4.0')) fail('Swiss Dwellings license changed');
  const raw=readEntry(entries.find(e=>e.path===s.archivePath),range);
  if(sha256(raw)!==s.sha256 || raw.includes(0) || !raw.toString('utf8').match(/\bSECTION\b/)) fail('Original SHA/ASCII DXF mismatch');
  const handle=await open(output,'wx',0o600);
  try { await handle.writeFile(raw); } finally { await handle.close(); }
  console.log(JSON.stringify({output,selectedFilename:s.archivePath,sha256:sha256(raw),bytes:raw.length,license:'CC BY 4.0',licenseSha256:sha256(Buffer.from(license)),usage:'Noncommercial competition; local only; no redistribution',attribution:s.attribution}));
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) fetchHoldout(process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1;});
