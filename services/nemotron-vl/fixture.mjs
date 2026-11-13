import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

// Authored demonstration data, not benchmark measurements or a vision-accuracy test.
export function syntheticFixture() {
  const image=readFileSync(new URL('./synthetic-worksheet.png',import.meta.url));
  const row={workload:'synthetic-render-worksheet',kind:'3d-render',sceneCount:1,objectCount:800,
    inputDigest:createHash('sha256').update('authored-synthetic-scene-v1').digest('hex'),width:1920,height:1080,
    precision:'fp32',quality:'same authored scene and quality declaration',software:'synthetic worksheet v1',timingScope:'authored frame estimate',
    warmup:0,repeats:1,unit:'ms',evidence:'authored-estimate',provenance:'unverified authored fixture'};
  return {question:'Read the visible worksheet labels and distinguish authored estimates from measurements. Use an official NVIDIA model source card and compare baseline against candidate with the benchmark tool. Explain what is established and the next check needed; do not claim a measured GPU speedup.',
    images:['data:image/png;base64,'+image.toString('base64')],benchmarkRows:[
      {id:'baseline',record:{...row,hardware:'authored baseline hardware label',timings:[120]}},
      {id:'candidate',record:{...row,hardware:'authored candidate hardware label',timings:[60]}}
    ]};
}
