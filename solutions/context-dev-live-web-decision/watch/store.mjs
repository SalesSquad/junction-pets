import {DatabaseSync} from 'node:sqlite';
import {mkdirSync,existsSync,lstatSync,chmodSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {homedir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {validateDefinition,LIMITS,problem,criteriaKey} from './model.mjs';
import {nextOccurrence} from './schedule.mjs';

export function defaultStateFile(){return join(process.env.SUPPLYPULSE_STATE_DIR??(process.platform==='darwin'?join(homedir(),'Library','Application Support','SupplyPulse'):join(process.env.XDG_STATE_HOME??join(homedir(),'.local','state'),'supplypulse')),'watches.sqlite');}
const decode=value=>value?JSON.parse(value):null;
const instant=ms=>new Date(ms).toISOString();
export class WatchStore {
  constructor(file=defaultStateFile(),{dailyLimit=LIMITS.dailyRequests}={}){
    this.dailyLimit=dailyLimit;
    if(file!==':memory:'){
      mkdirSync(dirname(file),{recursive:true,mode:0o700});
      if(lstatSync(dirname(file)).isSymbolicLink()||existsSync(file)&&lstatSync(file).isSymbolicLink())throw problem('STORE_UNAVAILABLE');
    }
    this.db=new DatabaseSync(file);if(file!==':memory:')chmodSync(file,0o600);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS watches(id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,revision INTEGER NOT NULL,definition TEXT NOT NULL,status TEXT NOT NULL,next_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,watch_id TEXT NOT NULL REFERENCES watches(id),revision INTEGER NOT NULL,criteria_key TEXT NOT NULL,kind TEXT NOT NULL,trigger TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,summary TEXT,error_code TEXT,requests_used INTEGER NOT NULL DEFAULT 0,reserved INTEGER NOT NULL,budget_day TEXT NOT NULL,credits REAL);
      CREATE UNIQUE INDEX IF NOT EXISTS one_running_watch ON runs(watch_id) WHERE status='running';
      CREATE TABLE IF NOT EXISTS budgets(day TEXT PRIMARY KEY,used INTEGER NOT NULL DEFAULT 0,reserved INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,watch_id TEXT NOT NULL,run_id TEXT,created_at TEXT NOT NULL,type TEXT NOT NULL,title TEXT NOT NULL,detail TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);`);
  }
  tx(fn){this.db.exec('BEGIN IMMEDIATE');try{const result=fn();this.db.exec('COMMIT');return result;}catch(e){this.db.exec('ROLLBACK');throw e;}}
  raw(id){const row=this.db.prepare('SELECT * FROM watches WHERE id=?').get(id);if(!row)throw problem('WATCH_NOT_FOUND');return row;}
  event(watchId,runId,type,title,detail,now){this.db.prepare('INSERT INTO events(watch_id,run_id,created_at,type,title,detail) VALUES(?,?,?,?,?,?)').run(watchId,runId,instant(now),type,title.slice(0,200),detail.slice(0,1000));}
  watch(row){
    const latest=this.db.prepare('SELECT * FROM runs WHERE watch_id=? ORDER BY started_at DESC,rowid DESC LIMIT 1').get(row.id);
    const good=this.db.prepare("SELECT summary FROM runs WHERE watch_id=? AND status='completed' AND kind='search' AND criteria_key=? ORDER BY started_at DESC,rowid DESC LIMIT 1").get(row.id,criteriaKey(decode(row.definition)));
    return {id:row.id,revision:row.revision,definition:decode(row.definition),status:row.status,nextRunAt:row.next_at,createdAt:row.created_at,updatedAt:row.updated_at,
      lastRunAt:latest?.started_at??null,lastRunStatus:latest?.status??null,runCount:this.db.prepare('SELECT count(*) AS n FROM runs WHERE watch_id=?').get(row.id).n,lastSummary:decode(good?.summary)};
  }
  list(){return this.db.prepare('SELECT * FROM watches ORDER BY created_at DESC').all().map(r=>this.watch(r));}
  get(id){return this.watch(this.raw(id));}
  run(row){return {id:row.id,status:row.status,kind:row.kind,trigger:row.trigger,startedAt:row.started_at,finishedAt:row.finished_at,summary:decode(row.summary),errorCode:row.error_code,requestsUsed:row.requests_used,creditsConsumed:row.credits??null};}
  detail(id){const watch=this.get(id);const key=criteriaKey(watch.definition);return {watch,runs:this.db.prepare('SELECT * FROM runs WHERE watch_id=? ORDER BY started_at DESC,rowid DESC LIMIT 30').all(id).map(r=>({...this.run(r),currentCriteria:r.criteria_key===key})),events:this.db.prepare('SELECT * FROM events WHERE watch_id=? ORDER BY id DESC LIMIT 100').all(id).map(r=>({id:r.id,runId:r.run_id,createdAt:r.created_at,type:r.type,title:r.title,detail:r.detail}))};}
  future(def,now,requireFuture=false){const next=nextOccurrence(def.schedule,now);if(requireFuture&&def.schedule.kind==='once'&&!next)throw problem('INVALID_DATE_TIME');return next;}
  create(raw,token,now){
    const def=validateDefinition(raw);if(typeof token!=='string'||!/^[0-9a-f-]{36}$/i.test(token))throw problem('INVALID_REQUEST');
    return this.tx(()=>{
      const existing=this.db.prepare('SELECT * FROM watches WHERE token=?').get(token);
      if(existing){if(existing.definition!==JSON.stringify(def))throw problem('IDEMPOTENCY_CONFLICT');return this.watch(existing);}
      if(this.db.prepare('SELECT count(*) AS n FROM watches').get().n>=LIMITS.maxWatches)throw problem('WATCH_LIMIT');
      const id=randomUUID(),at=instant(now);const next=this.future(def,now,true);
      this.db.prepare('INSERT INTO watches VALUES(?,?,1,?,?,?,?,?)').run(id,token,JSON.stringify(def),'active',next,at,at);
      this.event(id,null,'created','Watch saved','Searches run at your selected times while this server is running.',now);return this.get(id);
    });
  }
  cancelRunning(id,now,code='RUN_CANCELLED'){
    for(const row of this.db.prepare("SELECT * FROM runs WHERE watch_id=? AND status='running'").all(id)){
      this.db.prepare('UPDATE budgets SET reserved=max(0,reserved-?) WHERE day=?').run(row.reserved-row.requests_used,row.budget_day);
      this.db.prepare("UPDATE runs SET status='cancelled',finished_at=?,error_code=? WHERE id=? AND status='running'").run(instant(now),code,row.id);
    }
  }
  update(id,revision,raw,now){
    const def=validateDefinition(raw);return this.tx(()=>{
      const row=this.raw(id);if(row.revision!==revision)throw problem('REVISION_CONFLICT');
      const count=this.db.prepare('SELECT count(*) AS n FROM runs WHERE watch_id=?').get(id).n;
      const status=row.status==='active'&&count>=def.maxRuns?'paused':row.status;
      const next=status==='active'?this.future(def,now,true):null;this.cancelRunning(id,now);
      this.db.prepare('UPDATE watches SET definition=?,revision=revision+1,status=?,next_at=?,updated_at=? WHERE id=?').run(JSON.stringify(def),status,next,instant(now),id);
      this.event(id,null,'updated','Watch updated','New criteria start a new comparison baseline; earlier observations remain in history.',now);return this.get(id);
    });
  }
  action(id,revision,action,now){
    return this.tx(()=>{
      const row=this.raw(id);if(row.revision!==revision)throw problem('REVISION_CONFLICT');
      if(!['pause','resume','archive'].includes(action))throw problem('INVALID_REQUEST');
      const def=decode(row.definition),count=this.db.prepare('SELECT count(*) AS n FROM runs WHERE watch_id=?').get(id).n;
      if(action==='resume'&&count>=def.maxRuns)throw problem('RUN_LIMIT_REACHED');
      const status=action==='resume'?'active':action==='archive'?'archived':'paused';
      const next=status==='active'?this.future(def,now,true):null;this.cancelRunning(id,now);
      this.db.prepare('UPDATE watches SET status=?,revision=revision+1,next_at=?,updated_at=? WHERE id=?').run(status,next,instant(now),id);
      if(action==='resume')this.db.prepare("DELETE FROM settings WHERE key='provider_blocked'").run();
      this.event(id,null,action,action==='resume'?'Watch resumed':action==='archive'?'Watch archived':'Watch paused','Previously submitted provider requests may still consume credits; no further calls from the cancelled run are started.',now);return this.get(id);
    });
  }
  budget(now){const day=instant(now).slice(0,10);const row=this.db.prepare('SELECT * FROM budgets WHERE day=?').get(day);return {dailyRequestLimit:this.dailyLimit,dailyRequestsUsed:row?.used??0,dailyRequestsReserved:row?.reserved??0,budgetDayUTC:day};}
  blocked(){return this.db.prepare("SELECT value FROM settings WHERE key='provider_blocked'").get()?.value??null;}
  pauseForProvider(code,now){this.tx(()=>{
    for(const row of this.db.prepare("SELECT * FROM watches WHERE status='active'").all()){
      this.cancelRunning(row.id,now);this.db.prepare("UPDATE watches SET status='paused',next_at=NULL,revision=revision+1,updated_at=? WHERE id=?").run(instant(now),row.id);
      this.event(row.id,null,'connection','Searches paused',code+'. Fix the connection or balance, then explicitly resume a watch.',now);
    }
    this.db.prepare("INSERT INTO settings(key,value) VALUES('provider_blocked',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(code);
  });}
  due(now){return this.db.prepare("SELECT id FROM watches WHERE status='active' AND next_at IS NOT NULL AND next_at<=? AND NOT EXISTS(SELECT 1 FROM runs WHERE runs.watch_id=watches.id AND runs.status='running') ORDER BY next_at LIMIT 5").all(instant(now)).map(r=>r.id);}
  deferForBudget(id,now){this.tx(()=>{const row=this.raw(id);if(row.status!=='active')return;const midnight=Date.parse(instant(now).slice(0,10)+'T00:00:00Z')+86_400_000;
    const next=this.future(decode(row.definition),midnight-1);
    this.db.prepare('UPDATE watches SET next_at=?,status=?,updated_at=? WHERE id=?').run(next,next?'active':'paused',instant(now),id);
    this.event(id,null,'limit','Daily search request limit reached','This slot was skipped. The next chosen schedule after the UTC budget reset is retained; no catch-up burst.',now);
  });}
  claim(id,trigger,kind,now){return this.tx(()=>{
    const row=this.raw(id),def=decode(row.definition);
    if(row.status==='archived')throw problem('WATCH_ARCHIVED');
    if(trigger==='scheduled'&&(row.status!=='active'||!row.next_at||Date.parse(row.next_at)>now))throw problem('RUN_CANCELLED');
    if(this.db.prepare("SELECT id FROM runs WHERE watch_id=? AND status='running'").get(id))throw problem('RUN_BUSY');
    const count=this.db.prepare('SELECT count(*) AS n FROM runs WHERE watch_id=?').get(id).n;if(count>=def.maxRuns)throw problem('RUN_LIMIT_REACHED');
    const reserved=kind==='research'?1:LIMITS.requestsPerSearch;const budget=this.budget(now);
    if(budget.dailyRequestsUsed+budget.dailyRequestsReserved+reserved>this.dailyLimit)throw problem('DAILY_REQUEST_LIMIT');
    const runId=randomUUID(),at=instant(now),day=at.slice(0,10);
    this.db.prepare('INSERT INTO budgets(day,used,reserved) VALUES(?,0,?) ON CONFLICT(day) DO UPDATE SET reserved=reserved+excluded.reserved').run(day,reserved);
    this.db.prepare("INSERT INTO runs(id,watch_id,revision,criteria_key,kind,trigger,status,started_at,reserved,budget_day) VALUES(?,?,?,?,?,?,'running',?,?,?)").run(runId,id,row.revision,criteriaKey(def),kind,trigger,at,reserved,day);
    const consumeSlot=trigger==='scheduled'||row.next_at&&Date.parse(row.next_at)<=now;
    if(consumeSlot)this.db.prepare('UPDATE watches SET next_at=?,updated_at=? WHERE id=?').run(this.future(def,now),at,id);
    return {id:runId,watchId:id,revision:row.revision,definition:def,kind,trigger,previous:this.watch(row).lastSummary};
  });}
  beforeRequest(runId,now=Date.now()){return this.tx(()=>{
    const row=this.db.prepare('SELECT * FROM runs WHERE id=?').get(runId);
    if(!row||row.status!=='running'||this.raw(row.watch_id).revision!==row.revision)throw problem('RUN_CANCELLED');
    if(row.budget_day!==instant(now).slice(0,10))throw problem('RUN_DAY_CHANGED');
    if(row.requests_used>=row.reserved)throw problem('REQUEST_LIMIT');
    this.db.prepare('UPDATE runs SET requests_used=requests_used+1 WHERE id=?').run(runId);
    this.db.prepare('UPDATE budgets SET used=used+1,reserved=reserved-1 WHERE day=?').run(row.budget_day);
  });}
  finish(runId,{summary=null,errorCode=null,credits=null},now){return this.tx(()=>{
    const row=this.db.prepare('SELECT * FROM runs WHERE id=?').get(runId);if(!row||row.status!=='running')return false;
    const watch=this.raw(row.watch_id);if(watch.revision!==row.revision)return false;
    this.db.prepare('UPDATE budgets SET reserved=max(0,reserved-?) WHERE day=?').run(row.reserved-row.requests_used,row.budget_day);
    this.db.prepare('UPDATE runs SET status=?,finished_at=?,summary=?,error_code=?,credits=? WHERE id=?').run(errorCode?'failed':'completed',instant(now),summary?JSON.stringify(summary):null,errorCode,credits,runId);
    const def=decode(watch.definition),count=this.db.prepare('SELECT count(*) AS n FROM runs WHERE watch_id=?').get(watch.id).n;
    if(count>=def.maxRuns||def.schedule.kind==='once'&&!watch.next_at)this.db.prepare("UPDATE watches SET status='paused',next_at=NULL,updated_at=? WHERE id=?").run(instant(now),watch.id);
    const money=value=>typeof value==='number'?'EUR '+(value/100).toFixed(2):'Unknown';
    for(const change of summary?.changes??[]){
      const detail=change.type==='availability'?`Availability: ${change.before??'unknown'} → ${change.after??'unknown'}`:change.type==='new'?`New listing observed. Item price: ${money(change.after)}.`:change.type==='target_reached'?`Confirmed item-price filters met at ${money(change.after)}.`:`Item price: ${money(change.before)} → ${money(change.after)}.`;
      this.event(watch.id,runId,change.type,change.title,detail,now);
    }
    if(errorCode)this.event(watch.id,runId,'error','Search did not complete',errorCode+'. Previous successful evidence is retained.',now);
    return true;
  });}
  close(){if(!this.closed){this.closed=true;this.db.close();}}
}
