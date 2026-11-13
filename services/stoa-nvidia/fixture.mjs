import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
/** Authored worksheet, not sponsor data or a blueprint. */
export function drawingFixture() {
 const image=readFileSync(new URL('../nemotron-vl/synthetic-worksheet.png',import.meta.url));
 const hash=createHash('sha256').update(image).digest('hex');
 return {question:'Read the visible estimate labels in this authored worksheet. No real benchmark or geometry is present.',
 source:{id:'synthetic-worksheet',sha256:hash,page:1,dataClass:'synthetic'},
 regions:[{id:'whole-sheet',image:'data:image/png;base64,'+image.toString('base64'),imageSha256:hash,bounds:[0,0,1,1]}]};
}
