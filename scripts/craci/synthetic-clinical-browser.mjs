import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {createServer} from 'node:net';
import {once} from 'node:events';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium,firefox,webkit} from 'playwright';

// CRACI synthetic privacy/decision UX qualification. No live clinical or recipient traffic.
const products={
  aalto:{root:'solutions/aalto-recovery-compass/web',csp:"connect-src 'none'"},
  astra:{root:'solutions/astrazeneca-care-equity/web',csp:"connect-src 'self'"},
};
const engines={chromium,firefox,webkit};
const product=process.argv[2],engineName=process.argv[3];
assert.ok(Object.hasOwn(products,product));
assert.ok(Object.hasOwn(engines,engineName));
const sourceRoot=resolve(process.env.CRACI_SOURCE_ROOT);
const sourceSha=process.env.CRACI_SOURCE_SHA;
assert.match(sourceSha,/^[0-9a-f]{40}$/);
assert.equal(execFileSync('git',['-C',sourceRoot,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),sourceSha);
const output=resolve(process.env.CRACI_BROWSER_OUTPUT);
await mkdir(output,{recursive:true});

async function availablePort(){
  const server=createServer();
  server.listen(0,'127.0.0.1');
  await once(server,'listening');
  const {port}=server.address();
  await new Promise(done=>server.close(done));
  return port;
}
async function localDemo(){
  const port=await availablePort();
  const root=resolve(sourceRoot,products[product].root);
  const child=spawn(process.execPath,[resolve(root,'serve.mjs')],{
    cwd:root,env:{...process.env,PORT:String(port)},stdio:['ignore','pipe','pipe'],
  });
  let stderr='';
  child.stderr.on('data',chunk=>{stderr=(stderr+chunk.toString()).slice(-1000);});
  const base='http://127.0.0.1:'+port;
  let ready=false;
  for(let i=0;i<80;i++){
    if(child.exitCode!==null) break;
    try {
      const response=await fetch(base,{signal:AbortSignal.timeout(1000)});
      if(response.status===200){ready=true;break;}
    }catch{}
    await new Promise(r=>setTimeout(r,80));
  }
  if(!ready) {
    if(child.exitCode===null)child.kill('SIGTERM');
    throw Error('Synthetic local demo did not start: '+stderr.slice(0,240));
  }
  return {base,child};
}

async function aaltoJourney(page){
  assert.equal(await page.locator('#suggestion').isHidden(),true);
  assert.equal(await page.locator('#share').isHidden(),true);
  assert.equal(await page.locator('#preview-box').textContent(),'');
  assert.equal(await page.locator('#consent').isChecked(),false);
  await page.locator('#energy').selectOption('steady');
  await page.locator('input[name="activity"][value="contact"]').check();
  await page.locator('#checkin').click();
  await page.locator('#suggestion').waitFor({state:'visible'});
  assert.equal(await page.locator('#share').isHidden(),true,'Sharing appeared before opt-in');
  assert.match(await page.locator('#action-title').textContent(),/Connect with someone you choose/);
  await page.locator('#choose').click();
  await page.locator('#share').waitFor({state:'visible'});
  assert.equal(await page.locator('#include-energy').isChecked(),false,'Energy should be opt-in');
  assert.equal(await page.locator('#include-action').isChecked(),true);

  await page.locator('#preview').click();
  let preview=JSON.parse(await page.locator('#preview-box').textContent());
  assert.equal(preview.effect,'PREVIEW_ONLY');
  assert.equal(preview.receiverConnected,false);
  assert.equal(preview.clinicalRiskPrediction,false);
  assert.equal(Object.hasOwn(preview.fields,'energy'),false);
  assert.match(preview.fields.chosenAction,/Connect/);
  await page.locator('#consent-draft').click();
  assert.match(await page.locator('#message').textContent(),/Refused: explicit consent required/i);
  assert.equal(JSON.parse(await page.locator('#preview-box').textContent()).effect,'PREVIEW_ONLY');

  await page.locator('#include-energy').check();
  await page.locator('#consent').check();
  await page.locator('#consent-draft').click();
  const draft=JSON.parse(await page.locator('#preview-box').textContent());
  assert.equal(draft.effect,'UNSENT_LOCAL_DRAFT');
  assert.equal(draft.consented,true);
  assert.equal(draft.receiverConnected,false);
  assert.equal(draft.fields.energy,'steady');
  assert.match(await page.locator('#message').textContent(),/No clinician is connected/i);

  await page.locator('#revoke').click();
  assert.equal(await page.locator('#consent').isChecked(),false);
  assert.equal(await page.locator('#preview-box').textContent(),'');
  assert.match(await page.locator('#message').textContent(),/Draft cleared locally/);
  await page.locator('#recipient').fill('test@example.com');
  await page.locator('#preview').click();
  assert.match(await page.locator('#preview-box').textContent(),/invalid local recipient label/);
  await page.locator('#recipient').fill('Example clinician');

  await page.locator('#clear').click();
  assert.equal(await page.locator('#share').isHidden(),true);
  assert.equal(await page.locator('#suggestion').isHidden(),true);
  assert.match(await page.locator('#message').textContent(),/Session erased/);
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('input[name="activity"][value="contact"]').waitFor();
  assert.equal(await page.locator('#share').isHidden(),true);
  assert.equal(await page.locator('#suggestion').isHidden(),true);
  assert.equal(await page.locator('#preview-box').textContent(),'');
  const storage=await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}));
  assert.deepEqual(storage,{local:0,session:0},'Sensitive state persisted');
  assert.match(await page.locator('footer').textContent(),/112/);
  return {checks:['no_share_before_choice','no_draft_without_explicit_consent',
    'preview_only','unsent_local_draft','revoke_clears_state','invalid_recipient_refused',
    'erase_hides_outputs','reload_no_persistence','emergency_disclosure_112']};
}

async function astraState(page,state){
  await page.waitForFunction(st=>document.querySelector('#badge')?.dataset.state===st,state);
  assert.equal(await page.locator('#badge').getAttribute('data-state'),state);
}
async function astraJourney(page){
  await astraState(page,'ACTION_REVIEW');
  await page.waitForFunction(()=>!document.querySelector('#export')?.disabled && document.querySelector('#action')?.textContent.includes('Regional referral pathway lead'));
  assert.equal(await page.locator('#export').isEnabled(),true);
  assert.match(await page.locator('#action').textContent(),/Regional referral pathway lead/);
  await page.locator('#indicator').selectOption('diagnostic_wait');
  await astraState(page,'INSUFFICIENT_EVIDENCE');
  assert.equal(await page.locator('#export').isDisabled(),true);
  await page.locator('#indicator').selectOption('treatment_start');
  await astraState(page,'SUPPRESSED');
  await page.waitForFunction(()=>document.querySelector('#export')?.disabled && document.querySelector('#numbers')?.textContent==='');
  assert.equal(await page.locator('#export').isDisabled(),true);
  assert.equal(await page.locator('#numbers').textContent(),'','Suppressed numbers must not render');

  await page.locator('#indicator').selectOption('timely_referrals');
  await astraState(page,'ACTION_REVIEW');
  await page.locator('#peer').selectOption('fictional-coastal');
  await astraState(page,'REFUSED');
  assert.equal(await page.locator('#export').isDisabled(),true);
  await page.locator('#focus').selectOption('fictional-inland');
  await page.locator('#peer').selectOption('fictional-coastal');
  await astraState(page,'NO_ACTION_GAP');
  assert.equal(await page.locator('#export').isDisabled(),true);

  await page.locator('#focus').selectOption('fictional-coastal');
  await astraState(page,'REFUSED');
  await page.locator('#peer').selectOption('fictional-inland');
  await astraState(page,'ACTION_REVIEW');
  assert.equal(await page.locator('#export').isEnabled(),true);
  const [download]=await Promise.all([
    page.waitForEvent('download'),
    page.locator('#export').click(),
  ]);
  assert.equal(download.suggestedFilename(),'SYNTHETIC-care-equity-review.json');
  const exported=JSON.parse(await readFile(await download.path(),'utf8'));
  assert.equal(exported.ok,true);
  assert.equal(exported.effect,'DRAFT_ONLY');
  assert.equal(exported.verifiedLiveData,false);
  assert.equal(exported.humanApproval,'REQUIRED_NOT_GRANTED');
  assert.equal(exported.sourceKind,'SYNTHETIC_DEMONSTRATION');
  assert.equal(exported.evidence.goal3Verified,false);
  assert.match(exported.evidence.sourceDigest,/^[0-9a-f]{64}$/);
  assert.equal(exported.action.decision,'HUMAN_REVIEW_REQUIRED');
  assert.equal(exported.observations.length,2);
  assert.ok(exported.observations.every(o=>o.n>=30),'Exported small cohort');
  return {checks:['approval_gate','uncertain_overlap_refused','small_cohort_suppressed',
    'self_comparison_refused','reverse_direction_no_gap','draft_only_export',
    'source_digest','no_live_data','human_approval_required']};
}

async function viewportRun(browser,base,viewport){
  const context=await browser.newContext({viewport,acceptDownloads:true,serviceWorkers:'block'});
  const denied=[],errors=[];
  let page;
  try{
    await context.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!==base){denied.push(url.origin);await route.abort();}
      else await route.continue();
    });
    page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    const start=await page.goto(base,{waitUntil:'domcontentloaded'});
    assert.equal(start.status(),200);
    const policy=start.headers()['content-security-policy'];
    assert.ok(policy?.includes(products[product].csp),'Privacy CSP missing '+products[product].csp);
    const result=product==='aalto'?await aaltoJourney(page):await astraJourney(page);
    const overflow=await page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-innerWidth);
    assert.ok(overflow<=1,'Unexpected horizontal overflow: '+overflow+'px');
    assert.deepEqual(errors,[],'Uncaught browser errors');
    assert.deepEqual(denied,[],'Unapproved external network request');
    const receipt={schema:'craci.synthetic-clinical-browser.v1',product,engine:engineName,viewport,
      sourceSha,sourceKind:'SYNTHETIC_DEMONSTRATION',clinicalEfficacyClaim:false,
      externalRecipients:0,externalNetworkRequests:0,browserErrors:0,horizontalOverflowPx:overflow,
      ...result};
    const name=product+'-'+engineName+'-'+viewport.width;
    await writeFile(resolve(output,name+'.json'),JSON.stringify(receipt,null,2)+'\n');
    await page.screenshot({path:resolve(output,name+'.png'),fullPage:false});
    return receipt;
  }catch(error){
    if(page)try{await page.screenshot({path:resolve(output,product+'-'+engineName+'-'+viewport.width+'-failure.png')});}catch{}
    throw error;
  }finally{await context.close();}
}

const {base,child}=await localDemo();
let browser;
try{
  browser=await engines[engineName].launch({headless:true});
  for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
    console.log(JSON.stringify(await viewportRun(browser,base,viewport)));
  }
}finally{
  if(browser)await browser.close();
  if(child.exitCode===null&&child.signalCode===null)child.kill('SIGTERM');
}
