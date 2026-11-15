/** Deliberately narrow browser adapter for the unchanged synthetic trade domain. */
import { ed25519 } from '@noble/curves/ed25519.js';
import { sha256 } from '@noble/hashes/sha2.js';
const bad=()=>{throw Object.assign(new Error('Unsupported or malformed browser crypto operation.'),{code:'BROWSER_CRYPTO_UNSUPPORTED'});};
const bytes=value=>typeof value==='string'?new TextEncoder().encode(value):value instanceof Uint8Array?value:value instanceof ArrayBuffer?new Uint8Array(value):bad();
export class Buffer extends Uint8Array {
  static from(value,encoding='utf8'){
    if(typeof value!=='string')return new Buffer(bytes(value));
    if(encoding==='utf8'||encoding==='utf-8')return new Buffer(new TextEncoder().encode(value));
    if(encoding==='hex'){if(value.length%2||!/^[a-f0-9]*$/i.test(value))bad();return new Buffer(value.match(/../g)?.map(pair=>parseInt(pair,16))??[]);}
    if(encoding==='base64'||encoding==='base64url'){
      if(!/^[A-Za-z0-9_+/=-]*$/.test(value))bad();
      const decoded=atob(value.replace(/-/g,'+').replace(/_/g,'/'));
      return new Buffer(Uint8Array.from(decoded,char=>char.charCodeAt(0)));
    }return bad();
  }
  static concat(values){const output=new Buffer(values.reduce((sum,value)=>sum+value.length,0));let offset=0;for(const value of values){output.set(value,offset);offset+=value.length;}return output;}
  toString(encoding='utf8'){
    if(encoding==='utf8'||encoding==='utf-8')return new TextDecoder().decode(this);
    if(encoding==='hex')return Array.from(this,value=>value.toString(16).padStart(2,'0')).join('');
    if(encoding==='base64'||encoding==='base64url'){
      let text='';for(let i=0;i<this.length;i+=4096)text+=String.fromCharCode(...this.subarray(i,i+4096));
      const encoded=btoa(text);return encoding==='base64url'?encoded.replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,''):encoded;
    }return bad();
  }
}
const DER=Buffer.from('302e020100300506032b657004220420','hex');
const secrets=new WeakMap(),publics=new WeakMap();
const publicObject=raw=>{
  if(raw.length!==32||!ed25519.utils.isValidPublicKey(raw,false))bad();
  const key=Object.freeze({asymmetricKeyType:'ed25519',export(options){if(options?.format!=='jwk')bad();return {kty:'OKP',crv:'Ed25519',x:Buffer.from(raw).toString('base64url')};}});
  publics.set(key,new Uint8Array(raw));return key;
};
const privateObject=seed=>{
  if(seed.length!==32)bad();const raw=new Uint8Array(seed);
  const key=Object.freeze({asymmetricKeyType:'ed25519',export(options){if(options?.format!=='der'||options.type!=='pkcs8')bad();return Buffer.concat([DER,raw]);}});
  secrets.set(key,raw);return key;
};
export function createHash(algorithm){
  if(algorithm!=='sha256')bad();const hash=sha256.create();let done=false;
  const api={update(value){if(done)bad();hash.update(bytes(value));return api;},digest(encoding){if(done)bad();done=true;const result=Buffer.from(hash.digest());return encoding?result.toString(encoding):result;}};return api;
}
export function randomUUID(){if(typeof globalThis.crypto?.randomUUID!=='function')bad();return globalThis.crypto.randomUUID();}
export function generateKeyPairSync(algorithm){if(algorithm!=='ed25519'||!globalThis.crypto?.getRandomValues)bad();const seed=globalThis.crypto.getRandomValues(new Uint8Array(32));return {privateKey:privateObject(seed),publicKey:publicObject(ed25519.getPublicKey(seed))};}
export function createPrivateKey(options){
  if(options?.format!=='der'||options.type!=='pkcs8')bad();const value=bytes(options.key);
  if(value.length!==48||!DER.every((value,index)=>value===options.key[index]))bad();return privateObject(value.subarray(DER.length));
}
export function createPublicKey(value){
  if(secrets.has(value))return publicObject(ed25519.getPublicKey(secrets.get(value)));
  if(value?.format!=='jwk'||value.key?.kty!=='OKP'||value.key.crv!=='Ed25519'||typeof value.key.x!=='string'||value.key.d!==undefined)bad();
  const raw=Buffer.from(value.key.x,'base64url');if(raw.toString('base64url')!==value.key.x)bad();return publicObject(raw);
}
export function sign(algorithm,value,key){if(algorithm!==null||!secrets.has(key))bad();return Buffer.from(ed25519.sign(bytes(value),secrets.get(key)));}
export function verify(algorithm,value,key,signature){if(algorithm!==null||!publics.has(key))bad();try{return ed25519.verify(bytes(signature),bytes(value),publics.get(key),{zip215:false});}catch{return false;}}
