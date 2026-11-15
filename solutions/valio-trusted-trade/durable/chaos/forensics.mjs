/** Bounded, redacted failure diagnostics; never dump PGDATA or connection URLs. */
import {open,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';

export function redactPgLine(input){
  return String(input)
    .replace(/postgres(?:ql)?:\/\/[^\s'"<>]+/gi,'postgres://[redacted]')
    .replace(/(password|authorization|token|api[_-]?key)\s*[:=]\s*['"]?[^\s'";,]+/gi,'$1=[redacted]')
    .slice(0,300);
}

export function summarizePgTail(text,maxLines=32){
  const lines=String(text).split(/\r?\n/)
    .filter(s=>/\b(LOG|ERROR|FATAL|PANIC|WARNING|CONTEXT|STATEMENT):|recovery|redo|interrupted|checkpoint/i.test(s));
  return lines.slice(-Math.max(1,Math.min(32,maxLines))).map(redactPgLine);
}

export async function captureOwnedPgFailure(logFile){
  const info=await stat(logFile);
  const bytes=Math.min(info.size,65536);
  const start=info.size-bytes;
  const fh=await open(logFile,'r');
  let contents;
  try {
    const buffer=Buffer.alloc(bytes);
    const {bytesRead}=await fh.read(buffer,0,bytes,start);
    contents=buffer.subarray(0,bytesRead);
  }finally{await fh.close();}
  return {totalLogBytes:info.size,readTailBytes:contents.length,
    tailSha256:createHash('sha256').update(contents).digest('hex'),
    recentEvents:summarizePgTail(contents.toString('utf8'))};
}
