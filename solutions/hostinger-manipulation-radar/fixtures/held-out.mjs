import {sample} from '../public/generator.mjs';
// Frozen before benchmark execution; shared generator limits independence.
// No held-out labels are exported to the browser.
export const heldOut=[
 {id:'h-cohort',title:'New cohort',events:sample('orchid',6,{names:false})},
 {id:'h-old',title:'Older matching handles',events:sample('cobalt',7,{young:false})},
 {id:'h-unknown',title:'Unknown ages',events:sample('amber',5,{unknown:true})},
 {id:'h-paraphrase',title:'Varied copy, common target',events:sample('quartz',8,{reuse:false})},
 {id:'h-evasive',title:'Delayed adversary',events:sample('delayed',6,{step:600,names:false})},
 {id:'h-wire',title:'Wire reposting',events:sample('bulletin',9,{names:false,young:false,target:false,attribution:true})},
 {id:'h-organic',title:'Organic burst',events:sample('garden',10,{names:false,young:false,reuse:false})},
 {id:'h-sparse',title:'Unknown pair',events:sample('pair',2,{unknown:true})},
 {id:'h-single',title:'Single observation',events:sample('single',1)},
 {id:'h-reposts',title:'Benign delayed reposts',events:sample('archive',6,{step:900,names:false,young:false,target:false})},
 {id:'h-volunteers',title:'Coordinated benign volunteers',events:sample('volunteer',7)},
 {id:'h-unlinked',title:'Unlinked activity',events:sample('random',8,{reuse:false,url:false,target:false,names:false,young:false})}
];
