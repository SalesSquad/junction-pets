const $=id=>document.getElementById(id);
const node=(tag,text,className)=>{const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;};
const labels={PASS:'Läpäisty',FAIL:'Virhe',RUNNING:'Käynnissä',NOT_RUN:'Odottava'};
let state=null,selected='purchase',pending=false,pollTimer=null;
const safeText=value=>typeof value==='string'?value:JSON.stringify(value);
const request=async(path,body)=>{
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(120000)});
  const value=await response.json();if(!response.ok)throw Error(value.error==='SIMULATION_BUSY'?'Edellinen simulaatio on vielä käynnissä.':'Ajoa ei voitu tarkistaa. Yritä uudelleen.');
  if(value.mode!=='LOCAL_SIMULATION'||value.externalProviderCalls!==0||!Array.isArray(value.scenarios)||!Array.isArray(value.results))throw Error('Simulaation tulos ei vastaa odotettua rajattua testitilaa.');
  return value;
};
function error(message){$('error').hidden=!message;$('error').textContent=message??'';}
function render(){
  if(!state)return;
  const busy=state.busy||pending,passed=state.results.filter(result=>result.outcome==='PASS').length;
  $('run-all').disabled=$('run-one').disabled=$('scenario-select').disabled=busy;
  $('run-all').lastChild.textContent=busy?' Ajo käynnissä…':' Suorita kaikki simulaatiot';
  $('passed').textContent=state.results.length?passed+' / '+state.results.length:'0 / '+state.scenarios.length;
  $('scope').textContent=state.results.length?'Simulaatiota läpäisty':'Odottavat ajoa';
  $('overall').textContent=state.outcome==='PASS'?'Kaikki ajon tarkistukset läpi':state.outcome==='FAIL'?'Ajo vaatii korjauksen':busy?'Simulaatio käynnissä':'Valmis aloittamaan';
  $('overall').className=state.outcome==='PASS'?'safe':'';
  $('timing').textContent=state.completedAt&&state.startedAt?'Kesto '+((Date.parse(state.completedAt)-Date.parse(state.startedAt))/1000).toLocaleString('fi-FI',{maximumFractionDigits:1})+' s · eristetyt testitilat':busy?'Palvelua ajetaan nyt · odota tuloksia':'Uusi eristetty testitila jokaiselle skenaariolle';
  $('scenario-count').textContent=state.scenarios.length+' tilannetta';
  $('run-short').textContent=state.runId?'AJO '+state.runId.slice(0,8).toUpperCase():'EI AJOA';
  const result=state.results.find(value=>value.scenarioId===selected),scenario=state.scenarios.find(value=>value.id===selected);
  $('trace-title').textContent=scenario?.title??'Näe mitä tapahtui.';
  $('trace-description').textContent=scenario?.description??'Valitse skenaario nähdäksesi tapahtumaketjun.';
  const status=result?.outcome??(busy?'RUNNING':'NOT_RUN');
  $('trace-state').textContent=labels[status]??'Tarkistamaton';$('trace-state').className='status '+({PASS:'pass',FAIL:'fail',RUNNING:'running'}[status]??'waiting');
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
      if(item.expected!==undefined)detail.append(node('p','Odotus: '+safeText(item.expected)));
      if(item.observed!==undefined)detail.append(node('p',safeText(item.observed),'observed'));
      li.append(detail);steps.append(li);
    }
  }else{
    const li=node('li',undefined,'empty'),detail=node('div');li.append(node('span',busy?'◌':'◎'));detail.append(node('h3',busy?'Testitoimijat suorittavat ostopolkua':'Tämä tilanne odottaa ajoa'),node('p',busy?'Tulos tulee näkyviin, kun palvelun tarkistukset valmistuvat.':'Suorita kaikki tai aja valittu skenaario.'));li.append(detail);steps.append(li);
  }
  const receipt=$('receipt');receipt.replaceChildren();receipt.hidden=!result?.summary;
  const summaryLabels={orderId:'Testitilaus',quoteId:'Tarjous',totalCents:'Testisumma',amountCents:'Testisumma',orderCount:'Luodut tilaukset',orders:'Luodut tilaukset',transferCount:'Maksusiirrot',transfers:'Maksusiirrot',refundBalanced:'Alkusaldo palautui',walletRestored:'Alkusaldo palautui',missingLitres:'Puuttuva määrä (L)',externalProviderCalls:'Ulkoiset toimittajakutsut'};
  for(const [key,value]of Object.entries(result?.summary??{})){
    const text=['totalCents','amountCents'].includes(key)&&Number.isSafeInteger(value)?new Intl.NumberFormat('fi-FI',{style:'currency',currency:'EUR'}).format(value/100):typeof value==='boolean'?(value?'Kyllä':'Ei'):safeText(value);
    receipt.append(node('dt',summaryLabels[key]??key),node('dd',text));
  }
  const commit=state.source?.commit;
  $('source').textContent=/^[a-f0-9]{40}$/.test(commit??'')?'Lähde '+commit.slice(0,10)+(state.source.worktreeDirty?' · työversio':''):'Lähdeversio ei saatavilla';
}
async function refresh(){try{state=await request('/api/simulation/status');render();}catch(e){error(e.message);}}
async function run(scenario){
  if(pending||state?.busy)return;
  pending=true;state={...state,busy:true,outcome:'RUNNING',results:[],startedAt:new Date().toISOString(),completedAt:null};error(null);render();
  pollTimer=setInterval(()=>{void refresh();},600);
  try{state=await request('/api/simulation/run',{scenario});if(state.outcome==='FAIL')error('Yksi tarkistus epäonnistui. Tapahtumaketju säilyttää toteutuneen tuloksen.');}
  catch(e){error(e.message);await refresh();}
  finally{pending=false;clearInterval(pollTimer);pollTimer=null;render();}
}
$('run-all').addEventListener('click',()=>{selected='purchase';void run('all');});
$('run-one').addEventListener('click',()=>{selected=$('scenario-select').value;void run(selected);});
try{
  state=await request('/api/simulation/status');
  for(const item of state.scenarios)$('scenario-select').append(new Option(item.title,item.id));
  render();
  if(state.busy)pollTimer=setInterval(()=>{void refresh().then(()=>{if(!state?.busy){clearInterval(pollTimer);pollTimer=null;}});},600);
}catch(e){error(e.message);$('run-all').disabled=$('run-one').disabled=true;}
