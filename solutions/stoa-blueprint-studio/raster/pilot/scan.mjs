import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {open, mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest, readLines, roomAnnotation} from './reading.mjs';

const run = promisify(execFile);
const options = {timeout:30_000,maxBuffer:4*1024*1024};

async function boundedRead(path, max) {
  const handle = await open(path,'r');
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.size > max) throw new Error('Expected a bounded regular file.');
    const buffer = Buffer.alloc(max+1);
    let length = 0;
    while (length < buffer.length) {
      const {bytesRead} = await handle.read(buffer,length,buffer.length-length,length);
      if (!bytesRead) break;
      length += bytesRead;
    }
    if (length > max) throw new Error('File exceeds input limit.');
    return buffer.subarray(0,length);
  } finally { await handle.close(); }
}

export async function scan(path, page = 1) {
  if (!Number.isSafeInteger(page) || page < 1 || page > 1000) throw new Error('Invalid page number.');
  const source = await boundedRead(path,16*1024*1024);
  const dir = await mkdtemp(join(tmpdir(),'stoa-ocr-'));
  const png = join(dir,'page.png');
  try {
    if (source.subarray(0,5).toString() === '%PDF-') {
      const input = join(dir,'source.pdf');
      await writeFile(input,source);
      await run('pdftoppm',['-f',String(page),'-l',String(page),'-scale-to','2400','-singlefile','-png',input,join(dir,'page')],options);
    } else {
      if (page !== 1) throw new Error('PNG has one page.');
      await writeFile(png,source);
    }
    const raster = await boundedRead(png,16*1024*1024);
    if (raster.length < 24 || raster.subarray(0,8).toString('hex') !== '89504e470d0a1a0a' ||
        raster.toString('ascii',12,16) !== 'IHDR') throw new Error('Expected PNG or PDF.');
    const width = raster.readUInt32BE(16), height = raster.readUInt32BE(20);
    if (!width || !height || width > 4096 || height > 4096 || width*height > 8_000_000) {
      throw new Error('PNG dimensions exceed the raster budget.');
    }
    const {stdout} = await run('tesseract',[png,'stdout','-l','eng','--psm','11','tsv'],options);
    return {page,width,height,sourceSha256:digest(source),rasterSha256:digest(raster),lines:readLines(stdout,width,height)};
  } finally { await rm(dir,{recursive:true,force:true}); }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [file,room,page='1'] = process.argv.slice(2);
  if (!file || !room) throw new Error('Usage: node raster/pilot/scan.mjs file.png|file.pdf ROOM|--page-data [PAGE]');
  const result = await scan(file,Number(page));
  console.log(JSON.stringify(room === '--page-data' ? result : roomAnnotation(result,room),null,2));
}
