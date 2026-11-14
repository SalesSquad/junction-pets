import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleRequest } from '../server.mjs';
const request=async(url='/',method='GET',host='127.0.0.1:4173')=>{
 const result={};const res={socket:{localPort:4173},writeHead(status,headers){Object.assign(result,{status,headers});},end(body){result.body=body?.toString()??'';}};
 await handleRequest({url,method,headers:{host}},res);return result;
};
test('in-process handler serves every declared page/module with safe headers',async()=>{for(const url of ['/','/app.mjs','/style.css','/core.mjs','/fixture.mjs']){const r=await request(url);assert.equal(r.status,200);assert.ok(r.body.length);assert.match(r.headers['Content-Security-Policy'],/connect-src 'none'/);assert.equal(r.headers['X-Content-Type-Options'],'nosniff');}assert.match((await request()).body,/<html lang="en">/);});
test('in-process handler refuses writes, hostile hosts, traversal and private paths',async()=>{for(const method of ['POST','PUT','DELETE','OPTIONS'])assert.equal((await request('/',method)).status,405);assert.equal((await request('/','GET','attacker.invalid')).status,403);for(const path of ['/../README.md','/%2e%2e/README.md','/cala-contract.mjs','/.env','/api/send','/api/cala'])assert.equal((await request(path)).status,404);assert.equal((await request('/','HEAD')).body,'');});
