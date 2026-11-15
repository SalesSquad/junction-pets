// OFFLINE_SYNTHETIC_OOD: authored challenge design, fixed before scoring.
// Independent of public/generator.mjs, development cases and held-out fixtures.
export const SEEDS=Object.freeze([12011,24029,36037,48049,60077,72091,84121,96137]);
export const FAMILIES=Object.freeze([
 {id:'volunteers',count:16,harmful:false,stipulation:'Consenting emergency-response or civic volunteers share an openly organized bulletin; no deception.',counterevidence:'Shared shift schedules, public volunteer sign-up and approved bulletin templates can explain bursts, young handles and repeated destinations.',action:'Request the public shift notice and template provenance; compare the flagged event IDs and timing with it. Keep Insufficient context until verified; record Likely benign only with supporting evidence.'},
 {id:'wire',count:12,harmful:false,stipulation:'Authorized journalism syndication with source attribution, sometimes lost on excerpted copies; no deceptive independence.',counterevidence:'Wire credits and an original dispatch can explain copied text and synchronized publication; missing excerpt credits do not establish deception.',action:'Trace the original dispatch and verify redistribution permission and credit history for the flagged outlets. Record unresolved provenance and request human review.'},
 {id:'community',count:12,harmful:false,stipulation:'Independent community members discuss a common event without a hidden organizer or paid amplification.',counterevidence:'A shared public event and established participants can explain URL concentration and close timing, even with a quoted announcement.',action:'Check the event schedule and independently sourced context. Compare original commentary with quoted text; preserve uncertainty if account metadata cannot be verified.'},
 {id:'overt',count:12,harmful:true,stipulation:'Authors stipulate a hidden operator pays controlled accounts to deceptively appear independent; the observations alone cannot prove this.',counterevidence:'Apparent coordination is compatible with legitimate outreach; intent is stipulated only in this synthetic audit.',action:'Seek independently licensed evidence of concealed control and deceptive independence before any conclusion. Review signal event IDs; never infer intent from rule points.'},
 {id:'evasive',count:12,harmful:true,stipulation:'Authors stipulate the same concealed paid operator, spacing posts or mixing organic participants to evade timing and cohort gates.',counterevidence:'Slow timing and mixed account ages can hide the authored manipulation; an unflagged case does not establish safety.',action:'Request authorized longitudinal and provenance evidence; document the timing-gate miss and retain Insufficient context. Do not lower thresholds from these results.'}
].map(Object.freeze));
// Mulberry32 with explicit uint32 arithmetic, no Math.random or external entropy.
export function random32(seed){let state=seed>>>0;return()=>{state=(state+0x6D2B79F5)>>>0;let t=state;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;};}
const epoch=Date.parse('2026-09-03T08:00:00Z');
const aliases=['acorn','beacon','coral','dune','egret','flint','grove','heath','iris','juniper','kestrel','lagoon','marsh','nectar'];
const commentary=['Arrived early and checked the north entrance with a friend','My notebook has a sketch of the accessible route beside the station','We discussed several alternatives during the afternoon session','The noticeboard lists revised opening times for next weekend','I tried the workshop exercise and wrote down two questions','Our neighborhood map now includes the temporary footbridge'];
// This API separates authored truth from observations; only events enter analyze().
export function corpus(seeds=SEEDS){
 if(!Array.isArray(seeds)||!seeds.length||seeds.length>8||new Set(seeds).size!==seeds.length||seeds.some(s=>!Number.isInteger(s)||s<0||s>0xffffffff))throw new Error('Use 1–8 distinct uint32 seeds.');
 const cases=[],labels={};
 for(const seed of seeds){const rand=random32(seed),int=(a,b)=>a+Math.floor(rand()*(b-a+1));
 for(const [familyIndex,family]of FAMILIES.entries())for(let variant=0;variant<family.count;variant++){
 const id=`ood-${seed}-${familyIndex}-${String(variant).padStart(2,'0')}`,events=[];
 const n=int(4,14),groups=1+variant%3,start=epoch+int(0,20)*86400000+int(0,3600)*1000;
 const spacing=family.id==='evasive'?int(90,1800):variant%4===0?int(35,160):int(2,12);
 const patterned=family.id==='volunteers'?variant%3!==0:family.id==='overt'?variant%4!==0:family.id==='evasive'?variant%2===0:false;
 const reuse=family.id==='wire'||family.id==='volunteers'||family.id==='overt'||variant%3===0;
 const bulletin=`Community bulletin sector ${int(10,99)} opens the temporary crossing on Thursday please share this exact notice`;
 for(let i=0;i<n;i++){
 const group=i%groups,core=group===0,ageMode=variant%4;
 const young=(family.id==='volunteers'||family.id==='overt')&&ageMode!==0;
 const age=ageMode===3&&i%3===0?null:young?int(0,14):int(200,2400);
 const text=reuse?(i%4===0?`${bulletin} updated`:bulletin):`${commentary[(i+variant)%commentary.length]} observation ${int(100,999)}`;
 events.push({id:`e${i}`,account:patterned&&core?`desk_${seed}_${variant}_${i}`:`${aliases[i%aliases.length]}${seed}x${variant}z${i}`,time:new Date(start+i*spacing*1000+int(0,3)*1000).toISOString(),text:core?text:`${commentary[(i+2)%commentary.length]} district ${group} note ${int(100,999)}`,url:variant%5===0?'':`https://fixture.invalid/${seed}/${variant}/${group}${variant%4===1?`/story-${i%2}`:''}?channel=${i}`,amplifies:variant%4===2?'':`dispatch-${seed}-${variant}-${group}`,accountAgeDays:age,attribution:family.id==='wire'&&(variant%4!==0||i%2===0)?'Authored synthetic wire credit':family.id==='evasive'&&variant%4===0?'Unverified supplied credit':''});
 }
 cases.push({id,family:family.id,events});labels[id]={harmful:family.harmful,stipulation:family.stipulation};
 }
 }return {cases,labels};
}
