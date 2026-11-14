import {sample} from './generator.mjs';
export const development=[
 {id:'swarm',title:'Synchronized launch swarm',description:'Repeated copy, matching handles, recent accounts and a common amplification target.',events:sample('launch',8)},
 {id:'wire',title:'The wire-service trap',description:'Fast attributed syndication. Repetition alone would produce a false alarm.',events:sample('wire',8,{names:false,young:false,target:false,attribution:true})},
 {id:'viral',title:'Organic viral workshop',description:'A burst of varied commentary from established, differently named accounts.',events:sample('meetup',9,{names:false,young:false,reuse:false})},
 {id:'sparse',title:'Sparse / unknown',description:'Two observations cannot establish a multi-account campaign.',events:sample('unknown',2,{unknown:true})},
 {id:'slow',title:'Slow repeated bulletin',description:'Repetition across hours, without a synchronized window.',events:sample('slow',6,{step:2100,names:false,young:false,target:false})},
 {id:'mixed',title:'Mixed investigation desk',description:'Three separate clusters: a swarm, benign syndication and organic commentary.',events:[...sample('promo',8),...sample('dispatch',7,{names:false,young:false,target:false,attribution:true,offset:300000,payload:'Regional timetable update departure platform revised tomorrow morning bulletin'}),...sample('community',8,{names:false,young:false,reuse:false,offset:600000})]},
 {id:'burst',title:'Burst without a shared payload',description:'High activity without text, destination or target links remains insufficient.',events:sample('burst',7,{reuse:false,url:false,target:false,names:false,young:false})},
 {id:'unknown-swarm',title:'Unknown ages, repeated amplification',description:'Unknown metadata does not add age points; other independent signals can still trigger review.',events:sample('echo',7,{unknown:true})}
];
