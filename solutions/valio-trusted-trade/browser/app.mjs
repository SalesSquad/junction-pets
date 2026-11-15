import { BrowserWorkspace, runBrowserScenario, scenarioDefinitions } from './runtime.mjs';
const $=id=>document.getElementById(id),workspace=new BrowserWorkspace();
const money=value=>new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR'}).format(value/100);
const node=(tag,text,className)=>{const result=document.createElement(tag);if(text!==undefined)result.textContent=text;if(className)result.className=className;return result;};
let view=null,busy=true,dirty=false,expiryTimer;
const error=value=>{$('error').textContent=value??'';$('error').hidden=!value;};
const binding=()=>({quoteId:view.quote.id,snapshotId:view.quote.snapshotId});
const setDisabled=(id,disabled)=>{$(id).disabled=disabled;};
function render(){
  clearTimeout(expiryTimer);const blocked=busy||workspace.blocked||!view,q=view?.quote,order=view?.order,pay=view?.payment;
  const active=order?.status==='SIMULATED_COMMITTED',current=view?.freshness==='CURRENT',approved=q&&['APPROVED','AUTO_COMMIT_ELIGIBLE'].includes(q.status);
  $('storage-status').textContent=workspace.blocked?'STORAGE BLOCKED · no new purchasing effects':view?'Saved locally · cross-tab locking enabled':'Checking storage & Ed25519…';
  for(const id of ['milk','oat','budget','portfolio-preset','exception-preset'])$(id).disabled=blocked||active;
  setDisabled('plan',blocked||active);setDisabled('simulate-stale',blocked||active);setDisabled('run-scenarios',blocked);
  $('plan-status').textContent=dirty?'INPUT CHANGED':view?.plan?'OPTIONS CHECKED':view?.review?'SINGLE NEED REVIEW':'AWAITING NEED';
  const options=$('options-grid');options.replaceChildren();
  if(view?.plan){for(const option of view.plan.options){
    const card=node('button',undefined,'option-card'+(q?.optionId===option.id?' selected':''));card.type='button';card.dataset.option=option.id;card.dataset.testid='option-'+option.id;
    card.disabled=blocked||dirty||Boolean(order)||!option.withinBudget;
    card.append(node('strong',option.title),node('span',money(option.totalCents),'price'),node('small',option.equivalentTo?'Same allocation as '+option.equivalentTo:option.explanation),
      node('span',option.supplierCount+' suppliers · '+option.largestSupplierExposurePct+'% largest exposure','metric'),node('small',option.carbonKgEstimate+' kg estimated · fictional'));
    card.addEventListener('click',()=>act('select',{planId:view.plan.id,optionId:option.id}));options.append(card);
  }}else if(view?.review){const card=node('div',undefined,'option-card single-option');card.append(node('strong',q?'One exact source-bound basket':'Exact need cannot be fulfilled'),
    node('span',q?money(q.totalCents):'No eligible quote','price'),node('small',q?'Single-product exception review uses the original deterministic buyer flow.':view.review.diagnosis.explanation));options.append(card);
  }else options.append(node('div','Define your need to compare cost, resilience and footprint.','placeholder'));
  $('quote-content').hidden=!q;$('quote-empty').hidden=Boolean(q);
  $('quote-status').textContent=dirty?'REQUEST EDITED':!q?'NO QUOTE':!current?view.freshness.replaceAll('_',' '):q.status.replaceAll('_',' ');
  if(q){
    $('quote-id').textContent=q.id;$('quote-expiry').textContent='Fixed until '+new Date(q.expiresAtMs).toLocaleTimeString();
    $('quote-lines').replaceChildren();for(const line of q.lines){const item=node('div',undefined,'line'),description=node('div');
      description.append(node('b',line.quantityLitres+' L · '+(line.family==='dairy-milk'?'Lactose-free milk':'Oat drink')),node('small',line.sku+' · '+line.packs+' whole pack(s) × '+line.packLitres+' L · stock v'+line.stockVersion));
      item.append(description,node('span',money(line.totalCents)));$('quote-lines').append(item);
    }
    $('quote-total').textContent=money(q.totalCents);$('exception').hidden=!q.budgetException;
    if(q.budgetException)$('exception-copy').textContent=money(q.budgetException.originalBudgetCents)+' → '+money(q.totalCents)+'. Approve '+money(q.budgetException.additionalCents)+' extra for this quote only.';
    $('approve').textContent=q.budgetException?'Approve '+money(q.budgetException.additionalCents)+' exception & this quote':'Approve displayed quote';
    $('quote-context').textContent=dirty?'Your edited inputs never change this existing proposal. Prepare a fresh need before consent.':
      !current?'Current evidence invalidates this offer. Prepare a new quote and decision.':'Snapshot '+q.snapshotId.slice(0,24)+'… · stock checked, not reserved · no real supplier connected.';
    if(!order&&q.expiresAtMs>Date.now())expiryTimer=setTimeout(refresh,Math.min(2147483647,q.expiresAtMs-Date.now()+15));
  }
  setDisabled('approve',blocked||dirty||!q||!current||q.status!=='AWAITING_HUMAN_APPROVAL');setDisabled('reject',$('approve').disabled);
  setDisabled('prove',blocked||dirty||!q||!current||!approved||Boolean(order));
  $('proof-status').textContent=view?.proof?'Both envelopes cryptographically verified · self-attested local keys':approved?'Ready for an exact buyer mandate.':'Approval precedes signing.';
  $('proof-details').hidden=!view?.proof;
  if(view?.proof)$('proof-digests').textContent='Quote body: '+view.proof.verification.quoteBodyDigest+'\nOffer: '+view.proof.verification.signedOfferDigest+'\nMandate: '+view.proof.verification.signedMandateDigest;
  setDisabled('commit',blocked||dirty||!q||!current||!approved||!view.proof||Boolean(order));
  setDisabled('replay',blocked||!active);setDisabled('cancel',blocked||!active);
  $('order-status').textContent=order?order.status.replaceAll('_',' '):'NO ORDER';
  $('order-copy').textContent=order?'Receipt '+order.id+'. '+(active?'Retry retains this exact commitment; no second stock deduction.':'The synthetic order is cancelled and any settled test amount is refunded.'):'Exact source, approval and proof are rechecked before local stock changes.';
  $('wallet-balance').textContent=money(view?.wallet.buyerBalanceCents??250000);
  $('payment-status').textContent=pay?.transfer?pay.transfer.status.replaceAll('_',' '):pay?.approval?'PAYMENT APPROVED':'NO PAYMENT';
  $('payment-copy').textContent=pay?'Exact proposal: '+money(pay.proposal.amountCents)+' for '+order.id+'. Purchase consent and payment consent remain separate.':'Purchase approval does not authorize payment. Confirm the exact proposal separately.';
  setDisabled('payment-approve',blocked||!active||!pay||Boolean(pay.transfer)||pay.approval?.decision==='approve');
  setDisabled('settle',blocked||!active||!pay||pay.approval?.decision!=='approve');
  $('audit-valid').textContent=view?.auditValid?'HASH LINKS VALID · LOCAL ONLY':'NO EXTERNAL AUDIT';$('audit-count').textContent=(view?.auditCount??0)+' local recorded events · showing the most recent 30.';
  $('audit-list').replaceChildren();for(const receipt of [...(view?.audit??[])].reverse()){
    const item=node('li');item.append(node('b',receipt.event.replaceAll('_',' ')),node('small',new Date(receipt.time).toLocaleTimeString()+' · '+receipt.id));$('audit-list').append(item);
  }
  renderScenarios(view?.simulations??[]);
}
function renderScenarios(results){
  const root=$('scenario-results');root.replaceChildren();
  if(!results.length){root.append(node('p','Purchase · rejection · stale source · persisted retry · shortage · expiry','microcopy'));return;}
  for(const result of results){const card=node('div',undefined,'scenario-result'+(result.outcome==='FAIL'?' failed':''));card.dataset.scenario=result.id;
    card.append(node('b',result.title),node('span',result.outcome+' · '+result.elapsedMs+' ms · browser-local only'));
    const list=node('ol');for(const step of result.steps){const code=step.observed?.code;list.append(node('li',step.title+' — '+step.outcome+(code?' ('+code+')':'')));}card.append(list);root.append(card);
  }
}
async function refresh(){if(busy)return;try{view=await workspace.read();render();}catch(failure){error((failure.code??'BROWSER_FAILURE')+': '+failure.message);render();}}
async function act(action,payload={}){
  if(busy||workspace.blocked)return;busy=true;error();render();
  try{view=await workspace.command(action,{...(view?.quote?binding():{}),...payload});if(action==='prepare'||action==='select')dirty=false;}
  catch(failure){error((failure.code??'BROWSER_FAILURE')+': '+failure.message);try{if(!workspace.blocked)view=await workspace.read();}catch{}}
  finally{busy=false;render();}
}
$('mission-form').addEventListener('submit',event=>{event.preventDefault();
  if(!$('mission-form').reportValidity())return;
  const amount=$('budget').value;if(!/^[0-9]+(?:\.[0-9]{1,2})?$/.test(amount)){error('INVALID_BUDGET: Enter whole cents, without scientific notation or fractional cents.');return;}
  const [euros,cents='']=amount.split('.'),budgetCents=Number(euros)*100+Number(cents.padEnd(2,'0'));
  act('prepare',{milkLitres:Number($('milk').value),oatLitres:Number($('oat').value),budgetCents});
});
for(const id of ['milk','oat','budget'])$(id).addEventListener('input',()=>{dirty=Boolean(view?.quote||view?.plan);render();});
function preset(milk,oat,budget){$('milk').value=milk;$('oat').value=oat;$('budget').value=budget;dirty=Boolean(view?.quote||view?.plan);render();}
$('portfolio-preset').addEventListener('click',()=>preset(480,240,1750));$('exception-preset').addEventListener('click',()=>preset(1000,0,1400));
for(const [id,action] of [['approve','approve'],['reject','reject'],['prove','prove'],['commit','commit'],['replay','replay'],['cancel','cancel'],['settle','settle'],['simulate-stale','reprice']])$(id).addEventListener('click',()=>act(action));
$('payment-approve').addEventListener('click',()=>act('payment-approve',{proposalDigest:view.payment.proposal.digest}));
$('run-scenarios').addEventListener('click',async()=>{
  if(busy||workspace.blocked)return;busy=true;error();render();const results=[];
  try{for(const definition of scenarioDefinitions){results.push(await runBrowserScenario(definition.id));renderScenarios(results);}
    view=await workspace.command('simulations',{results});
  }catch(failure){error((failure.code??'BROWSER_FAILURE')+': '+failure.message);}
  finally{busy=false;render();}
});
workspace.subscribe(refresh);window.addEventListener('focus',refresh);
window.addEventListener('pagehide',event=>{if(!event.persisted){clearTimeout(expiryTimer);workspace.close();}});
Object.defineProperty(window,'valioAimoApp',{value:Object.freeze({scope:'BROWSER_LOCAL_SYNTHETIC',inspect:()=>workspace.read()})});
try{view=await workspace.read();const needs=view.intent?.requirements;
  if(needs){$('milk').value=needs.find(need=>need.family==='dairy-milk')?.quantityLitres??0;$('oat').value=needs.find(need=>need.family==='oat-drink')?.quantityLitres??0;$('budget').value=view.intent.budgetCents/100;}
}catch(failure){error((failure.code??'BROWSER_FAILURE')+': '+failure.message);}
finally{busy=false;render();}
