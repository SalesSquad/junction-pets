import {admitSource, createDataset, createClaim} from '../../../../services/evidence-kit/src/index.mjs';
import {scanBytes} from './scan.mjs';
import {roomAnnotation} from './reading.mjs';

export function rasterAdapter(pageNumber = 1) {
  return Object.freeze({
    id:'stoa-raster-page',
    async ingest(input, {filename = 'drawing.png', rights = {kind:'unknown',attribution:''},
      expectedSha256 = null} = {}) {
      if (!(input instanceof Uint8Array) || input.length > 16*1024*1024) throw new Error('Invalid source bytes.');
      const bytes = Buffer.from(input);
      const mediaType = bytes.subarray(0,5).toString() === '%PDF-' ? 'application/pdf' : 'image/png';
      const source = await admitSource(bytes,{filename,rights,mediaType,units:null,frame:null,
        adapter:{id:'stoa-raster-page',version:'1.1.0'}},{expectedSha256});
      const page = await scanBytes(bytes,pageNumber);
      const {lines,views,...locator} = page;
      const records = [{id:'page',kind:'ocr-page',locator,data:{views:views.map(({id,inverse})=>({id,inverse}))}}];
      for (const view of [{id:null,lines},...views]) {
        for (const line of view.lines) {
          const id = view.id ? view.id+':'+line.id : line.id;
          records.push({id,kind:'ocr-line',locator:{...locator,view:view.id,viewBox:line.box},data:line});
        }
      }
      return createDataset(source,records);
    }
  });
}

export async function readPrintedArea(dataset, room) {
  if (typeof room !== 'string' || !/^[0-9]{2,5}(?:\.[0-9]{1,4})?$/.test(room)) throw new Error('Invalid room identifier.');
  if (dataset.manifest().source.adapter.id !== 'stoa-raster-page') throw new Error('Expected a raster page dataset.');
  const records = dataset.entities();
  const metadata = records.find(record=>record.id === 'page');
  const linesFor = view => records.filter(record=>record.kind === 'ocr-line' && record.locator.view === view).map(record=>record.data);
  const page = {...metadata.locator,lines:linesFor(null),
    views:metadata.data.views.map(view=>({...view,lines:linesFor(view.id)}))};
  const result = roomAnnotation(page,room);
  const observed = result.status === 'observed';
  return createClaim(dataset,{
    method:{id:'printed-room-area',version:'1.1.0',parameters:{room,page:page.page}},
    question:`What area is printed for room ${room}?`,
    status:observed ? 'supported' : 'abstained',level:observed ? 'source_observed' : 'unavailable',
    value:observed ? `${result.value} m²` : null,
    refs:result.citations.map(citation=>dataset.ref(citation.id)),
    checks:result.citations.map(({id,box,page,rasterSha256})=>({id,box,page,rasterSha256})),
    reason:result.reason ?? 'OCR observation of the printed annotation; inspect the two cited regions.'
  });
}
