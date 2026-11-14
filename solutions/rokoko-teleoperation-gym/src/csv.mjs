// Bounded RFC4180-like CSV parser: duplicates remain distinct column indexes.
// Never infer SDK column names/units; users provide explicit positional mapping.
import {validateEpisode} from "./engine.mjs";

export function parseCsv(text) {
  if (typeof text!=="string" || text.length>5_000_000) throw new Error("REFUSED: CSV preview exceeds bounded 5MB");
  const rows=[];
  let cell="",row=[],quoted=false;
  for(let i=0;i<text.length;i++) {
    const ch=text[i];
    if(quoted) {
      if(ch==='"' && text[i+1]==='"') {cell+='"';i++;}
      else if(ch==='"') quoted=false;
      else cell+=ch;
    } else if(ch==='"') {
      if(cell.length) throw new Error("REFUSED: malformed CSV quote");
      quoted=true;
    } else if(ch===",") {row.push(cell);cell="";}
    else if(ch==="\n") {row.push(cell.replace(/\r$/,"")); rows.push(row);row=[];cell="";}
    else cell+=ch;
  }
  if(quoted) throw new Error("REFUSED: unterminated CSV quote");
  if(cell.length || row.length) {row.push(cell);rows.push(row);}
  if(rows.length<4) throw new Error("REFUSED: insufficient CSV records");
  const width=rows[0].length;
  if(!rows.every(r=>r.length===width)) throw new Error("REFUSED: ragged CSV row");
  return {headers:rows[0],records:rows.slice(1)};
}

export function previewMappedCsv(text, mapping, calibration, goal, baseline_ms=1000) {
  const {headers,records}=parseCsv(text);
  const names=["time","x","y","z","grip","quality","deadman"];
  if(!mapping || !names.every(k=>Number.isSafeInteger(mapping[k]) && mapping[k]>=0 && mapping[k]<headers.length)) throw new Error("REFUSED: explicit CSV column indexes required");
  const idx=names.map(k=>mapping[k]);
  if(new Set(idx).size!==idx.length) throw new Error("REFUSED: same column mapped to multiple distinct signals");
  if(records.length>2000) throw new Error("REFUSED: too many frames for bounded preview");
  const steps=records.map((row,i)=>{
    const number=k=>{
      const v=row[mapping[k]].trim();
      if(!v || !Number.isFinite(Number(v))) throw new Error("REFUSED: nonnumeric CSV field "+k+" row "+(i+2));
      return Number(v);
    };
    const dm=row[mapping.deadman].trim();
    if(!["0","1"].includes(dm)) throw new Error("REFUSED: deadman must be 0 or 1 row "+(i+2));
    return {at_ms:number("time"),hand:{x:number("x"),y:number("y"),z:number("z"),grip:number("grip")},tracking_quality:number("quality"),deadman:dm==="1"};
  });
  const episode={schema:"motionbridge.episode.v1",id:"imported-unverified",source_label:"UNVERIFIED_REPLAY",calibration,goal,baseline_ms,steps};
  validateEpisode(episode);
  return {episode,columns:names.map(k=>({signal:k,index:mapping[k],header:headers[mapping[k]]})),duplicate_header_count:headers.length-new Set(headers).size,source_provenance_verified:false,sdk_integration_verified:false};
}
