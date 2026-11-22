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

export function roomAnnotation(page, room) {
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
