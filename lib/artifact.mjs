import {createHash} from 'node:crypto';

export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') + '}';
}
export function sha256(value) {return createHash('sha256').update(value).digest('hex');}

export function safeHttps(value) {
  if (typeof value !== 'string' || value.length > 2048 || /[\u0000-\u0020\u007f\\]/.test(value)) return false;
  try {const url = new URL(value);return url.protocol === 'https:' && !url.username && !url.password && !!url.hostname && !url.hash;} catch {return false;}
}
