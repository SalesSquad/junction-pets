import {WatchStore} from './store.mjs';
import {ContextClient} from './context.mjs';
import {executeWatch} from './engine.mjs';
import {problem,safeError} from './model.mjs';

export class WatchService {
  constructor({store,client,now=Date.now,stateFile,apiKey,tickMs=10_000,scheduler=false}={}){
    this.store=store??new WatchStore(stateFile);this.client=client??new ContextClient({apiKey});this.now=now;this.running=new Map();this.stopped=false;this.ticking=false;
    this.tickMs=tickMs;if(scheduler)this.startScheduler();
  }
  startScheduler(){if(this.timer||this.stopped)return;this.timer=setInterval(()=>this.tick().catch(()=>{}),this.tickMs);this.timer.unref();this.tick().catch(()=>{});}
  overview(){return {watches:this.store.list(),runner:{connected:this.client.connected,scheduledExecution:'while-server-running',timeZone:'Europe/Helsinki',blockedCode:this.store.blocked(),...this.store.budget(this.now())}};}
  detail(id){return this.store.detail(id);}
  create(definition,token){return this.store.create(definition,token,this.now());}
  update(id,revision,definition){const result=this.store.update(id,revision,definition,this.now());this.cancelLocal(id);return result;}
  action(id,revision,action){const result=this.store.action(id,revision,action,this.now());this.cancelLocal(id);return result;}
  cancelLocal(watchId){for(const run of this.running.values())if(run.watchId===watchId)run.controller.abort();}
  start(id,{trigger='manual',kind='search'}={}){
    if(this.stopped)throw problem('RUN_CANCELLED');if(!this.client.connected)throw problem('CONNECTION_REQUIRED');
    if(!['manual','scheduled'].includes(trigger)||!['search','research'].includes(kind))throw problem('INVALID_REQUEST');
    const claim=this.store.claim(id,trigger,kind,this.now()),controller=new AbortController();
    const task=(async()=>{
      try{
        const result=await executeWatch(claim,{client:this.client,beforeCall:()=>this.store.beforeRequest(claim.id,this.now()),signal:controller.signal});
        this.store.finish(claim.id,result,this.now());
      }catch(error){
        const code=safeError(error);this.store.finish(claim.id,{errorCode:code},this.now());
        if(['PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED'].includes(code)){
          this.store.pauseForProvider(code,this.now());for(const entry of this.running.values())entry.controller.abort();
        }
      }finally{this.running.delete(claim.id);}
    })();
    this.running.set(claim.id,{watchId:id,controller,task});return {runId:claim.id};
  }
  async tick(){
    if(this.stopped||this.ticking||!this.client.connected||this.store.blocked())return;
    this.ticking=true;
    try{
      // One scheduled job at a time per server; SQLite claims also fence other
      // processes. Overdue slots are consumed once, never replayed in a burst.
      if(this.running.size)return;
      for(const id of this.store.due(this.now())){
        try{this.start(id,{trigger:'scheduled'});break;}
        catch(e){
          if(safeError(e)==='DAILY_REQUEST_LIMIT')this.store.deferForBudget(id,this.now());
          if(safeError(e)==='RUN_LIMIT_REACHED'){const watch=this.store.get(id);this.store.action(id,watch.revision,'pause',this.now());}
        }
      }
    }finally{this.ticking=false;}
  }
  async settle(){await Promise.allSettled([...this.running.values()].map(v=>v.task));}
  close(){return this.closing??=(async()=>{this.stopped=true;if(this.timer)clearInterval(this.timer);for(const run of this.running.values())run.controller.abort();await this.settle();await this.store.close();})();}
}
