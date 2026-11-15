// Research appendix page: renders the Evo 2 benchmark (RESEARCH) from app.json with the same renderer as before.
// It is kept off the main care-equity page; a failure shows its reason, not a blank.
import {genomicsHtml} from './tracks.mjs';
const el=document.getElementById('variant-content');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fetch('/data/app.json').then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}).then(app=>{el.innerHTML=genomicsHtml(app);}).catch(e=>{el.innerHTML=`<p class="missing-label">This section could not be rendered: ${esc(e.message)}</p>`;});
