import {MODE,SOURCES} from './engine.mjs';
const snapshot=(id,priceCents,inventory,leadDays)=>({mode:MODE,id,url:SOURCES[id],httpStatus:200,jsonSuccess:true,partial:false,observedAt:'2026-11-14T09:00:00.000Z',cacheOriginAt:'2026-11-14T09:00:00.000Z',currency:'EUR',priceCents,inventory,leadDays,confidence:96,text:'SYNTHETIC_REPLAY • fictional supplier listing. Desk lamp, ivory.'});
export const before={mode:MODE,asOf:'2026-11-14T09:01:00.000Z',snapshots:[snapshot('north',1200,80,2),snapshot('coast',1350,65,3)]};
export const after=structuredClone(before);after.asOf='2026-11-14T09:03:00.000Z';after.snapshots[0].inventory=12;after.snapshots[0].text+=' SYNTHETIC_REPLAY stock correction: 12 units.';
export const cosmetic=structuredClone(before);cosmetic.snapshots[0].text+=' SYNTHETIC_REPLAY new banner: Weekend collection.';
export const failed=structuredClone(after);failed.snapshots[1].jsonSuccess=false;
export const scenarios={before,after,cosmetic,failed};
