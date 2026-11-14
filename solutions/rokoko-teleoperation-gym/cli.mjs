#!/usr/bin/env node
import {readFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {evaluateEpisode,compareEpisodes} from "./src/engine.mjs";
import {previewMappedCsv} from "./src/csv.mjs";

import {retargetCsv} from "./src/retarget.mjs";

const args=process.argv.slice(2);
const value=flag=>{
  const i=args.indexOf(flag);
  if(i<0 || !args[i+1]) throw new Error("expected "+flag+" value");
  return args[i+1];
};
async function main() {
  if(args.includes("--help")) {
    process.stdout.write("MotionBridge Studio (offline only)\n  node cli.mjs --episode fixtures/episodes.json\n  node cli.mjs --csv fixtures/duplicate-columns.csv --map fixtures/mapping.json\n  node cli.mjs --retarget-csv fixtures/synthetic-retarget.csv --retarget-map fixtures/retarget-map.json\n");
    return;
  }
  const modes=["--episode","--csv","--retarget-csv"].filter(f=>args.includes(f));
  const allowed=modes[0]==="--episode"?["--episode"]:modes[0]==="--csv"?["--csv","--map"]:["--retarget-csv","--retarget-map"];
  if(modes.length!==1 || args.length!==allowed.length*2 || !allowed.every(f=>args.filter(a=>a===f).length===1) || args.some((a,i)=>i%2===0 && !allowed.includes(a))) throw new Error("choose one mode with its exact flags");
  let result, input;
  if(args.includes("--retarget-csv")) {
    const readExactUtf8=async flag=>{
      const bytes=await readFile(value(flag));
      const text=bytes.toString("utf8");
      if(!Buffer.from(text,"utf8").equals(bytes)) throw new Error("invalid UTF-8 input: "+flag);
      return text;
    };
    const replay=retargetCsv(await readExactUtf8("--retarget-csv"),await readExactUtf8("--retarget-map"));
    process.stdout.write(JSON.stringify({product:"MotionBridge Studio",evidence:"OFFLINE_DETERMINISTIC",...replay},null,2)+"\n");
    return;
  }
  if(args.includes("--episode") && !args.includes("--csv")) {
    input=JSON.parse(await readFile(value("--episode"),"utf8"));
    const episodes=Array.isArray(input.episodes)?input.episodes:[input];
    result=compareEpisodes(episodes);
  } else if(args.includes("--csv") && args.includes("--map") && !args.includes("--episode")) {
    const config=JSON.parse(await readFile(value("--map"),"utf8"));
    const preview=previewMappedCsv(await readFile(value("--csv"),"utf8"),config.columns,config.calibration,config.goal,config.baseline_ms);
    result=[{receipt:evaluateEpisode(preview.episode),import_audit:{columns:preview.columns,duplicate_header_count:preview.duplicate_header_count,source_provenance_verified:false}}];
    input=preview.episode;
  } else throw new Error("choose --episode or --csv with --map");
  const digest=createHash("sha256").update(JSON.stringify(input)).digest("hex");
  process.stdout.write(JSON.stringify({product:"MotionBridge Studio",evidence:"OFFLINE_DETERMINISTIC",input_sha256:digest,results:result},null,2)+"\n");
}
main().catch(e=>{console.error("REFUSED:",e.message);process.exitCode=1;});
