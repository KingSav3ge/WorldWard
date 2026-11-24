'use strict';
let riseDraft=null,riseReview=null,riseSetupRequest=0;
const riseCreationKey='irgs-rise-create-pending';
function riseElapsedLabel(seconds){
  const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),remaining=seconds%60;
  return [hours?`${hours} h`:'',minutes?`${minutes} min`:'',remaining?`${remaining} s`:''].filter(Boolean).join(' ')||'0 min';
}

function riseCard(campaign){
  return `<article class="panel library-campaign rise-library"><span class="eyebrow">SETTLEMENT CAMPAIGN</span><h2>${esc(campaign.title)}</h2><p>${esc(campaign.summary)}</p><p class="note">Start with a clearly fictional founding example. Its work, travel and provision values are disclosed before you begin.</p><button type="button" class="primary" data-rise-setup>Begin a founding story</button><details><summary>All eight design families</summary><ul>${(campaign.templates||[]).filter(t=>t.id!=='R00').map(t=>`<li>${esc(t.id)} · ${esc(t.title)} — ${esc(t.status)}</li>`).join('')}</ul></details></article>`;
}

function riseChoicesForm(){
  const d=riseDraft||{name:'',template_id:'R00',founder_name:'',household_name:'',settlement_name:'',region_name:'Greywater Reach',date_label:'Spring, Year 1',company:'solo',permission:'seek',supplies:'basic'};
  const input=(key,title)=>`<label>${esc(title)}<input name="${key}" required maxlength="${key==='name'?100:80}" value="${esc(d[key])}"></label>`;
  const select=(key,title,options)=>`<label>${esc(title)}<select name="${key}">${options.map(([value,text])=>`<option value="${value}"${d[key]===value?' selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
  return `<form id="rise-form"><span class="eyebrow">THE RISE OF... YOU · FICTIONAL START</span><h2 id="rise-title">A place to begin.</h2><p>Choose your founder and starting means. Nothing is saved until you review and confirm. Other households keep their own goods and choices.</p><div class="setup-fields">${input('name','Campaign name')}${input('founder_name','Founder name')}${input('household_name','Household name')}${input('settlement_name','Settlement name')}${input('region_name','Fictional region name')}${input('date_label','Fictional opening date label')}</div>${select('company','Starting company',[['solo','Solo founder'],['sibling','Founder and adult sibling Rowan'],['two_households','Founder and an independent Mira household']])}${select('permission','Founding permission',[['seek','Seek a grant during play'],['held','Arrive with a received and accepted limited grant']])}${select('supplies','Actual founder-household supplies',[['basic','Basic · 12 grain, 6 timber, 1 axe'],['stocked','Stocked · 20 grain, 9 timber, 1 axe']])}${select('offer_profile','Optional household offers',[['','No stock offers'],['founder-household-offer-v1','Allow reviewed founder-household offer attempts']])}<p class="note">An offer is a proposal. It does not reserve or transfer goods, or give another person's consent.</p>${select('needs_profile','Optional ordinary needs',[['','No hunger or fatigue rules'],['rise-needs-1','Hunger, fatigue and steward relief']])}<p class="note">With needs, unfed people cannot work until fed, four hours of work requires rest, and Steward Elin may lend grain after a shortfall in return for footpath upkeep.</p><p class="note">Grain is measured in portions; timber in prepared bundles. Two grain portions are protected seed from that same inventory. Company and grant choices add no founder supplies.</p><p id="rise-error" role="status"></p><div class="buttons"><button class="primary" type="submit">Review starting facts</button><button class="quiet" type="button" data-rise-close>Cancel</button></div></form>`;
}

function bindRiseClose(){document.querySelectorAll('[data-rise-close]').forEach(button=>button.onclick=()=>{if(!busy)$('#rise-dialog').close();});}
async function openRiseSetup(){
  if(busy)return;
  const dialog=$('#rise-dialog');++riseSetupRequest;
  if(!dialog.open)dialog.showModal();
  dialog.oncancel=event=>{if(busy)event.preventDefault();};
  if(readLocal(riseCreationKey)){
    $('#rise-content').innerHTML='<h2 id="rise-title">Recover your founding story</h2><p>An earlier creation request is awaiting confirmation. Retrieve it using the same identity before starting another.</p><p id="rise-error" role="status"></p><div class="buttons"><button class="primary" id="rise-recover">Check / retry saved creation</button><button class="quiet" data-rise-close>Close</button></div>';
    $('#rise-recover').onclick=()=>saveRiseCreation(readLocal(riseCreationKey));bindRiseClose();return;
  }
  riseReview=null;$('#rise-content').innerHTML=riseChoicesForm();bindRiseClose();
  dialog.scrollTop=0;$('#rise-form [name="name"]').focus();
  $('#rise-form').onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    const form=new FormData(event.currentTarget),values=Object.fromEntries(form.entries());
    riseDraft={...values,template_id:'R00'};
    const {name,...choices}=riseDraft;if(!choices.offer_profile)delete choices.offer_profile;if(!choices.needs_profile)delete choices.needs_profile;const request=++riseSetupRequest;
    setBusy(true);
    try{const result=await api('rise/preview',{choices},{creator:false});if(request!==riseSetupRequest||!dialog.open)return;riseReview=result;renderRiseReview(name);}
    catch(error){if(dialog.open&&$('#rise-error'))$('#rise-error').textContent=error.message;}
    finally{setBusy(false);}
  };
}

function renderRiseReview(name){
  const r=riseReview,m=r.model,c=r.choices;
  $('#rise-content').innerHTML=`<span class="eyebrow">REVIEW YOUR START</span><h2 id="rise-title">${esc(name)}</h2><dl class="rise-facts"><dt>Founder / household</dt><dd>${esc(c.founder_name)} / ${esc(c.household_name)}</dd><dt>Future settlement</dt><dd>${esc(c.settlement_name)}</dd><dt>Fictional place and opening date</dt><dd>${esc(c.region_name)} · ${esc(c.date_label)}</dd></dl><h3>Company and control</h3><ul>${r.company.map(p=>`<li>${esc(p)}</li>`).join('')}</ul><p>${esc(r.control)}</p><h3>Permission and means</h3><p>${esc(r.permission)}</p><p>${esc(r.terms)}</p><p>Your household actually owns ${esc(r.founder_household_stocks.grain)} grain portions, ${esc(r.founder_household_stocks.timber)} prepared timber bundles and one serviceable axe.</p><p>${esc(r.neighbors)}</p>${r.offer_setup?`<h3>Optional household offers</h3><p>${esc(r.offer_setup.scope)}</p><p>${esc(r.offer_setup.notice)}</p><p>Household account: ${esc(r.offer_setup.account)} · Offer authority: ${esc(r.offer_setup.mandate_id)}</p><p class="note">Source: ${esc(r.offer_setup.source_ref)}</p>`:''}${r.needs_setup?`<h3>Ordinary needs</h3><p>${esc(r.needs_setup.summary)}</p><ul>${r.needs_setup.limits.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><p class="note">${esc(r.needs_setup.status)} · Source: ${esc(r.needs_setup.source_ref)}</p>`:''}<h3>Selected fictional procedures</h3><p>A walk takes ${m.travel_seconds} seconds. A shelter requires ${m.shelter_seconds} seconds of one person's work and ${m.shelter_timber} timber bundles, with an axe retained as a tool; it provides ${m.shelter_places} places. Oren's independent repair takes ${m.repair_seconds} seconds and ${m.repair_timber} timber bundle.</p><p>Every ${m.provision_interval_seconds} seconds, each household member needs ${m.grain_per_person} grain portion. ${m.protected_seed_grain} portions are protected seed within existing grain. Oren's agreed migration takes ${m.migration_seconds} seconds. These are authored demonstration values, not historical calibration.</p><p>At your stores you can inspect your household's current goods and provision ledger. Local work and camp presence are visible where you are; distant private records remain unavailable.</p><p>${esc(r.continuation)}</p><ul>${m.limits.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><label class="rise-confirm"><input id="rise-confirm" type="checkbox">I confirm these starting facts, company relationships and fictional procedures.</label><p id="rise-error" role="status"></p><div class="buttons"><button class="primary" id="rise-create" disabled>Start founding story</button><button class="quiet" id="rise-back">Back to choices</button><button class="quiet" data-rise-close>Cancel</button></div>`;
  $('#rise-dialog').scrollTop=0;$('#rise-title').setAttribute('tabindex','-1');$('#rise-title').focus();
  $('#rise-confirm').onchange=()=>{$('#rise-create').disabled=busy||!$('#rise-confirm').checked;};
  $('#rise-back').onclick=()=>{if(!busy)openRiseSetup();};bindRiseClose();
  $('#rise-create').onclick=async()=>{
    if(busy||!$('#rise-confirm').checked)return;
    const payload={name,choices:r.choices,review_digest:r.review_digest,request_id:crypto.randomUUID()};
    writeLocal(riseCreationKey,payload);await saveRiseCreation(payload);
  };
}

async function saveRiseCreation(payload){
  if(busy||!payload)return;setBusy(true);
  document.querySelectorAll('#rise-dialog button,#rise-dialog input').forEach(button=>button.disabled=true);
  try{
    const saved=await api('rise/create',payload,{creator:false});writeLocal(riseCreationKey,null);$('#rise-dialog').close();
    await refreshList(saved.status==='trashed'?undefined:saved.id);
    if(saved.status==='trashed'){changeView('trash');notice(routineText('campaign.rise_trashed'));return;}
    workspaceMode='player';view='story';updateViewRoute('story');await openCampaign(saved.id);notice(routineText('campaign.rise_created'));
  }catch(error){
    if(error.status&&error.status<500){writeLocal(riseCreationKey,null);$('#rise-content').innerHTML='<h2 id="rise-title">Review your starting choices</h2><p id="rise-error" role="status"></p><button class="quiet" id="rise-review-again">Return to setup</button>';$('#rise-error').textContent=error.message;$('#rise-review-again').onclick=openRiseSetup;}
    else{$('#rise-content').innerHTML='<h2 id="rise-title">Confirmation pending</h2><p id="rise-error" role="status">Your request may already be saved. Recover it before creating another story.</p><button class="primary" id="rise-recover">Check / retry saved creation</button>';$('#rise-recover').onclick=()=>saveRiseCreation(readLocal(riseCreationKey));}
  }finally{setBusy(false);}
}

function renderRiseStory(){
  const s=current.settlement;
  const context=`<details class="story-context"><summary>Current camp, supplies & work</summary>${s.camp?`<h3>Your camp</h3><p>${s.camp.residents} residents · ${s.camp.present} present · ${s.camp.shelter_places} shelter places · ${s.camp.shelter_shortfall} without a shelter place.</p>`:''}<h3>${esc(s.household_name)} · supplies</h3>${s.inventory?`<ul>${s.inventory.map(item=>`<li>${esc(item.quantity)} ${esc(item.material)} · ${esc(item.unit||'unit not configured')} (${esc(item.available)} available${item.reserved_for_work?`; ${esc(item.reserved_for_work)} reserved for work`:''})</li>`).join('')}</ul><p class="note">${s.seed_reserve} grain portions are protected seed within this stock.</p>`:'<p>Your stores are elsewhere. Return to inspect current quantities.</p>'}${s.provision?`<p>Last provision at ${s.provision.at} elapsed seconds: ${s.provision.delivered} delivered / ${s.provision.demand} needed; deficit ${s.provision.deficit}. No health effect is inferred.</p>`:''}${s.projects.length?`<h3>Local work</h3>${s.projects.map(p=>`<p>${esc(p.worker)} · ${esc(p.kind)} · ${esc(p.status)}<br><small>${esc(riseElapsedLabel(p.worked_seconds))} / ${esc(riseElapsedLabel(p.required_seconds))} worked</small></p>`).join('')}`:''}<h3>Supported scope</h3><ul>${s.limits.map(text=>`<li>${esc(text)}</li>`).join('')}</ul><p>Freeform responses remain unresolved intent. A saved-result lookup takes no new time.</p></details>`;
  $('#content').innerHTML=`<div class="story-reading rise-story"><header class="scene-header"><span class="eyebrow">THE RISE OF... YOU · ${esc(s.region)}</span><h2>${esc(s.camp?.name||label(s.location))}</h2><p>${esc(s.opening_date)} · ${esc(riseElapsedLabel(s.elapsed_seconds))} since arrival</p><p>${esc(s.people.join(', '))}</p></header>${context}${storyToolsMarkup()}<div id="story-feed" class="story-feed" aria-label="Your story, oldest to newest"></div><div id="feed-end" tabindex="-1"></div><section class="story-decisions" aria-label="Your next move"><section class="rise-next" ${current.pending_declaration?'hidden':''}><h3>Your next choice</h3><p class="note">These are intentions. Each action checks current permission, presence and means when submitted.</p><div class="rise-actions">${s.actions.map(a=>`<button type="button" class="quiet" data-rise-action="${esc(a.id)}"><strong>${esc(a.title)}</strong><small>${esc(a.description)}</small></button>`).join('')}</div></section>${processControlsMarkup()}${communicationControlsMarkup()}</section></div>`;
  bindStoryFeed();
  $('#declaration').placeholder='Describe what your character says or attempts…';
  const campaign=current.id,actor=current.actor_id;
  document.querySelectorAll('[data-rise-action]').forEach(button=>button.onclick=()=>reviewRiseAction(button.dataset.riseAction,campaign,actor));bindProcessControls();bindCommunicationControls();syncComposer();
}

async function submitRiseAction(action,campaign,actor){
  if(busy||workspaceMode!=='player'||current?.id!==campaign||current?.actor_id!==actor||current.pending_declaration||transportPending||!current.settlement?.actions.some(item=>item.id===action))return;
  const pending={endpoint:'rise/action',body:{id:campaign,revision:current.revision,actor,action,request_id:crypto.randomUUID()}};
  storeTransport(pending);await deliverAction(pending);
}
