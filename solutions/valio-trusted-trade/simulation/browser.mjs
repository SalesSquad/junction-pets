/** Run the real simulation UI, retain scoped screenshots/report, then close all owned resources. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createSimulationServer } from './server.mjs';

const {chromium}=await import(process.env.PLAYWRIGHT_MODULE??'playwright');
const destination=resolve(process.env.VALIO_SIMULATION_ARTIFACT_DIR??'.runtime/simulation-receipts/browser');
await mkdir(destination,{recursive:true});
const app=await createSimulationServer();app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
const base='http://127.0.0.1:'+app.server.address().port;
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_PATH}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1050}});
const page=await context.newPage(),errors=[],external=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{if(new URL(request.url()).origin!==base)external.push(request.url());});
page.setDefaultTimeout(30000);
try {
  await page.goto(base+'/');
  await page.waitForFunction(()=>!document.getElementById('run-all').disabled&&document.querySelectorAll('[data-scenario]').length===7);
  assert.match(await page.locator('body').innerText(),/Oikeita tilauksia tai maksuja ei lähetetä/);
  await page.locator('#run-all').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.getElementById('overall').textContent==='Kaikki ajon tarkistukset läpi',{},{timeout:120000});
  assert.equal(await page.locator('#passed').textContent(),'7 / 7');
  assert.equal(await page.locator('.mark.pass').count(),7);
  const report=await(await fetch(base+'/api/simulation/report')).json();
  assert.equal(report.outcome,'PASS');assert.equal(report.results.length,7);assert.equal(report.externalProviderCalls,0);
  for(const result of report.results)assert.equal(result.outcome,'PASS',result.scenarioId);
  await page.screenshot({path:resolve(destination,'simulation-desktop.png'),fullPage:true});
  await page.locator('[data-scenario="retry"]').click();
  assert.equal(await page.locator('#scenario-select').inputValue(),'retry');
  assert.match(await page.locator('#steps').innerText(),/COMMIT|kuittaus|katko|uudelleen/i);
  await page.screenshot({path:resolve(destination,'simulation-retry.png'),fullPage:true});
  const before=report.runId;await page.reload();
  await page.waitForFunction(()=>document.getElementById('passed').textContent==='7 / 7');
  assert.equal((await(await fetch(base+'/api/simulation/status')).json()).runId,before,'reload must display the actual completed run without replaying effects');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'mobile must not overflow');
  await page.screenshot({path:resolve(destination,'simulation-mobile.png'),fullPage:true});
  assert.equal(await page.locator('#error').isVisible(),false);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const receipt={...report,browserEvidence:{engine:'Chromium',desktop:{width:1440,height:1050},mobile:{width:390,height:844},keyboardRun:true,reloadDidNotRerun:true,horizontalOverflow:false,javascriptErrors:errors,externalBrowserRequests:external}};
  await writeFile(resolve(destination,'simulation-report.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify({check:'simulation-browser-seven-scenarios',outcome:'PASS',runId:report.runId,scenarios:7,allResults:'PASS',
    keyboardRun:true,reloadDidNotRerun:true,desktopAndMobile:true,javascriptErrors:0,externalRequests:0,source:report.source,artifacts:destination}));
} finally {await context.close();await browser.close();await app.close();}
