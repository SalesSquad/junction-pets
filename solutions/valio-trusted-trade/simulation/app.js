const $=id=>document.getElementById(id);
const node=(tag,text,className)=>{const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;};
const labels={PASS:'Läpäisty',FAIL:'Virhe',RUNNING:'Käynnissä',NOT_RUN:'Odottava'};
let state=null,selected='purchase',pending=false,pollTimer=null,pollBusy=false,recovering=false,reconcileUntil=0;
const safeText=value=>typeof value==='string'?value:JSON.stringify(value);
const euros=value=>new Intl.NumberFormat('fi-FI',{style:'currency',currency:'EUR'}).format(value/100);
const refusalText={HOST_ASSERTION_INVALID:'Vanhentunut allekirjoitus torjuttiin.',QUOTE_EXPIRED:'Vanhentuneella tarjouksella ei voi tilata.',QUOTE_STALE:'Tarjouksen lähde on muuttunut. Vanhaa hyväksyntää ei käytetä.',IDENTITY_REVOKED:'Hyväksyjän oikeus ei ole enää voimassa. Tilaus estettiin.',CALLER_APPROVAL_MISSING:'Hyväksyntä puuttuu. Agentti ei saanut tilata.',HUMAN_APPROVAL_REQUIRED:'Tilaukselta puuttuu vaadittu hyväksyntä.',HTTP_UNAVAILABLE:'Kuittaus katosi. Toteutunut tila tarkistetaan ennen uusintaa.',HTTP_DEADLINE:'Kuittausta ei saatu ajoissa. Toteutunut tila tarkistetaan ennen uusintaa.'};
const observation=(value,passed)=>{
  if(!value||typeof value!=='object')return safeText(value);
  if(value.code)return refusalText[value.code]??(passed?'Odotettu torjunta toteutui.':'Tarkistus epäonnistui.');
  if(value.identity)return 'Testiagentin allekirjoitus tarkistettiin paikallisesti. Kaupankäynti on simuloitu.';
  if(Number.isSafeInteger(value.totalCents))return 'Tarjous '+euros(value.totalCents)+'. Budjetti '+euros(value.budgetCents)+'. Vain tämän tarjouksen lisävaltuus '+euros(value.additionalBudgetCents)+'.';
  if(value.status==='APPROVED')return 'Hyväksyntä koskee vain tätä tarjousta. Ostajan yleinen budjetti ei muutu.';
  if(value.status==='REJECTED')return 'Ehdotus hylättiin. Tilausta tai maksua ei hyväksytty.';
  if(value.missingLitres)return 'Maitoa puuttuu '+value.missingLitres.toLocaleString('fi-FI')+' litraa. Korvauksia: '+value.substitutions+'.';
  if(value.availableLitres===0)return 'Maidon saatavuus asetettiin nollaan testikatalogissa.';
  if(value.serverRestarted&&value.buyerRestarted)return 'Palvelin ja ostaja palautettiin samoista tallennetuista tiedoista.';
  if(value.newSnapshot)return 'Uusi lähdeversio sai uuden hyväksynnän. Testitilaus '+value.orderId+' peruttiin lopuksi.';
  if(value.newUnitPriceCents)return 'Testihinnaksi muuttui '+euros(value.newUnitPriceCents)+' litralta.';
  if(Number.isSafeInteger(value.balanceCents))return 'Testilompakossa '+euros(value.balanceCents)+'. Tilauksia '+value.orders+', maksusiirtoja '+value.transfers+', palautuksia '+value.refunds+'.'+(value.journalValid?' Kirjanpito täsmää.':'');
  if(Number.isSafeInteger(value.amountCents))return 'Erillinen testimaksu '+euros(value.amountCents)+'. Tilauksia '+value.orders+', maksusiirtoja '+value.transfers+'.';
  if(value.orderId)return 'Testikuitti '+value.orderId+'. Luotuja tilauksia '+value.orders+'.';
  if(value.orders!==undefined)return 'Tilauksia '+value.orders+', maksusiirtoja '+value.transfers+', palautuksia '+value.refunds+'.';
  return passed?'Palvelun vastaus täytti tarkistuksen.':'Tarkistus epäonnistui.';
};
const request=async(path,body)=>{
  try{
    const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(body===undefined?5000:120000)});
    const value=await response.json();if(!response.ok)throw Error(value.error==='SIMULATION_BUSY'?'SIMULATION_BUSY':'SIMULATION_CONNECTION_UNAVAILABLE');
    if(value.mode!=='LOCAL_SIMULATION'||value.externalProviderCalls!==0||!Array.isArray(value.scenarios)||!Array.isArray(value.results))throw Error('SIMULATION_RESULT_INVALID');
    return value;
  }catch(e){throw Error(['SIMULATION_BUSY','SIMULATION_RESULT_INVALID'].includes(e.message)?e.message:'SIMULATION_CONNECTION_UNAVAILABLE');}
};
function error(message,retry=false){$('error').hidden=!message;$('error').textContent=message??'';$('retry-status').hidden=!retry;}
function render(){
  if(!state)return;
  const busy=state.busy||pending||recovering,passed=state.results.filter(result=>result.outcome==='PASS').length;
  $('run-all').disabled=$('run-one').disabled=$('scenario-select').disabled=busy;
  $('run-all').lastChild.textContent=busy?' Ajo käynnissä…':' Suorita kaikki simulaatiot';
  $('passed').textContent=state.results.length?passed+' / '+state.results.length:'0 / '+state.scenarios.length;
  $('scope').textContent=state.results.length?'Simulaatiota läpäisty':'Odottavat ajoa';
  $('overall').textContent=recovering?'Ajon tilaa tarkistetaan':busy?'Simulaatio käynnissä':state.outcome==='PASS'?'Kaikki ajon tarkistukset läpi':state.outcome==='FAIL'?'Ajo vaatii korjauksen':'Valmis aloittamaan';
  $('overall').className=state.outcome==='PASS'?'safe':'';
  $('timing').textContent=state.completedAt&&state.startedAt?'Kesto '+((Date.parse(state.completedAt)-Date.parse(state.startedAt))/1000).toLocaleString('fi-FI',{maximumFractionDigits:1})+' s · eristetyt testitilat':busy?'Palvelua ajetaan nyt · odota tuloksia':'Uusi eristetty testitila jokaiselle skenaariolle';
  $('scenario-count').textContent=state.scenarios.length+' tilannetta';
  $('run-short').textContent=state.runId?'AJO '+state.runId.slice(0,8).toUpperCase():'EI AJOA';
  const result=state.results.find(value=>value.scenarioId===selected),scenario=state.scenarios.find(value=>value.id===selected);
  $('trace-title').textContent=scenario?.title??'Näe mitä tapahtui.';
  $('trace-description').textContent=scenario?.description??'Valitse skenaario nähdäksesi tapahtumaketjun.';
  const status=result?.outcome??(busy?'RUNNING':'NOT_RUN');
  $('trace-state').textContent=labels[status]??'Tarkistamaton';$('trace-state').className='status '+({PASS:'pass',FAIL:'fail',RUNNING:'running'}[status]??'waiting');
  if($('scenario-select').options.length!==state.scenarios.length){$('scenario-select').replaceChildren();for(const item of state.scenarios)$('scenario-select').append(new Option(item.title,item.id));}
  const list=$('scenarios');list.replaceChildren();
  state.scenarios.forEach((item,index)=>{
    const current=state.results.find(value=>value.scenarioId===item.id);
    const button=node('button',undefined,'scenario-button'+(selected===item.id?' active':''));button.type='button';button.dataset.scenario=item.id;
    button.setAttribute('aria-pressed',String(selected===item.id));
    button.append(node('span',String(index+1).padStart(2,'0'),'number'),node('span',item.title,'scenario-name'),
      node('span',current?.outcome==='PASS'?'✓':current?.outcome==='FAIL'?'!':'○','mark '+(current?.outcome==='PASS'?'pass':current?.outcome==='FAIL'?'fail':'')));
    button.addEventListener('click',()=>{selected=item.id;$('scenario-select').value=selected;render();});list.append(button);
  });
  const steps=$('steps');steps.replaceChildren();
  if(result){
    for(const item of result.steps??[]){
      const li=node('li');li.append(node('span',item.outcome==='PASS'?'✓':'!','step-mark'+(item.outcome==='FAIL'?' fail':'')));
      const detail=node('div');detail.append(node('h3',item.title));
      if(item.expected!==undefined)detail.append(node('p','Odotus: '+(Array.isArray(item.expected)?item.expected.map(value=>refusalText[value]??value).join(' / '):safeText(item.expected))));
      if(item.observed!==undefined){detail.append(node('p',observation(item.observed,item.outcome==='PASS')));const technical=node('details',undefined,'technical');technical.append(node('summary','Tekninen tulos'),node('pre',safeText(item.observed),'observed'));detail.append(technical);}
      li.append(detail);steps.append(li);
    }
  }else if(state.executionError){
    const li=node('li'),detail=node('div');li.append(node('span','!','step-mark fail'));detail.append(node('h3','Suoritusta ei voitu varmentaa'),node('p','Tämä tarkistus ei läpäissyt. Säilytä ajon tulos ja korjaa virhe ennen uutta yritystä.'),node('p',state.executionError.code,'observed'));li.append(detail);steps.append(li);
  }else{
    const li=node('li',undefined,'empty'),detail=node('div');li.append(node('span',busy?'◌':'◎'));detail.append(node('h3',busy?'Testitoimijat suorittavat ostopolkua':'Tämä tilanne odottaa ajoa'),node('p',busy?'Tulos tulee näkyviin, kun palvelun tarkistukset valmistuvat.':'Suorita kaikki tai aja valittu skenaario.'));li.append(detail);steps.append(li);
  }
  const receipt=$('receipt');receipt.replaceChildren();receipt.hidden=!result?.summary;
  const summaryLabels={orderId:'Testitilaus',quoteId:'Tarjous',totalCents:'Testisumma',budgetGapCents:'Tarjouksen lisävaltuus',orders:'Luodut tilaukset',transfers:'Maksusiirrot',refunds:'Palautukset',initialBalanceCents:'Testilompakon alkusaldo',finalBalanceCents:'Testilompakon loppusaldo',missingLitres:'Puuttuva määrä (L)',serverRestarts:'Palvelimen uudelleenkäynnistykset',lostOrderAcks:'Kadonneet tilauskuittaukset',lostPaymentAcks:'Kadonneet maksukuittaukset',advancedClockMs:'Testikellon siirto (s)',resourcesClosed:'Testiresurssit suljettu'};
  for(const [key,value]of Object.entries(result?.summary??{})){
    if(!Object.hasOwn(summaryLabels,key))continue;
    const text=key.endsWith('Cents')&&Number.isSafeInteger(value)?new Intl.NumberFormat('fi-FI',{style:'currency',currency:'EUR'}).format(value/100):key==='advancedClockMs'?String(value/1000):typeof value==='boolean'?(value?'Kyllä':'Ei'):safeText(value);
    receipt.append(node('dt',summaryLabels[key]??key),node('dd',text));
  }
  const commit=state.source?.commit;
  $('source').textContent=/^[a-f0-9]{40}$/.test(commit??'')?'Lähde '+commit.slice(0,10)+(state.source.worktreeDirty?' · työversio':''):'Lähdeversio ei saatavilla';
}
async function refresh(){
  if(pollBusy)return false;
  pollBusy=true;
  try{state=await request('/api/simulation/status');recovering=false;error(state.outcome==='FAIL'?'Yksi tarkistus epäonnistui. Toteutunut tulos säilyy tapahtumaketjussa.':null);render();return true;}
  catch{recovering=true;error('Yhteys katkesi. Ajon tilaa tarkistetaan; uutta ajoa ei käynnistetä.',true);render();return false;}
  finally{pollBusy=false;}
}
function scheduleStatus(){
  clearTimeout(pollTimer);
  if(Date.now()>=reconcileUntil){recovering=true;error('Ajon tilaa ei saatu vahvistettua määräajassa. Tarkista tila ennen uutta ajoa.',true);render();return;}
  pollTimer=setTimeout(async()=>{const ok=await refresh();if(!ok||state?.busy||pending)scheduleStatus();},recovering?1200:600);
}
async function run(scenario){
  if(pending||state?.busy||recovering)return;
  pending=true;state={...state,busy:true,outcome:'RUNNING',results:[],startedAt:new Date().toISOString(),completedAt:null};reconcileUntil=Date.now()+120000;error(null);render();scheduleStatus();
  try{state=await request('/api/simulation/run',{scenario});recovering=false;error(state.outcome==='FAIL'?'Yksi tarkistus epäonnistui. Toteutunut tulos säilyy tapahtumaketjussa.':null);}
  catch{await refresh();}
  finally{pending=false;clearTimeout(pollTimer);pollTimer=null;if(recovering||state?.busy)scheduleStatus();render();}
}
$('run-all').addEventListener('click',()=>{selected='purchase';void run('all');});
$('run-one').addEventListener('click',()=>{selected=$('scenario-select').value;void run(selected);});
$('retry-status').addEventListener('click',()=>{reconcileUntil=Date.now()+120000;void refresh().then(ok=>{if(!ok||state?.busy)scheduleStatus();});});
reconcileUntil=Date.now()+120000;
void refresh().then(ok=>{if(!ok||state?.busy)scheduleStatus();});
