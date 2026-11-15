import {validZone,validateSchedule,problem} from './model.mjs';
const formats=new Map();
function parts(ms,zone){
  if(!formats.has(zone)){validZone(zone);formats.set(zone,new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}));}
  return Object.fromEntries(formats.get(zone).formatToParts(ms).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]));
}
function offset(ms,zone){const p=parts(ms,zone);return Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute,p.second)-Math.floor(ms/1000)*1000;}
function localCandidates(local,zone){
  const [day,time]=local.split('T');const [year,month,date]=day.split('-').map(Number);const [hour,minute]=time.split(':').map(Number);
  const wall=Date.UTC(year,month-1,date,hour,minute);const offsets=new Set([-36,-12,0,12,36].map(h=>offset(wall+h*3_600_000,zone)));
  return [...offsets].map(o=>wall-o).filter(ms=>{const p=parts(ms,zone);return p.year===year&&p.month===month&&p.day===date&&p.hour===hour&&p.minute===minute;}).sort((a,b)=>a-b);
}
export function onceInstant(schedule){
  const s=validateSchedule(schedule);const candidates=localCandidates(s.at,s.timeZone);
  if(!candidates.length)throw problem('INVALID_DATE_TIME');return candidates[0];
}
export function nextOccurrence(schedule,afterMs){
  const s=validateSchedule(schedule);if(!Number.isFinite(afterMs))throw problem('INVALID_DATE_TIME');
  if(s.kind==='manual')return null;
  if(s.kind==='interval')return new Date(afterMs+s.minutes*60_000).toISOString();
  if(s.kind==='once'){const ms=onceInstant(s);return ms>afterMs?new Date(ms).toISOString():null;}
  const p=parts(afterMs,s.timeZone);const base=Date.UTC(p.year,p.month-1,p.day);
  for(let i=0;i<21;i++){
    const date=new Date(base+i*86_400_000);const weekday=date.getUTCDay()||7;
    if(s.kind==='weekly'&&!s.weekdays.includes(weekday))continue;
    // Always select the first occurrence on a fall-back day: one run per local
    // date. A nonexistent spring-forward time is skipped, not shifted silently.
    const candidate=localCandidates(date.toISOString().slice(0,10)+'T'+s.time,s.timeZone)[0];
    if(candidate!==undefined&&candidate>afterMs)return new Date(candidate).toISOString();
  }
  return null;
}
