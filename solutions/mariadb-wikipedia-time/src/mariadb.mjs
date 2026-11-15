import {readFile} from 'node:fs/promises';
import {admitSnapshot,revisionUrl,LICENSE} from './wikipedia.mjs';
import {at,sha256,utc} from './chronicle.mjs';

const columns = 'dataset_id,source_revision_id,page_id,article_title,revised_at_utc,content_body,content_sha256,source_url,dataset_license,provenance,retrieved_at_utc,source_uri,snapshot_sha256,attribution';
const sqlTime = s => new Date(utc(s)).toISOString().replace('T',' ').replace('Z','');
const values = (d,r) => [d.dataset_id,r.revision_id,r.page_id,r.title,sqlTime(r.revised_at),r.body,r.hash,r.source_url,d.dataset_license,d.provenance,sqlTime(d.retrieved_at),d.source_uri,d.snapshot_sha256,d.attribution];
export const INSERT = `INSERT INTO wiki_revision_events (${columns}) VALUES (${Array(14).fill('?').join(',')})`;
// Only explicitly supplied loopback/local-test connections; no defaults, URLs or TLS/password logging.
export async function connectLocal(config) {
  if(!config || typeof config!=='object' || !['127.0.0.1','::1','localhost'].includes(config.host) ||
      !Number.isInteger(config.port) || config.port<1 || config.port>65535 || typeof config.database!=='string' || !/^[A-Za-z0-9_]{1,64}$/.test(config.database) ||
      typeof config.user!=='string' || !config.user || (config.password!==undefined && typeof config.password!=='string') || Object.keys(config).some(k=>!['host','port','database','user','password'].includes(k)))throw new Error('EXPLICIT_LOCAL_TEST_CONNECTION_REQUIRED');
  let conn;
  try {
    const driver=await import('mariadb');
    conn=await driver.createConnection({...config,multipleStatements:false,connectTimeout:3000,dateStrings:true,bigIntAsNumber:false});
    await conn.query("SET time_zone = '+00:00'");return conn;
  } catch {if(conn)await conn.end().catch(()=>{});throw new Error('LOCAL_DB_UNAVAILABLE (optional project-local mariadb driver and explicit test server required)');}
}
// Explicit opt-in for a NEW test database. CREATE IF NOT EXISTS never migrates historical tables.
export async function initializeSchema(conn) {
  const text=await readFile(new URL('../sql/schema.sql',import.meta.url),'utf8');
  const ddl=text.match(/CREATE TABLE IF NOT EXISTS wiki_revision_events[\s\S]*?WITH SYSTEM VERSIONING;/)?.[0];
  if(!ddl)throw new Error('SCHEMA_NOT_FOUND');await conn.query(ddl);
}
export async function importSnapshot(conn,snapshot) {
  const d=admitSnapshot(snapshot);
  await conn.beginTransaction();
  try {
    let inserted=0;
    for(const r of d.revisions) {
      const v=values(d,r);
      const existing=await conn.execute(`SELECT ${columns.replace('revised_at_utc',"DATE_FORMAT(revised_at_utc, '%Y-%m-%d %H:%i:%s.%f') AS revised_at_utc").replace('retrieved_at_utc',"DATE_FORMAT(retrieved_at_utc, '%Y-%m-%d %H:%i:%s.%f') AS retrieved_at_utc")} FROM wiki_revision_events WHERE dataset_id = ? AND source_revision_id = ? FOR UPDATE`,[d.dataset_id,r.revision_id]);
      if(existing.length) {
        const row=existing[0];
        const actual=columns.split(',').map(k=>row[k]);
        // DATETIME(6) and (3) represent the same exact millisecond clock here.
        for(const i of [4,10])actual[i]=actual[i]?.slice(0,23);
        if(existing.length!==1 || JSON.stringify(actual)!==JSON.stringify(v))throw new Error('REVISION_ID_CONFLICT');
      } else {await conn.execute(INSERT,v);inserted++;}
    }
    await conn.commit();return {inserted,deduplicated:d.revisions.length-inserted,dataset_id:d.dataset_id,snapshot_sha256:d.snapshot_sha256};
  } catch {await conn.rollback();throw new Error('IMPORT_REFUSED_OR_ROLLED_BACK');}
}
export async function readAsOf(conn,datasetId,pageId,instant,systemAsOf=null) {
  if(typeof datasetId!=='string' || !/^fiwiki-[a-f0-9]{64}$/.test(datasetId) || typeof pageId!=='string' || !/^[1-9][0-9]{0,14}$/.test(pageId))throw new Error('INVALID_IDENTITY');
  const systemClause=systemAsOf===null ? '' : ' FOR SYSTEM_TIME AS OF TIMESTAMP ?';
  const parameters=[...(systemAsOf===null?[]:[sqlTime(systemAsOf)]),datasetId,pageId,sqlTime(instant)];
  const rows=await conn.execute(`SELECT source_revision_id,page_id,article_title,DATE_FORMAT(revised_at_utc, '%Y-%m-%dT%H:%i:%s.%fZ') AS revised_at,content_body,content_sha256,source_url,dataset_license,provenance,retrieved_at_utc,source_uri,snapshot_sha256,attribution FROM wiki_revision_events${systemClause} WHERE dataset_id = ? AND page_id = ? AND revised_at_utc <= ? ORDER BY revised_at_utc DESC, source_revision_id DESC LIMIT 2`,parameters);
  const revisions=rows.map(r=>{
    const stamp=r.revised_at.replace(/(\.\d{3})\d{3}Z$/,'$1Z');
    if(r.provenance!=='WIKIPEDIA_API_SNAPSHOT' || r.dataset_license!==LICENSE || r.source_url!==revisionUrl(r.source_revision_id) || r.page_id!==pageId || !/^[1-9][0-9]{0,14}$/.test(r.source_revision_id) || sha256(r.content_body)!==r.content_sha256)throw new Error('DB_INTEGRITY_REFUSED');
    return {revision_id:r.source_revision_id,page_id:r.page_id,title:r.article_title,body:r.content_body,source_url:r.source_url,revised_at:stamp,ms:utc(stamp),hash:r.content_sha256};
  });
  return {...at({dataset_id:datasetId,provenance:'WIKIPEDIA_API_SNAPSHOT',dataset_license:rows[0]?.dataset_license,source_integrity:'DB_READBACK_HASH_ONLY_UNVERIFIED',revisions},pageId,instant),
    temporal_basis:'WIKIPEDIA_REVISION_TIME',import_system_as_of:systemAsOf,
    retrieved_at:rows[0]?.retrieved_at_utc || null,source_uri:rows[0]?.source_uri || null,
    snapshot_sha256:rows[0]?.snapshot_sha256 || null,attribution:rows[0]?.attribution || null,system_time_note:'MariaDB SYSTEM_TIME records import/correction time, never the historical Wikipedia edit clock.'};
}
