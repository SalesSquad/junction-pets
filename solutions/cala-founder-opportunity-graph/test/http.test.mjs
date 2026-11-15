import { PRODUCT_SOURCE_DIGEST } from '../source-meta.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createServer } from '../server.mjs';
const get=(port,path='/',method='GET',host=`127.0.0.1:${port}`)=>new Promise((resolve,reject)=>{const req=http.request({host:'127.0.0.1',port,path,method,headers:{host}},res=>{let body='';res.on('data',b=>body+=b);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body}));});req.on('error',reject);req.end();});
test('localhost HTTP smoke: complete assets, CSP, read-only and host boundaries',async()=>{
 const server=createServer();await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
 try{const {port,address}=server.address();assert.equal(address,'127.0.0.1');const page=await get(port);assert.equal(page.status,200);assert.match(page.body,/FICTIONAL_FIXTURE/);assert.match(page.headers['content-security-policy'],/connect-src 'none'/);for(const path of ['/source-meta.mjs','/app.mjs','/core.mjs','/fixture.mjs','/style.css','/restore.mjs'])assert.equal((await get(port,path)).status,200);assert.ok((await get(port,'/source-meta.mjs')).body.includes(PRODUCT_SOURCE_DIGEST));assert.equal((await get(port,'/','POST')).status,405);assert.equal((await get(port,'/../../README.md')).status,404);assert.equal((await get(port,'/cala-contract.mjs')).status,404);assert.equal((await get(port,'/','GET','evil.example')).status,403);assert.equal((await get(port,'/','HEAD')).body,'');}
 finally{await new Promise(resolve=>server.close(resolve));}
});
