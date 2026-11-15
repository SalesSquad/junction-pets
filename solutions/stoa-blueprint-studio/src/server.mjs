import http from 'node:http';
import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseDxf, DXF_LIMITS } from './dxf.mjs';
import { answerDrawingV2 as answerDrawing } from './quantities.mjs';
import { parseIfc, IFC_LIMITS } from './ifc.mjs';
import { answerIfc } from './ifc-qa.mjs';
import { sourceRevision, sourceIdentity, engineIdentity, digest, resolveEvidence, evidencePacket, verifyPacket } from './evidence.mjs';
import { createReviewStore } from './review.mjs';
import { compareSources } from './revisions.mjs';
import { makeDemo } from './demo.mjs';

const publicDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');

function send(res, code, data) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
  res.end(JSON.stringify(data));
}
async function body(req, limit) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) { const error = new Error('Request is too large.'); error.status = 413; throw error; }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

export function createServer() {
const cache = new Map([['demo', { drawing: makeDemo(), created: Date.now(), answers: new Map() }]]);
const MAX_FILES = 3;
const MAX_AGE_MS = 30 * 60 * 1000;

  const engine = engineIdentity();
function forget(id) {
  const item=cache.get(id); if(item?.timer)clearTimeout(item.timer); cache.delete(id);
}
function getDrawing(id) {
  const item = cache.get(id);
  if (!item) return null;
  if (id !== 'demo' && Date.now() - item.created > MAX_AGE_MS) { forget(id); return null; }
  return item.drawing;
}
function remember(drawing, model = null) {
  for (const [id, value] of cache) if (id !== 'demo' && Date.now() - value.created > MAX_AGE_MS) forget(id);
  while (cache.size >= MAX_FILES + 1) forget([...cache.keys()].find(id => id !== 'demo'));
  const timer=setTimeout(()=>forget(drawing.id),MAX_AGE_MS); timer.unref();
  cache.set(drawing.id, { drawing, model, created: Date.now(), answers: new Map(), timer });
}

  async function evaluate(drawingId, question, {store=true}={}) {
    if (typeof question !== 'string') throw new Error('Question must be text.');
    const drawing = getDrawing(drawingId);
    if (!drawing) { const error = new Error('Source expired. Reimport it.'); error.status = 404; throw error; }
    const result = drawing.format === 'IFC STEP'
      ? answerIfc(cache.get(drawingId).model, question) ?? { status: 'abstained', answer: null, explanation: 'Unsupported IFC question. Use an exact quoted storey or room name.', evidence: [], metric: null, evidenceLevel: 'unavailable', method: 'ifc.typed-entities-and-quantities/v1' }
      : answerDrawing(drawing, question);
    resolveEvidence(drawing,result.evidence);
    result.source = sourceIdentity(drawing);
    result.provenance = { sourceRevision: sourceRevision(drawing), engineSha256: (await engine).sha256, method: result.method, independentVerification: false };
    const record = { id: randomUUID(), question, result, sourceRevision: sourceRevision(drawing) };
    record.review = createReviewStore(drawing,record);
    if (store) saveAnswer(drawingId,record);
    return { result, answerId: record.id, review: record.review.snapshot(), ...(!store?{record}:{}) };
  }
  function saveAnswer(drawingId,record) {
    const answers=cache.get(drawingId).answers;
    if (answers.size>=100) answers.delete(answers.keys().next().value);
    answers.set(record.id,record);
  }
  function answerRecord(input) {
    const drawing = getDrawing(input.drawingId);
    const record = drawing && cache.get(input.drawingId).answers.get(input.answerId);
    if (!record) { const error = new Error('Answer or source expired. Ask again or restore an exported packet.'); error.status = 404; throw error; }
    return {drawing,record};
  }
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost');
      const origin = req.headers.origin;
      if (origin && !/^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/.test(origin)) {
        return send(res, 403, { error: 'Remote origins cannot access private drawings.' });
      }
      if (req.method === 'GET' && url.pathname === '/api/health') return send(res, 200, { ok: true, engine: 'deterministic', externalInference: false });
      if (req.method === 'GET' && url.pathname === '/api/demo') return send(res, 200, { drawing: getDrawing('demo') });
      if (req.method === 'POST' && url.pathname === '/api/import-dxf') {
        if (!/^application\/(?:dxf|octet-stream)/i.test(req.headers['content-type'] || '')) return send(res, 415, { error: 'Use application/dxf or application/octet-stream.' });
        const bytes = await body(req, DXF_LIMITS.bytes);
        const filename = decodeURIComponent(String(req.headers['x-filename'] || 'uploaded.dxf'));
        const drawing = parseDxf(bytes.toString('utf8'), filename);
        drawing.sha256 = createHash('sha256').update(bytes).digest('hex');
        drawing.id = randomUUID();
        drawing.sourceNotice = 'USER-IMPORTED LOCAL FILE · Geometry extracted; claims require human verification';
        remember(drawing);
        return send(res, 201, { drawing });
      }
      if (req.method === 'POST' && url.pathname === '/api/import-ifc') {
        if (!/^application\/(?:x-step|octet-stream)(?:;|$)/i.test(req.headers['content-type'] || '')) return send(res, 415, { error: 'Use application/x-step or application/octet-stream.' });
        const bytes = await body(req, IFC_LIMITS.bytes);
        const model = parseIfc(bytes.toString('latin1'));
        const filename = decodeURIComponent(String(req.headers['x-filename'] || 'uploaded.ifc')).replace(/[\\/\u0000-\u001F]/g, '_').slice(0, 120);
        if (!/\.ifc$/i.test(filename)) return send(res, 415, { error: 'Use an .ifc STEP file.' });
        const drawing = { id: randomUUID(), filename, format: 'IFC STEP', schema: model.schema,
          sha256: createHash('sha256').update(bytes).digest('hex'), unitsLabel: 'SI (validated per quantity)',
          storeys: model.storeys.map(s => String(s.name)),
          sourceNotice: 'LOCAL IFC · Entity evidence, not a projected floor plan',
          entities: [...model.entities.values()].filter(e => !['IFCCARTESIANPOINT', 'IFCPOLYLINE'].includes(e.type)).map(e => ({
            guid: typeof e.args[0] === 'string' && /^[0-9A-Za-z_$]{22}$/.test(e.args[0]) && /^(IFCSPACE|IFCDOOR|IFCWINDOW|IFCWALL|IFCSLAB|IFCCOLUMN|IFCBEAM|IFCSTAIR|IFCBUILDING|IFCSANITARY|IFCLIGHT)/.test(e.type) ? e.args[0] : null,
            id: `#${e.id}`, type: e.type, layer: e.type, text: typeof e.args[2] === 'string' ? e.args[2] : e.type,
            sourceText: [e.sourceRecord, ...[...(model.quantities.get(e.id) ?? []), ...(model.props.get(e.id) ?? [])].map(q => model.entities.get(q.entityId)?.sourceRecord), ...((model.quantities.get(e.id) ?? []).length ? model.of('IFCUNITASSIGNMENT', 'IFCSIUNIT').map(u => u.sourceRecord) : [])].filter(Boolean).join('\n'),
          })) };
        remember(drawing, model);
        return send(res, 201, { drawing });
      }
      if (req.method === 'POST' && url.pathname === '/api/ask') {
        if (!/^application\/json/i.test(req.headers['content-type'] || '')) return send(res, 415, { error: 'Use application/json.' });
        const input = JSON.parse((await body(req, 2048)).toString('utf8'));
        return send(res, 200, await evaluate(input.drawingId, input.question));
      }
      if (req.method === 'GET' && url.pathname === '/api/sources') {
        const sources = [...cache.keys()].map(id=>getDrawing(id)).filter(Boolean).map(d=>({id:d.id,...sourceIdentity(d)}));
        return send(res,200,{sources});
      }
      if (req.method === 'POST' && ['/api/review','/api/review-read','/api/export-evidence','/api/compare','/api/restore-review'].includes(url.pathname)) {
        if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) return send(res,415,{error:'Use application/json.'});
        const input = JSON.parse((await body(req,url.pathname === '/api/restore-review' ? 16*1024*1024 : 32768)).toString('utf8'));
        if (!input || typeof input !== 'object' || Array.isArray(input)) return send(res,400,{error:'Use a JSON object.'});
        if (url.pathname === '/api/compare') {
          const before=getDrawing(input.beforeId),after=getDrawing(input.afterId);
          if (!before || !after) return send(res,404,{error:'Both source revisions must be imported and unexpired.'});
          const comparison=compareSources(before,after,input.options);
          comparison.payload.engine=await engine;
          comparison.integrity.sha256=digest(comparison.payload);
          return send(res,200,{comparison});
        }
        if (url.pathname === '/api/restore-review') {
          verifyPacket(input.packet);
          const drawing=getDrawing(input.drawingId),payload=input.packet.payload;
          if (!drawing || payload.source.revision!==sourceRevision(drawing) || payload.engine.sha256!==(await engine).sha256) return send(res,409,{error:'Restore requires the same source bytes and engine version.'});
          const {record,...evaluated}=await evaluate(input.drawingId,payload.question,{store:false});
          const events=payload.review?.events;
          if (!Array.isArray(events) || events.length>100) throw new Error('Invalid review history.');
          for (const event of events) {
            const command={operationId:event.operationId,expectedRevision:record.review.snapshot().revision,sourceRevision:record.sourceRevision,kind:event.kind,reviewer:event.reviewer};
            if (event.kind==='correct') Object.assign(command,{answer:event.state?.answer,entityIds:event.state?.entityIds,note:event.state?.note});
            else if (event.kind==='confirm') command.note=event.state?.note;
            record.review.apply(command);
          }
          saveAnswer(input.drawingId,record);
          return send(res,200,{...evaluated,review:record.review.snapshot()});
        }
        const {drawing,record}=answerRecord(input);
        if (url.pathname === '/api/review-read') return send(res,200,{review:record.review.snapshot()});
        if (url.pathname === '/api/review') return send(res,200,{review:record.review.apply(input.command)});
        if (input.expectedReviewRevision!==record.review.snapshot().revision) return send(res,409,{error:'Review changed. Refresh before export.'});
        return send(res,200,{packet:evidencePacket(drawing,record,await engine,record.review.snapshot())});
      }
      const staticFiles = new Map([
        ['/', ['index.html', 'text/html; charset=utf-8']],
        ['/workspace.js', ['workspace.js', 'text/javascript; charset=utf-8']],
        ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
        ['/style.css', ['style.css', 'text/css; charset=utf-8']],
      ]);
      if (req.method === 'GET' && staticFiles.has(url.pathname)) {
        const [name, mime] = staticFiles.get(url.pathname);
        const data = await readFile(join(publicDir, name));
        res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'" });
        return res.end(data);
      }
      return send(res, 404, { error: 'No route at this path.' });
    } catch (error) {
      const code = error.status || (error instanceof SyntaxError ? 400 : 422);
      send(res, code, { error: String(error.message || error).slice(0, 240) });
    }
  });
  server.once('close',()=>{for(const id of cache.keys())forget(id);});
  return server;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const port = Number(process.env.PORT || 4315);
  const host = process.env.HOST || '127.0.0.1';
  createServer().listen(port, host, () => console.info(`Stoa Blueprint Studio listening on http://${host}:${port}`));
}
