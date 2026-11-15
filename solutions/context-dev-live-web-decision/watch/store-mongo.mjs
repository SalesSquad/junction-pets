// Optional MongoDB Atlas persistence for SupplyPulse product watches.
// Zero-dependency: the official `mongodb` driver is imported only when MONGODB_URI is set.
//
// Design: WatchStore's interface is synchronous (service.mjs never awaits it), and its budget/claim
// logic relies on transactions. MongoWatchStore therefore keeps the proven in-memory working copy
// (the parent class on SQLite ':memory:') and makes MongoDB the durable system of record:
//   open()  -> hydrate watches, runs, events, budgets and settings from Atlas
//   writes  -> every mutating call schedules an ordered, serialised write-behind flush (upserts)
//   close() -> flushes, then closes the Mongo client
// One server process owns a database at a time; running jobs from a dead process are cancelled on open.
import {WatchStore} from './store.mjs';
import {problem} from './model.mjs';

const MUTATORS=['create','update','action','pauseForProvider','deferForBudget','claim','beforeRequest','finish'];
const DAY=86_400_000;
const date=value=>value==null?null:new Date(value);
const iso=value=>value==null?null:new Date(value).toISOString();
const json=value=>value==null?null:JSON.parse(value);

export const COLLECTIONS={watches:'watches',runs:'runs',events:'events',budgets:'budgets',settings:'settings'};

export async function loadMongoDriver(importer=specifier=>import(specifier)){
  try{return await importer('mongodb');}
  catch(error){
    if(error?.code==='ERR_MODULE_NOT_FOUND'||error?.code==='MODULE_NOT_FOUND')throw Object.assign(Error("MONGODB_URI is set but the 'mongodb' driver is not installed. Run `npm i mongodb` in solutions/context-dev-live-web-decision."),{code:'MONGODB_DRIVER_MISSING'});
    throw error;
  }
}

// Opens the Atlas-backed store. Pass `db` (an object with .collection(name)) in tests; otherwise the
// connection string is read only from MONGODB_URI (never accepted from requests, never logged).
export async function openMongoWatchStore({db,uri=process.env.MONGODB_URI,dbName=process.env.MONGODB_DB??'supplypulse',dailyLimit,eventTtlDays=90,runTtlDays=null,onError,importer}={}){
  let client=null;
  if(!db){
    if(!uri)throw Object.assign(Error('MONGODB_URI is not set'),{code:'MONGODB_URI_MISSING'});
    const {MongoClient}=await loadMongoDriver(importer);
    client=new MongoClient(uri,{serverSelectionTimeoutMS:8000,appName:'supplypulse'});
    try{await client.connect();}catch{await client.close().catch(()=>{});throw problem('STORE_UNAVAILABLE');}  // driver errors can echo host names; surface only the safe code
    db=client.db(dbName);
  }
  const store=new MongoWatchStore({db,client,dailyLimit,eventTtlDays,runTtlDays,onError});
  try{await store.hydrate();}catch(error){await store.shutdown().catch(()=>{});throw error?.code?error:problem('STORE_UNAVAILABLE');}
  return store;
}

export class MongoWatchStore extends WatchStore {
  constructor({db,client=null,dailyLimit,eventTtlDays=90,runTtlDays=null,onError}={}){
    super(':memory:',dailyLimit===undefined?{}:{dailyLimit});
    this.mongo=db;this.client=client;this.eventTtlDays=eventTtlDays;this.runTtlDays=runTtlDays;this.onError=onError;
    this.chain=Promise.resolve();this.lastError=null;this.seen={watches:new Map(),runs:new Map(),budgets:new Map(),settings:new Map()};this.lastEventId=0;
    for(const name of MUTATORS){const original=WatchStore.prototype[name];this[name]=(...args)=>{const result=original.apply(this,args);this.schedule();return result;};}
  }
  col(name){return this.mongo.collection(COLLECTIONS[name]);}
  async ensureIndexes(){
    await this.col('watches').createIndex({status:1,nextAt:1},{name:'due_watches'});
    await this.col('watches').createIndex({token:1},{name:'idempotency_token',unique:true});
    await this.col('runs').createIndex({watchId:1,startedAt:-1},{name:'watch_history'});
    await this.col('events').createIndex({watchId:1,_id:-1},{name:'watch_events'});
    await this.col('events').createIndex({expireAt:1},{name:'events_ttl',expireAfterSeconds:0});
    if(this.runTtlDays)await this.col('runs').createIndex({expireAt:1},{name:'runs_ttl',expireAfterSeconds:0});
  }
  async hydrate(){
    await this.ensureIndexes();
    const [watches,runs,events,budgets,settings]=await Promise.all([
      this.col('watches').find({}).sort({createdAt:1}).toArray(),this.col('runs').find({}).sort({startedAt:1}).toArray(),
      this.col('events').find({}).sort({_id:1}).toArray(),this.col('budgets').find({}).toArray(),this.col('settings').find({}).toArray()]);
    const ids=new Set(watches.map(w=>w._id));
    this.tx(()=>{
      for(const w of watches)this.db.prepare('INSERT INTO watches VALUES(?,?,?,?,?,?,?,?)').run(w._id,w.token,w.revision,JSON.stringify(w.definition),w.status,iso(w.nextAt),iso(w.createdAt),iso(w.updatedAt));
      for(const r of runs){if(!ids.has(r.watchId))continue;
        this.db.prepare('INSERT INTO runs(id,watch_id,revision,criteria_key,kind,trigger,status,started_at,finished_at,summary,error_code,requests_used,reserved,budget_day,credits) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
          .run(r._id,r.watchId,r.revision,r.criteriaKey,r.kind,r.trigger,r.status,iso(r.startedAt),iso(r.finishedAt),r.summary==null?null:JSON.stringify(r.summary),r.errorCode??null,r.requestsUsed??0,r.reserved,r.budgetDay,r.credits??null);}
      for(const e of events){if(!ids.has(e.watchId))continue;this.db.prepare('INSERT INTO events(id,watch_id,run_id,created_at,type,title,detail) VALUES(?,?,?,?,?,?,?)').run(e._id,e.watchId,e.runId??null,iso(e.createdAt),e.type,e.title,e.detail);}
      for(const b of budgets)this.db.prepare('INSERT INTO budgets(day,used,reserved) VALUES(?,?,?)').run(b._id,b.used,b.reserved);
      for(const s of settings)this.db.prepare('INSERT INTO settings(key,value) VALUES(?,?)').run(s._id,s.value);
    });
    this.lastEventId=events.reduce((m,e)=>Math.max(m,e._id),0);
    const snapshot=this.collect();for(const name of Object.keys(this.seen))for(const [key,doc] of snapshot[name])this.seen[name].set(key,JSON.stringify(doc));
    // A run that was 'running' belongs to a process that is gone; cancel it so budget reservations are released.
    const now=Date.now();let cancelled=false;
    for(const w of watches)if(this.db.prepare("SELECT 1 FROM runs WHERE watch_id=? AND status='running'").get(w._id)){this.cancelRunning(w._id,now,'RUN_CANCELLED');cancelled=true;}
    if(cancelled)this.schedule();
    await this.flush();
  }
  // Read the working copy as Mongo documents, keyed by _id.
  collect(){
    const out={watches:new Map(),runs:new Map(),budgets:new Map(),settings:new Map()};
    for(const r of this.db.prepare('SELECT * FROM watches').all())out.watches.set(r.id,{_id:r.id,token:r.token,revision:r.revision,definition:json(r.definition),status:r.status,nextAt:date(r.next_at),createdAt:date(r.created_at),updatedAt:date(r.updated_at)});
    for(const r of this.db.prepare('SELECT * FROM runs').all()){
      const doc={_id:r.id,watchId:r.watch_id,revision:r.revision,criteriaKey:r.criteria_key,kind:r.kind,trigger:r.trigger,status:r.status,startedAt:date(r.started_at),finishedAt:date(r.finished_at),summary:json(r.summary),errorCode:r.error_code,requestsUsed:r.requests_used,reserved:r.reserved,budgetDay:r.budget_day,credits:r.credits};
      if(this.runTtlDays&&r.status!=='running')doc.expireAt=new Date(Date.parse(r.finished_at??r.started_at)+this.runTtlDays*DAY);
      out.runs.set(r.id,doc);}
    for(const r of this.db.prepare('SELECT * FROM budgets').all())out.budgets.set(r.day,{_id:r.day,used:r.used,reserved:r.reserved});
    for(const r of this.db.prepare('SELECT * FROM settings').all())out.settings.set(r.key,{_id:r.key,value:r.value});
    return out;
  }
  schedule(){this.chain=this.chain.then(()=>this.flush()).catch(error=>{this.lastError=error?.code??'STORE_UNAVAILABLE';try{this.onError?.(this.lastError);}catch{}});return this.chain;}
  async flush(){
    const snapshot=this.collect();
    for(const name of Object.keys(this.seen)){
      const seen=this.seen[name];
      for(const [key,doc] of snapshot[name]){const text=JSON.stringify(doc);if(seen.get(key)===text)continue;const {_id,...fields}=doc;
        await this.col(name).updateOne({_id},{$set:fields},{upsert:true});seen.set(key,text);}
      for(const key of [...seen.keys()])if(!snapshot[name].has(key)){await this.col(name).deleteOne({_id:key});seen.delete(key);}
    }
    for(const e of this.db.prepare('SELECT * FROM events WHERE id>? ORDER BY id').all(this.lastEventId)){
      const at=Date.parse(e.created_at);
      const doc={watchId:e.watch_id,runId:e.run_id,createdAt:new Date(at),type:e.type,title:e.title,detail:e.detail};
      if(this.eventTtlDays)doc.expireAt=new Date(at+this.eventTtlDays*DAY);
      await this.col('events').updateOne({_id:e.id},{$set:doc},{upsert:true});this.lastEventId=e.id;
    }
  }
  async shutdown(){if(this.client){const c=this.client;this.client=null;await c.close();}}
  // service.close() should `await this.store.close()` so the final flush completes before exit.
  close(){
    if(this.closing)return this.closing;
    return this.closing=(async()=>{
      await this.chain;await this.schedule();
      try{await this.shutdown();}catch{}
      super.close();
    })();
  }
}
