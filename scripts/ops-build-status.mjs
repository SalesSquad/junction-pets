import {fileURLToPath} from 'node:url';
import {writeStatus} from '../ops/registry.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const args=process.argv.slice(2);
if(args.length) {
  console.error('Usage: node scripts/ops-build-status.mjs');
  process.exitCode=2;
} else {
  try {
    const {target,status}=await writeStatus(root);
    console.log(JSON.stringify({output:target,source:status.source,summary:status.summary},null,2));
  } catch(error) {
    console.error(error.stack??String(error));
    process.exitCode=1;
  }
}
