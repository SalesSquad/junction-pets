import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {openMongoWatchStore,loadMongoDriver} from './store-mongo.mjs';
import {WatchService} from './service.mjs';
import {validateDefinition} from './model.mjs';
const NOW=Date.parse('2026-11-15T06:00:00Z');
const definition=(patch={})=>validateDefinition({name:'Studio mouse',query:'Logitech MX Master 3S',gtin:'5099206129382',merchantIds:['gigantti','proshop'],schedule:{kind:'manual',timeZone:'Europe/Helsinki'},maxPriceCents:11000,...patch});
// In-memory fake of the MongoDB collection subset the store uses.
class FakeCollection {
  docs=new Map();indexes=[];
  async createIndex(keys,options={}){this.indexes.push({keys,...options});return options.name;}
  find(){const docs=[...this.docs.values()].map(d=>structuredClone(d));return {sort(spec){const [[k,dir]]=Object.entries(spec);docs.sort((a,b)=>((a[k]>b[k])-(a[k]<b[k]))*dir);return this;},async toArray(){return docs;}};}
  async findOne(f){return structuredClone(this.docs.get(f._id))??null;}
  async insertOne(doc){if(this.docs.has(doc._id))throw Error('E11000');this.docs.set(doc._id,structuredClone(doc));}
  async updateOne(f,update,{upsert}={}){const cur=this.docs.get(f._id);if(!cur&&!upsert)return {matchedCount:0};this.docs.set(f._id,{...(cur??{_id:f._id}),...structuredClone(update.$set)});return {matchedCount:cur?1:0};}
  async deleteOne(f){this.docs.delete(f._id);}
}
class FakeDb {cols={};collection(name){return this.cols[name]??=new FakeCollection();}}

test('writes watches, runs, events and budgets to collections with due-time and TTL indexes',async()=>{
  const db=new FakeDb(),store=await openMongoWatchStore({db});
  try{
    const w=store.create(definition({schedule:{kind:'daily',time:'09:00',timeZone:'Europe/Helsinki'}}),randomUUID(),NOW);
    const run=store.claim(w.id,'manual','search',NOW);store.beforeRequest(run.id,NOW);
    assert.equal(store.finish(run.id,{summary:{offers:[{id:'o'}],changes:[{type:'new',title:'New',after:10900}]},credits:3},NOW+1),true);
    await store.flush();
    const doc=db.cols.watches.docs.get(w.id);assert.equal(doc.status,'active');assert(doc.nextAt instanceof Date);assert.equal(doc.definition.name,'Studio mouse');
    const stored=[...db.cols.runs.docs.values()];assert.equal(stored.length,1);assert.equal(stored[0].status,'completed');assert.equal(stored[0].summary.offers.length,1);assert.equal(stored[0].requestsUsed,1);
    assert(db.cols.events.docs.size>=2);assert([...db.cols.events.docs.values()].every(e=>e.expireAt instanceof Date&&e.expireAt>e.createdAt));
    assert.equal(db.cols.budgets.docs.get('2026-11-15').used,1);
    const names=Object.values(db.cols).flatMap(c=>c.indexes.map(i=>i.name));assert(names.includes('due_watches')&&names.includes('events_ttl'));
    assert.equal(db.cols.events.indexes.find(i=>i.name==='events_ttl').expireAfterSeconds,0);assert.equal(db.cols.watches.indexes.find(i=>i.name==='idempotency_token').unique,true);
    assert(!names.includes('runs_ttl'));
  }finally{await store.close();}
});

test('state survives reopen: watches, history, due schedule, budget and provider block',async()=>{
  const db=new FakeDb();let store=await openMongoWatchStore({db});
  const w=store.create(definition({schedule:{kind:'once',at:'2026-11-15T09:00',timeZone:'Europe/Helsinki'}}),randomUUID(),NOW);
  store.pauseForProvider('PROVIDER_CREDITS_EXHAUSTED',NOW+1);await store.close();
  store=await openMongoWatchStore({db});
  try{
    assert.equal(store.blocked(),'PROVIDER_CREDITS_EXHAUSTED');assert.equal(store.list().length,1);assert.equal(store.get(w.id).status,'paused');
    const resumed=store.action(w.id,store.get(w.id).revision,'resume',NOW+2);assert.equal(resumed.status,'active');assert.equal(store.blocked(),null);
    assert.deepEqual(store.due(NOW+3_600_000),[w.id]);
    const run=store.claim(w.id,'scheduled','search',NOW+3_600_000);store.beforeRequest(run.id,NOW+3_600_000);store.finish(run.id,{summary:{offers:[],changes:[]}},NOW+3_600_001);
    await store.close();
    assert.equal(db.cols.settings.docs.size,0);// provider_blocked deleted on resume
    store=await openMongoWatchStore({db});assert.deepEqual(store.due(NOW+10_000_000),[]);assert.equal(store.detail(w.id).runs.length,1);assert.equal(store.budget(NOW+3_600_000).dailyRequestsUsed,1);
    assert.equal(store.detail(w.id).events.length>=3,true);
  }finally{await store.close();}
});

test('idempotent create and revision rules still hold; run left running by a dead process is cancelled and budget released',async()=>{
  const db=new FakeDb();let store=await openMongoWatchStore({db});
  const def=definition(),token=randomUUID(),w=store.create(def,token,NOW);assert.equal(store.create(def,token,NOW).id,w.id);
  assert.throws(()=>store.create({...def,name:'Changed'},token,NOW),{code:'IDEMPOTENCY_CONFLICT'});
  assert.throws(()=>store.update(w.id,w.revision+5,def,NOW),{code:'REVISION_CONFLICT'});
  const run=store.claim(w.id,'manual','search',NOW);store.beforeRequest(run.id,NOW);
  assert.throws(()=>store.claim(w.id,'manual','search',NOW),{code:'RUN_BUSY'});
  await store.flush();assert.equal(db.cols.runs.docs.get(run.id).status,'running');
  // simulate crash: drop without close, reopen on same db
  store=await openMongoWatchStore({db});
  try{assert.equal(store.detail(w.id).runs[0].status,'cancelled');assert.equal(store.detail(w.id).runs[0].errorCode,'RUN_CANCELLED');assert.equal(store.budget(NOW).dailyRequestsReserved,0);assert.equal(store.budget(NOW).dailyRequestsUsed,1);
    assert(store.claim(w.id,'manual','search',NOW+5));await store.flush();assert.equal(db.cols.runs.docs.get(run.id).status,'cancelled');
  }finally{await store.close();}
});

test('optional run TTL is opt-in and sets expireAt only on finished runs',async()=>{
  const db=new FakeDb(),store=await openMongoWatchStore({db,runTtlDays:30});
  try{const w=store.create(definition(),randomUUID(),NOW),r1=store.claim(w.id,'manual','search',NOW);await store.flush();assert.equal(db.cols.runs.docs.get(r1.id).expireAt,undefined);
    store.finish(r1.id,{summary:{offers:[],changes:[]}},NOW+1000);await store.flush();assert(db.cols.runs.docs.get(r1.id).expireAt>new Date(NOW+29*86_400_000));
    assert(db.cols.runs.indexes.some(i=>i.name==='runs_ttl'));}finally{await store.close();}
});

test('WatchService works on the Mongo store and close() flushes before shutdown',async()=>{
  const db=new FakeDb(),store=await openMongoWatchStore({db}),service=new WatchService({store,client:{connected:true},now:()=>NOW});
  const w=service.create(definition(),randomUUID());await service.close();
  assert.equal(db.cols.watches.docs.get(w.id).definition.query,'Logitech MX Master 3S');
});

test('flush failures are reported by code only and never throw into the synchronous API',async()=>{
  const db=new FakeDb(),seen=[],store=await openMongoWatchStore({db,onError:c=>seen.push(c)});
  db.cols.watches.updateOne=async()=>{throw Object.assign(Error('mongodb+srv://user:secret@cluster.example/db failed'),{code:'ECONNRESET'});};
  try{store.create(definition(),randomUUID(),NOW);await store.chain;assert.deepEqual(seen,['ECONNRESET']);assert.equal(store.list().length,1);assert(!JSON.stringify(seen).includes('secret'));}
  finally{db.cols.watches.updateOne=FakeCollection.prototype.updateOne;await store.close();}
});

test('connection setup: URI only from env, clear driver-missing error, no connection string in errors',async()=>{
  await assert.rejects(openMongoWatchStore({uri:''}),{code:'MONGODB_URI_MISSING'});
  const missing=()=>Promise.reject(Object.assign(Error('Cannot find package mongodb'),{code:'ERR_MODULE_NOT_FOUND'}));
  await assert.rejects(loadMongoDriver(missing),/npm i mongodb/);
  const uri='mongodb+srv://user:topsecret@cluster0.example.mongodb.net/?retryWrites=true';let closed=false;
  class MongoClient{constructor(u){this.u=u;}async connect(){throw Error('connect failed to '+this.u);}async close(){closed=true;}}
  await assert.rejects(openMongoWatchStore({uri,importer:async()=>({MongoClient})}),error=>{assert.equal(error.code,'STORE_UNAVAILABLE');assert(!error.message.includes('topsecret'));return true;});assert(closed);
  const ok=[];class GoodClient{constructor(u,o){ok.push([u,o]);this.d=new FakeDb();}async connect(){}db(n){ok.push(n);return this.d;}async close(){ok.push('closed');}}
  const store=await openMongoWatchStore({uri,dbName:'sp',importer:async()=>({MongoClient:GoodClient})});await store.close();assert.deepEqual([ok[0][0],ok[1],ok[2]],[uri,'sp','closed']);
});
