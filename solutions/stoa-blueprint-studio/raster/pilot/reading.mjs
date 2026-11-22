import {createHash} from 'node:crypto';

export const digest = bytes => createHash('sha256').update(bytes).digest('hex');

export function readLines(tsv, width, height) {
  const lines = new Map();
  for (const row of tsv.split(/\r?\n/).slice(1)) {
    const fields = row.split('\t');
    if (fields[0] !== '5' || fields.length !== 12 || !fields[11].trim()) continue;
    const [x, y, w, h, confidence] = fields.slice(6, 11).map(Number);
    if (![x,y,w,h].every(Number.isSafeInteger) || x < 0 || y < 0 ||
        w <= 0 || h <= 0 || x+w > width || y+h > height || !Number.isFinite(confidence)) {
      throw new Error('Invalid OCR word coordinates or confidence.');
    }
    const id = fields.slice(1, 5).join('.');
    if (!lines.has(id)) lines.set(id, []);
    lines.get(id).push({text: fields[11].trim(), confidence, box: [x,y,x+w,y+h]});
  }
  return [...lines].map(([id, words]) => ({
    id,
    text: words.map(word => word.text).join(' '),
    confidence: Math.min(...words.map(word => word.confidence)),
    box: words.reduce((a, {box:b}) => [
      Math.min(a[0],b[0]), Math.min(a[1],b[1]), Math.max(a[2],b[2]), Math.max(a[3],b[3])
    ], words[0].box)
  }));
}

const idPattern = /^(?:ROOM\s+)?([0-9]{2,5}(?:\.[0-9]{1,4})?)$/i;
const areaPattern = /^(\d+(?:[.,]\d+)?)\s*m(?:²|2)$/i;
const below = (tag, area) => {
  const [x,y,r,b] = tag.box;
  const [ax,ay,ar] = area.box;
  return ay >= b && ay-b <= 2*(b-y) && Math.min(r,ar) > Math.max(x,ax);
};

function observation(page, room) {
  const abstain = reason => ({status:'abstained', reason, citations:[]});
  const tags = page.lines.filter(line => idPattern.test(line.text));
  const matches = tags.filter(line => idPattern.exec(line.text)[1] === room);
  if (matches.length !== 1) return abstain('Room identifier absent or ambiguous.');
  const tag = matches[0];
  const areas = page.lines.filter(line => areaPattern.test(line.text) && below(tag,line));
  if (areas.length !== 1 || tags.filter(line => below(line,areas[0])).length !== 1) {
    return abstain('No uniquely associated area annotation.');
  }
  const area = areas[0];
  const value = Number(areaPattern.exec(area.text)[1].replace(',','.'));
  if (!Number.isFinite(value) || value <= 0) return abstain('Invalid area annotation.');
  if (Math.min(tag.confidence,area.confidence) < 70) return abstain('OCR confidence below threshold.');
  return {status:'observed', value, unit:'m²',
    citations:[tag,area].map(({id,box,text}) => ({id,box,text,page:page.page,
      sourceSha256:page.sourceSha256,rasterSha256:page.rasterSha256,width:page.width,height:page.height}))};
}

// Controls are operator-labelled pixel segments in the exact rendered page.
export function checkScale(page, controls) {
  const abstain = reason => ({status:'abstained', reason});
  if (!Array.isArray(controls) || controls.length !== 2) return abstain('Two orthogonal controls required.');
  const ratios = [];
  const axes = new Set();
  for (const control of controls) {
    const {rasterSha256, from, to, metres} = control ?? {};
    const valid = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) &&
      p[0] >= 0 && p[1] >= 0 && p[0] < page.width && p[1] < page.height;
    if (rasterSha256 !== page.rasterSha256 || !valid(from) || !valid(to) ||
        !Number.isFinite(metres) || metres <= 0) return abstain('Invalid or stale scale control.');
    const dx = Math.abs(to[0]-from[0]), dy = Math.abs(to[1]-from[1]);
    if ((dx === 0) === (dy === 0)) return abstain('Controls must be axis aligned.');
    axes.add(dx ? 'x' : 'y');
    const ratio = (dx+dy)/metres;
    if (!Number.isFinite(ratio) || ratio <= 0) return abstain('Invalid pixel scale.');
    ratios.push(ratio);
  }
  if (Math.abs(ratios[0]-ratios[1])/Math.max(...ratios) > .02) return abstain('Scale controls disagree.');
  if (axes.size !== 2) return abstain('Two orthogonal controls required.');
  return {status:'controls_agree', pixelsPerMetre:ratios[0]/2+ratios[1]/2, rasterSha256:page.rasterSha256};
}

function sourceBox(box, inverse, width, height) {
  const [a,b,c,d,e,f] = inverse;
  const [left,top,right,bottom] = box;
  const corners = [[left,top],[left,bottom],[right,top],[right,bottom]];
  const xs = corners.map(([x,y]) => a*x+b*y+c);
  const ys = corners.map(([x,y]) => d*x+e*y+f);
  return [Math.max(0,Math.floor(Math.min(...xs))),Math.max(0,Math.floor(Math.min(...ys))),
    Math.min(width,Math.ceil(Math.max(...xs))),Math.min(height,Math.ceil(Math.max(...ys)))];
}

const overlaps = (a,b) => {
  const intersection = Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0])) *
    Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
  const area = box => (box[2]-box[0])*(box[3]-box[1]);
  return intersection >= .5*(area(a)+area(b)-intersection) && intersection > 0;
};

export function roomAnnotation(page, room) {
  const original = observation(page,room);
  const candidates = original.status === 'observed' ? [original] : [];
  for (const view of page.views ?? []) {
    const candidate = observation({...page,lines:view.lines},room);
    if (candidate.status !== 'observed') continue;
    candidate.citations = candidate.citations.map(citation => ({...citation,
      id:view.id+':'+citation.id,
      box:sourceBox(citation.box,view.inverse,page.width,page.height)}));
    candidates.push(candidate);
  }
  if (!candidates.length) return original;
  const first = candidates[0];
  if (candidates.some(candidate => candidate.value !== first.value ||
      candidate.citations.some((citation,i) => !overlaps(citation.box,first.citations[i].box)))) {
    return {status:'abstained',reason:'OCR views disagree on value or citation location.',citations:[]};
  }
  if (original.status === 'observed') return original;
  // A retry must corroborate another view or the original room identifier.
  const matchingTags = page.lines.filter(line => idPattern.exec(line.text)?.[1] === room);
  if (matchingTags.length > 1 || (candidates.length < 2 &&
      !matchingTags.some(line => line.confidence >= 70 && overlaps(line.box,first.citations[0].box)))) {
    return {status:'abstained',reason:'Retry lacks corroboration for the room identifier.',citations:[]};
  }
  return first;
}
