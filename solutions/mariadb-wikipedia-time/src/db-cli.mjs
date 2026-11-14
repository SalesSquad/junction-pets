// Explicit opt-in local/test import + one readback. Never provisions a database.
import {readFile,stat} from 'node:fs/promises';
import {admitSnapshot} from './wikipedia.mjs';
import {connectLocal,initializeSchema,importSnapshot,readAsOf} from './mariadb.mjs';
let conn;
try {
  const argv=process.argv.slice(2),args={};
  if(argv.length%2)throw new Error('USAGE');
  for(let i=0;i<argv.length;i+=2) {
    if(!['--snapshot','--connection','--page','--at','--system-at','--initialize-new-test-schema'].includes(argv[i]) || args[argv[i]])throw new Error('USAGE');
    args[argv[i]]=argv[i+1];
  }
  if(!args['--snapshot'] || !args['--connection'] || !args['--page'] || !args['--at'] ||
      (args['--initialize-new-test-schema']!==undefined && args['--initialize-new-test-schema']!=='yes'))throw new Error('USAGE');
  for(const [key,max] of [['--snapshot',4*1048576],['--connection',4096]])if((await stat(args[key])).size>max)throw new Error('FILE_LIMIT');
  const snapshot=JSON.parse(await readFile(args['--snapshot'],'utf8'));
  const d=admitSnapshot(snapshot);
  if(args['--page']!==d.revisions[0].page_id)throw new Error('PAGE_IDENTITY');
  const config=JSON.parse(await readFile(args['--connection'],'utf8'));
  conn=await connectLocal(config);
  if(args['--initialize-new-test-schema']==='yes')await initializeSchema(conn);
  const imported=await importSnapshot(conn,snapshot);
  const result=await readAsOf(conn,d.dataset_id,args['--page'],args['--at'],args['--system-at']||null);
  process.stdout.write(JSON.stringify({imported,result},null,2)+'\n');
} catch {
  // Driver errors can contain connection details: never serialize them.
  process.stderr.write('LOCAL_DB_REFUSED: check snapshot, explicit local test connection, optional driver and schema. No live qualification established.\n');
  process.exitCode=2;
} finally {if(conn)await conn.end();}
