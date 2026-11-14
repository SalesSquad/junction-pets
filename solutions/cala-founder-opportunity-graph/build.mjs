import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
for (const file of ['core.mjs','fixture.mjs','cala-contract.mjs','server.mjs','public/app.mjs']) {
  const r = spawnSync(process.execPath,['--check',new URL(file,import.meta.url).pathname],{stdio:'inherit'});
  if (r.status !== 0) process.exit(r.status ?? 1);
}
for (const file of ['public/index.html','public/style.css']) if (!(await readFile(new URL(file,import.meta.url))).length) throw Error(`Empty asset: ${file}`);
console.log('Build verified: native ES modules and static assets; no generated bundle or dependencies.');
