'use strict';
const $=selector=>document.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const label=value=>String(value??'').replaceAll('_',' ').replace(/\b\w/g,char=>char.toUpperCase());
const rows=value=>Array.isArray(value)?value.map((item,index)=>item&&typeof item==='object'?item:{id:String(index),name:String(item)}):Object.entries(value||{}).map(([id,item])=>item&&typeof item==='object'?{id,...item}:{id,name:String(item)});
let token,current=null,currentBinding=null,view='story',workspaceMode='player',busy=false,library={},deleteTarget=null,campaignRequest=0,loadingCampaign=false;
let historicalCatalogue=null,historicalEntryId=null,historicalPreview=null,historicalRequest=0,historicalLoading=false;
let startPreviewRequest=0,startCheckLoading=false,openingSelectionKey=null;
let wizardStep=0,startingOptions=null,startingRequest=0,startingLoading=false,reviewSelection=null,chronicleRequest=0,chronicleCursor=null,transportPending=null,inspectorRequest=0;
let campaignSummaries=[];
let features=[],featuresRequest=0,contentLibraryRequest=0,routeFeatureId=null,approvedEntries=new Map(),setupEntryContext=null,createDialogRequest=0;
const scrollPositions=new Map();
const defaultPreferences={theme:'dark',font:'serif',fontSize:18,lineHeight:1.8,width:740,mechanics:'concise',motion:'system',submitKey:'ctrl-enter'};
function readLocal(key,fallback=null){try{const value=localStorage.getItem(key);return value===null?fallback:JSON.parse(value);}catch{return fallback;}}
function writeLocal(key,value){try{if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,JSON.stringify(value));}catch{}}
let preferences={...defaultPreferences,...readLocal('irgs-reading-preferences',{})};
function notice(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';}
async function api(path,body,options={}){
  const creator=options.creator??workspaceMode==='creator';
  if(creator&&!/[?&]mode=/.test(path))path+=(path.includes('?')?'&':'?')+'mode=creator';
  const headers={'X-IRGS-Token':token||''};
  const request={headers};
  if(body!==undefined){headers['Content-Type']='application/json';request.method='POST';request.body=JSON.stringify(creator?{...body,mode:'creator'}:body);}
  const response=await fetch('/api/'+path,request);
  let result;try{result=await response.json();}catch{const error=new Error('The host returned an unreadable response. Check the saved request before retrying.');error.status=response.status;throw error;}
  if(!response.ok){const error=new Error(result.error||'Request failed');error.status=response.status;error.data=result;throw error;}
  return result;
}
function profileId(){return current?.binding?.campaign_profile||current?.state?.binding?.campaign_profile||'ast';}
function profileInfo(){return rows(library.campaign_profiles).find(profile=>profile.id===profileId())||{};}
function actors(){return workspaceMode==='creator'?current?.state?.actors||{}:Object.fromEntries([...(current?.known_actors||[]),...(current?.character?[current.character]:[])].map(actor=>[actor.id,actor]));}
function playerActor(){return current?.actor_id||null;}
function registry(id){return workspaceMode==='creator'?current?.state?.registry?.characters?.[id]||{}:{};}
function valueText(value){if(value===null||value===undefined)return 'Not established';if(typeof value==='object')return 'value'in value?String(value.value):JSON.stringify(value);return String(value);}
function facts(object,empty='No accessible records are established.'){return Object.entries(object||{}).map(([key,value])=>`<div class="list-row"><small>${esc(label(key))}</small><strong>${esc(valueText(value))}</strong></div>`).join('')||`<p class="note">${esc(empty)}</p>`;}
function records(items,empty){const list=rows(items);return list.length?list.map(item=>`<article class="record-card"><h3>${esc(item.name||item.title||item.description||item.id||'Record')}</h3>${facts(Object.fromEntries(Object.entries(item).filter(([key])=>!['name','title','id'].includes(key))))}</article>`).join(''):`<p class="note">${esc(empty)}</p>`;}
function viewKey(name=view){return [current?.id||'',current?.actor_id||'',workspaceMode,name].join(':');}
function rememberScroll(){if(current){const area=$('#reading-scroll');scrollPositions.set(viewKey(),{top:area.scrollTop||0,atEnd:area.scrollHeight-area.clientHeight-area.scrollTop<80});}}
function restoreScroll(){const key=viewKey();requestAnimationFrame(()=>{if(key!==viewKey())return;const area=$('#reading-scroll'),saved=scrollPositions.get(key);area.scrollTop=view==='story'&&(!saved||saved.atEnd)?area.scrollHeight:saved?.top||0;});}
function draftKey(){return current?`irgs-draft:${current.id}:${current.actor_id||'none'}`:null;}
function pendingKey(){return current?`irgs-pending:${current.id}:${current.actor_id||'none'}`:null;}
function stashDraft(){const key=draftKey();if(key)writeLocal(key,$('#declaration').value||'');}
function loadDraft(){const key=draftKey();$('#declaration').value=key?readLocal(key,''):'';transportPending=pendingKey()?readLocal(pendingKey()):null;loadSoloAttempt();}
function receivedCivilTime(){const civil=current?.start_context?.civil_time||current?.campaign_time?.civil;return civil?.status==='received_initial_checkpoint'&&civil.current_calendar_binding===false?civil:null;}
function displayTime(){
 if(current?.settlement)return current.settlement.opening_date+' · '+riseElapsedLabel(current.settlement.elapsed_seconds)+' since arrival';
 const civil=receivedCivilTime();if(civil)return `${civil.date} · ${label(civil.calendar)} · ${civil.precision} precision · ${civil.time||'hour unknown'}`;
 const time=current?.campaign_time||{};return [time.date||time.calendar_date||(time.day!==undefined?'Day '+time.day:null),time.time||'time unknown',time.precision&&time.precision!=='exact'?time.precision:null].filter(Boolean).join(' · ');
}
async function refreshList(selected){const data=await api('campaigns');token=data.token;const build=data.build,identity=$('#build-identity');if(identity&&build){identity.textContent='WorldWard '+(build.edition||'unknown')+' '+(build.classification==='pre_alpha'?'Pre-Alpha':'')+' · App '+(build.app_manifest_sha256||'unknown').slice(0,12)+' · Engine '+(build.engine_manifest_sha256||'unknown').slice(0,12)+' · Catalog '+(build.catalog_manifest_sha256||'unknown').slice(0,12);identity.title='Manifest SHA-256: App '+(build.app_manifest_sha256||'unavailable')+'; Engine '+(build.engine_manifest_sha256||'unavailable')+'; Catalog '+(build.catalog_manifest_sha256||'unavailable')+'. These fingerprints identify selected manifests, not a full integrity check.';}else if(identity){identity.textContent='Running host does not report its build';identity.title='This host may be an older installation. Restart the intended build to identify it.';}campaignSummaries=data.campaigns;$('#campaign').innerHTML='<option value="">Choose a campaign</option>'+data.campaigns.map(campaign=>`<option value="${esc(campaign.id)}">${esc(campaign.name)}</option>`).join('');if(selected)$('#campaign').value=selected;return data.campaigns;}
function syncControls(){
  const selected=current&&!loadingCampaign&&$('#campaign').value===current.id;
  $('#campaign').disabled=busy||!token;$('#player-character').disabled=busy||!selected||!(current?.controlled_actors||[]).length;
  $('#new-campaign').disabled=busy||!token;$('#new-campaign').textContent=workspaceMode==='creator'?'+ Creator initialization':'+ New playthrough';$('#workspace-mode').disabled=busy||!token;
  $('#export').disabled=$('#delete-campaign').disabled=busy||!selected;$('#fork').disabled=busy||!selected||workspaceMode!=='creator';
  $('#fork').hidden=workspaceMode!=='creator';$('#creator-nav').hidden=workspaceMode!=='creator';$('#library-nav').hidden=workspaceMode!=='creator';
  $('#binding-badge').hidden=workspaceMode!=='creator';
  $('#workspace-mode').textContent=workspaceMode==='creator'?'Return to player view':'Creator workspace';$('#mode-label').textContent=workspaceMode==='creator'?'Creator access · full records':'Player view · filtered by the server';
  $('#mode-badge').textContent=workspaceMode==='creator'?'CREATOR WORKSPACE':'PLAYER VIEW';$('#export').textContent=workspaceMode==='creator'?'Export full save':'Export known view';
  $('#saved').textContent=busy?'Saving…':loadingCampaign?'Loading campaign…':current?`Saved · revision ${current.revision}`:'Local host connected';
  $('#journey-name').textContent=current?.name||'Your adventures';$('#tome-title').textContent=current?.name||'Your story';
  syncCreateControls();syncComposer();
}
function setBusy(value){busy=value;syncControls();}
async function openCampaign(id,options={}){
  stashDraft();rememberScroll();invalidateActionReview();const request=++campaignRequest,selected=id||'',mode=workspaceMode;
  $('#campaign').value=selected;current=null;currentBinding=null;transportPending=null;loadingCampaign=Boolean(selected);render();
  if(!selected){localStorage.removeItem('irgs-active');return true;}
  const query=new URLSearchParams();if(options.actorId)query.set('actor_id',options.actorId);
  try{const result=await api('playthrough/'+encodeURIComponent(selected)+(query.size?'?'+query.toString():''),undefined,{creator:mode==='creator'});
    if(request!==campaignRequest||$('#campaign').value!==selected||workspaceMode!==mode)return false;
    if(result.id!==selected||(mode==='player'&&Object.prototype.hasOwnProperty.call(result,'state')))throw new Error('The host returned an incompatible playthrough view.');
    current=result;currentBinding=result.binding;loadingCampaign=false;localStorage.setItem('irgs-active',selected);
    // Refresh only an existing shelf entry from this accepted host view, never an action receipt.
    if(Number.isSafeInteger(result.revision))campaignSummaries=campaignSummaries.map(summary=>summary.id===result.id?{...summary,name:result.name,revision:result.revision}:summary);
    $('#player-character').innerHTML=(result.controlled_actors||[]).map(actor=>`<option value="${esc(actor.id)}">${esc(actor.name)}</option>`).join('')||'<option value="">No selected player character</option>';$('#player-character').value=result.actor_id||'';
    loadDraft();render();restoreScroll();return true;
  }catch(error){if(request!==campaignRequest||$('#campaign').value!==selected||workspaceMode!==mode)return false;loadingCampaign=false;render();throw error;}
}
function changeView(next,options={}){const drawerOpen=['nav-open','context-open','tools-open'].some(state=>document.body.classList.contains(state));rememberScroll();stashDraft();invalidateActionReview();++historicalReferenceRequest;++inspectorRequest;view=next;if($('#inspect-dialog').open)$('#inspect-dialog').close();closePreviewDrawers();if(options.route!==false)updateViewRoute(next,options.featureId);render();restoreScroll();if(drawerOpen)$('#content').focus({preventScroll:true});}
function empty(){return '<div class="empty adventure-welcome"><div class="welcome-copy"><span class="eyebrow">HISTORY IS ONLY THE BEGINNING</span><h2>Find your place.<br>Choose your path.</h2><p>A life at the edge of a changing world. Begin with a character, a moment in history, and a choice.</p><button id="empty-create" class="primary">Find your adventure <span aria-hidden="true">→</span></button><small>All 37 Century of Conflict starts offer an optional local Solo opening.</small></div><span class="art-caption">Illustrative campaign artwork</span></div>';}
function render(){
  applyPresentationTheme();$('#inspection-note').textContent=routineText('inspection.local');
  document.body.dataset.workspace=view;
  document.body.dataset.mode=workspaceMode;
  const headings={home:['Home','Resume a saved world or browse verified starts.'],story:['Story','Your next meaningful choice.'],world:['World','Inspect what your character can access.'],chronicle:['Chronicle','The record available to your character.'],creator:['Creator workspace','Explicitly sourced changes to the authoritative world.'],library:['Engines & libraries','Creator reference material.'],saves:['Your saved stories','Return to a world you have already begun.'],trash:['Campaign Trash','Recover complete saved campaigns.'],'content-library':['Content Library','Choose a sourced campaign and starting point.']};
  const heading=headings[view]||(view.startsWith('feature:')?[features.find(feature=>feature.id===view.slice(8))?.label||'Unavailable section','Registered section and implementation status.']:headings.story);$('#section-label').textContent=heading[0].toUpperCase();$('#page-title').textContent=current&&['story','world','chronicle','creator'].includes(view)?current.name:heading[0];$('#page-subtitle').textContent=heading[1];
  $('#header-campaign').textContent=current?.name||'Your campaign';$('#world-time').textContent=current?displayTime():'No campaign selected';$('#header-scene').textContent=current?.scene?.location||current?.scene?.title||'Persistent local worlds';
  $('#binding-badge').textContent=current?'Core '+(current.binding?.core||'3.3')+' · '+label(current.binding?.genre_id||'campaign'):'CORE 3.3';
  document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===view;button.classList.toggle('selected',active);if(button.getAttribute('role')==='tab'){button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;}});
  $('#content').setAttribute('role',['story','world','chronicle'].includes(view)?'tabpanel':'region');$('#content').setAttribute('aria-label',heading[0]);$('#content').setAttribute('aria-labelledby',['story','world','chronicle'].includes(view)?'tab-'+view:'page-title');syncControls();renderContext();renderPreviewTools();
  if(loadingCampaign){$('#content').innerHTML='<div class="empty">'+esc(routineText('campaign.loading'))+'</div>';return;}
  if(view==='home'){renderHome();return;}if(view==='saves'){renderPreviewSaves();return;}if(view==='trash'){renderTrash();return;}if(view==='library'){renderLibrary();return;}if(view==='content-library'){renderContentLibrary();return;}if(view.startsWith('feature:')){renderFeature(view.slice(8));return;}
  if(!current){$('#content').innerHTML=empty();$('#empty-create').onclick=openCreateDialog;return;}
  ({story:renderStory,world:renderWorld,chronicle:renderChronicle,creator:renderCreator}[view]||renderStory)();
}
function entryMarkup(entry){
  const status=entry.status||'',kind=entry.kind||'record',title=entry.title||label(kind),text=entry.text??entry.declaration??entry.assertion??'';
  const times=[['occurred',entry.occurrence_at],['observed',entry.observed_at],['transmitted',entry.transmitted_at],['recorded',entry.recorded_at],['received',entry.received_at]].filter(([,value])=>value!==undefined&&value!==null).map(([name,value])=>name+' '+valueText(value));
  const gap=entry.source_available===false||entry.source_gap;
  return `<article class="feed-entry ${esc(kind)}${entry.lastOutcome?' last-outcome':''}" id="entry-${esc(entry.id)}"><div class="entry-meta"><span>${esc(title)}</span>${status?`<span class="badge">${esc(label(status))}</span>`:''}</div><p class="entry-text">${esc(text)}</p>${gap?`<p class="source-gap note">${esc(entry.gap_note||'The original source text is unavailable; no transcript has been reconstructed.')}</p>`:''}<details class="entry-details" ${preferences.mechanics==='expanded'?'open':''}><summary>Record details</summary>${times.length?`<p class="note">${esc(times.join(' · '))}</p>`:''}${entry.source_refs?.length?`<p class="note">${esc(entry.source_refs.join(' · '))}</p>`:''}<button type="button" class="bookmark quiet" data-bookmark="${esc(entry.id)}" aria-pressed="false">Bookmark</button></details></article>`;
}
function renderStory(){
  if(current?.settlement){renderRiseStory();return;}
  const scene=current.scene||{};
  $('#content').innerHTML=`<div class="story-reading"><header class="scene-header"><span class="eyebrow">YOUR STORY${current.character?.name?' · '+esc(current.character.name):''}</span><h2>${esc(scene.title||'Your saved checkpoint')}</h2>${openingElapsedMarkup()}${scene.description?`<p class="scene-prose">${esc(valueText(scene.description))}</p>`:''}</header>${openingMarkup()}${storyToolsMarkup(`<p class="capability-note">${esc(actionCapabilityNote())}</p><p class="note">Looking up a saved record takes no new scene time. Listed durations are local gameplay rules; they do not establish a historical hour.</p>`)}<div id="story-feed" class="story-feed" aria-label="Your story, oldest to newest"></div><div id="feed-end" tabindex="-1"></div><section class="story-decisions" aria-label="Your next move">${playReadinessMarkup()}${responseChoicesMarkup()}${supportedActionsMarkup()}${processControlsMarkup()}${communicationControlsMarkup()}</section></div>`;
  bindStoryFeed();
  if($('#browse-supported-start'))$('#browse-supported-start').onclick=()=>changeView('content-library');
  $('#declaration').placeholder=responseChoices().length?'Write your own response, or edit a suggested answer here…':current.opening?.status==='awaiting_first_action'?'Your first move: describe what you say or attempt. A freeform declaration remains pending until resolved.':'Describe what your character says or attempts…';
  const campaign=current.id,actor=current.actor_id,available=supportedActions(),responses=responseChoices();document.querySelectorAll('[data-supported-action]').forEach(button=>{const action=available[Number(button.dataset.supportedAction)];button.onclick=()=>reviewSupportedAction(action,campaign,actor);});document.querySelectorAll('[data-response-choice]').forEach(button=>{const choice=responses[Number(button.dataset.responseChoice)];button.onclick=()=>chooseResponse(choice.id,campaign,actor,choice.text);});if($('#write-own-response'))$('#write-own-response').onclick=focusOwnResponse;bindProcessControls();bindCommunicationControls();syncComposer();
}
function renderWorld(){
  const world=current.world||{};
  $('#content').innerHTML=`<div class="world-workspace"><div class="panel"><span class="eyebrow">ONE AUTHORITATIVE WORLD</span><h2>The world you can inspect.</h2><p>These records reflect the selected character’s access. Looking around this workspace does not issue an order or advance the clock.</p></div><div class="world-grid"><section class="panel"><h3>Inventory & resources</h3>${records(world.inventory||current.inventory,'No accessible physical inventory records have been established. Quantities remain unknown.')}<button class="quiet" data-inspect="inventory">Inspect inventory</button></section><section class="panel"><h3>People & institutions</h3>${records(world.institutions||world.factions,'No accessible institution or faction records are available.')}<button class="quiet" data-inspect="factions">Inspect institutions</button></section><section class="panel"><h3>Projects & commitments</h3>${records(world.activities,'No accessible project progress is established.')}<button class="quiet" data-inspect="projects">Inspect projects</button></section><section class="panel"><h3>Known places</h3>${records(world.locations,'No known atlas or route records are supplied.')}<button class="quiet" data-inspect="map">Inspect known places</button></section></div><section class="panel time-controls"><h3>Time advancement</h3><p>${current?.settlement?'Use the time and movement choices in Story to advance this selected settlement model. Each request returns at its supported boundary; the civil calendar is unchanged.':current?.capabilities?.playable_opening?'Listed opening actions advance their authored local durations. General wait controls and campaign-calendar advancement remain unavailable.':'Elapsed-time advancement is unavailable because this campaign has no configured elapsed-time binding and automatic resolver.'}</p><label>Requested duration<select id="advance-duration" disabled><option>Until the next required decision</option><option>One hour</option><option>One day</option><option>One week</option><option>One month</option><option>One year</option></select></label><button class="primary" disabled>Time advancement unavailable</button><small>Scene dates and causal record order are preserved. No duration is inferred from the event counter.</small></section></div>`;
  bindInspectors();
}
async function renderChronicle(){
  const request=++chronicleRequest,campaign=current.id,actor=current.actor_id,mode=workspaceMode;
  let searchRequest=0;
  $('#content').innerHTML='<div class="chronicle-workspace"><div class="panel"><h2>Your available history.</h2><form id="chronicle-search"><label>Archive area<select name="area"><option value="timeline">Historical timeline</option><option value="personal">Personal chronicle</option><option value="biographies">Biographies</option><option value="relationships">Relationships</option><option value="institutions">Institutional history</option><option value="archive">Historical archive</option></select></label><label>Search accessible records<input name="q" type="search" placeholder="Event, person or source phrase"></label><button class="primary">Search Chronicle</button></form><p class="note">Only records returned for this character’s scope are shown. Original text and receipt dates retain their meaning.</p></div><div id="chronicle-results" aria-live="polite"></div></div>';
  const load=async(cursor=null)=>{const search=++searchRequest;const fields=Object.fromEntries(new FormData($('#chronicle-search'))),query=new URLSearchParams({...fields,limit:'30'});if(actor)query.set('actor_id',actor);if(cursor)query.set('cursor',cursor);$('#chronicle-results').innerHTML='<p class="note">Loading accessible history…</p>';try{const result=await api('chronicle/'+campaign+'?'+query.toString());if(search!==searchRequest||request!==chronicleRequest||view!=='chronicle'||current?.id!==campaign||current.actor_id!==actor||workspaceMode!==mode)return;const memory=result.memory||{};$('#chronicle-results').innerHTML=`<section class="panel archive-status"><h3>Historical memory</h3><p>${esc(memory.reason||'Archive periods require committed calendar boundaries.')}</p><small>Status: ${esc(memory.status||'unconfigured')} · summary budgets: ${esc(memory.budget_policy?.status||'unconfigured')}</small><p class="note">The consolidation structure is annual → five-year → twenty-five-year → expanding century records → sealed 500-year epochs. No summary is generated by inspecting this screen.</p></section><section class="panel">${(result.entries||[]).map(entryMarkup).join('')||'<p class="note">No accessible records match this area and search.</p>'}${result.pagination?.next_cursor?'<button id="chronicle-next" class="quiet">Next records →</button>':''}</section>`;if($('#chronicle-next'))$('#chronicle-next').onclick=()=>load(result.pagination.next_cursor);}catch(error){if(search===searchRequest&&request===chronicleRequest&&view==='chronicle')$('#chronicle-results').innerHTML=`<p class="note">${esc(error.message)}</p>`;}};
  $('#chronicle-search').onsubmit=event=>{event.preventDefault();load();};load();
}
function renderContext(){renderPreviewContext();}

function bindInspectors(){document.querySelectorAll('[data-inspect]').forEach(button=>button.onclick=()=>openInspector(button.dataset.inspect));}
async function openInspector(kind){
  if(!current)return;const inspect=++inspectorRequest;const world=current.world||{},titles={character:'Character',inventory:'Inventory',relationships:'Relationships',map:'Known places',projects:'Projects & research',factions:'Institutions & factions'};$('#inspect-title').textContent=titles[kind]||'Campaign information';
  const character=current.character;
  if(kind==='character')$('#inspect-content').innerHTML=character?`<h3>${esc(character.name)}</h3><p>${esc(character.species||'Species not established')}</p>${facts(character.current)}${backgroundDetailsMarkup(character.background_details||current.background_details)}<p class="note">Capability ratings, affiliations and possessions appear only when provided as accessible records.</p>`:'<p>No selected player character is available.</p>';
  if(kind==='inventory')$('#inspect-content').innerHTML=records(current.inventory||world.inventory,'No accessible inventory instances are supplied. Ownership, custody, carried location, storage, accessibility and condition remain distinct; none have been inferred from a description.');
  if(kind==='relationships')$('#inspect-content').innerHTML=records(current.relationships||world.relationships,'No accessible relationship or family-tree records have been established.');
  if(kind==='map')$('#inspect-content').innerHTML=records(world.locations,'No known map, routes or atlas are available. Inspecting a location would not move the character.');
  if(kind==='projects')$('#inspect-content').innerHTML=records(world.activities||world.projects,'No accessible projects, research progress or completed outputs are established.');
  if(kind==='factions')$('#inspect-content').innerHTML=records(world.institutions||world.factions,'No accessible institution or faction-control records are established. Existence, participation and control require separate evidence.');
  if(!$('#inspect-dialog').open)$('#inspect-dialog').showModal();
  if(kind==='factions'){const id=current.id,request=campaignRequest;try{const result=await api('availability/'+id+(current.actor_id?'?actor_id='+encodeURIComponent(current.actor_id):''));if(inspect===inspectorRequest&&request===campaignRequest&&current?.id===id&&$('#inspect-dialog').open)$('#inspect-content').innerHTML=records(result.entities?.factions||result.factions,result.reason||'No accessible current factions are established.');}catch(error){notice(error.message,true);}}
}
function renderCreator(){
  if(workspaceMode!=='creator'||!current?.state){$('#content').innerHTML='<div class="empty">Choose Creator workspace explicitly to inspect full records or apply sourced host decisions.</div>';return;}
  renderCreatorJournal();$('#content').insertAdjacentHTML('afterbegin','<section class="panel creator-warning"><span class="eyebrow">FULL RECORD ACCESS</span><h2>Creator tools</h2><p>These controls can inspect and change authoritative records. Player views remain server-filtered when you return.</p><div id="host-tools"></div></section>');mountTools();if(current.state.historical_start)$('#content').insertAdjacentHTML('afterbegin',historicalReferenceMarkup(current.state.historical_start));
}
async function mutate(path,payload){
  if(workspaceMode!=='creator'||busy||loadingCampaign||!current?.state||$('#campaign').value!==current.id)return;
  const target={id:current.id,revision:current.revision},request=campaignRequest;setBusy(true);
  try{const result=await api(path,{...target,...payload});if(request!==campaignRequest||current?.id!==target.id)return;await openCampaign(target.id,{actorId:current.actor_id});notice(result.last_result?.deferred?.length?'Request intent was preserved as unresolved.':'Host decision saved to the authoritative campaign.');}catch(error){notice(error.message,true);}finally{setBusy(false);}
}
function submit(op,params){return mutate('event',{op,params});}function submitBatch(events){return mutate('frontier',{events});}
function textItems(value) {return (Array.isArray(value)?value:value?[value]:[]).map(item=>typeof item==='string'?item:item.statement || item.text || item.summary || JSON.stringify(item));}
function safeHttpUrl(value) {try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)?url.href:null;}catch{return null;}}
function historicalResearchMarkup(research){
  if(!research)return '';
  const records=(research.material_context||[]).map(item=>'<section><h4>'+esc(item.topic)+'</h4><p>'+esc(item.statement)+'</p><small>'+esc((item.source_ids||[]).join(', '))+'</small></section>').join('');
  return '<details class="setting-details"><summary>Everyday life, institutions and material evidence</summary>'+(research.society||[]).map(text=>'<p>'+esc(text)+'</p>').join('')+(research.religious_context?'<p>'+esc(research.religious_context)+'</p>':'')+records+'<p class="note">These references describe historical context and research limits. Documentary rates do not create wages, stock, employment or personal knowledge.</p></details>';
}
function historicalSnapshotMarkup(snapshot) {
  const opening=snapshot.opening||{},briefing=textItems(snapshot.briefing),domains=snapshot.domains||{},sources=snapshot.sources||[];
  return `<div class="historical-opening"><span class="eyebrow">YOUR STARTING MOMENT</span><h3>${esc(opening.label||opening.date||'Opening date not specified')}</h3><p class="opening-date">${esc(label(opening.calendar||'calendar unspecified'))} calendar · ${opening.time?esc(opening.time):'hour unknown'}${opening.precision?' · '+esc(opening.precision)+' precision':''}</p><div class="historical-briefing">${briefing.map(value=>`<p>${esc(value)}</p>`).join('')}</div><details class="setting-details"><summary>Explore the historical setting</summary>${entryGuideMarkup(snapshot.entry_guide)}<div class="historical-domains">${['political','military','territorial','diplomatic'].map(key=>`<section><h3>${label(key)}</h3>${(domains[key]||[]).map(item=>`<p>${esc(typeof item==='string'?item:item.statement)}${item.source_ids?.length?` <small>[${esc(item.source_ids.join(', '))}]</small>`:''}</p>`).join('')||'<p class="note">No opening record supplied.</p>'}</section>`).join('')}</div>${historicalResearchMarkup(snapshot.research_extension)}${snapshot.actors?.length?`<details><summary>People in this historical world</summary>${snapshot.actors.map(actor=>`<div class="list-row"><strong>${esc(actor.name)}</strong><small>${esc(actor.role||'')}</small></div>`).join('')}</details>`:''}<h3>What remains unknown</h3>${textItems(snapshot.unknowns).map(value=>`<p class="note">${esc(value)}</p>`).join('')||'<p class="note">No additional unknowns are listed.</p>'}</details><details class="setting-details"><summary>Sources and starting assumptions</summary>${opening.boundary?`<p>${esc(opening.boundary)}</p>`:''}<p>Historical setting references describe the starting world. They do not automatically become your character's knowledge or determine future events.</p>${textItems(snapshot.simulation_rules).map(value=>`<p>${esc(value)}</p>`).join('')}${sources.map(source=>{const url=safeHttpUrl(source.url),title=source.title||source.id||'Source';return `<p>${source.id?`<small>${esc(source.id)} · </small>`:''}${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`:esc(title)}</p>`;}).join('')||'<p>No source links supplied.</p>'}</details></div>`;
}

function historicalReferenceMarkup(start) {
  const snapshot=start?.snapshot;
  if(!snapshot)return '';
  return `<details class="panel historical-reference"><summary>Opening reference · ${esc(snapshot.opening?.label || start.date || 'Historical start')}</summary><p class="reference-note">Preserved opening context. Later campaign events determine the current world state.</p>${historicalSnapshotMarkup(snapshot)}<p class="note">Historical archive policy: ${esc(start.history_origin?.status==='unbound'?'unconfigured':start.history_origin?.status || 'unconfigured')}. Opening provenance is retained for later calendar and history integration.</p></details>`;
}

const operations = {
 register_actor:['Register a character',{actor_id:'text',name:'text',species:'text',player_controlled:['false','true'],instruction_ref:'text'}],
 set_scene:['Set the scene',{day:'number',time:'text',precision:['approximate','exact','unknown'],description:'textarea',instruction_ref:'text'}],
 record_evidence:['Record evidence',{evidence_id:'text',subject:'actor',assertion:'textarea',status:['established','testimony','inference','provisional','unknown','superseded']}],
 receive_evidence:['Receive evidence',{evidence_id:'text',recipient:'actor'}],
 confirm_character_field:['Confirm character state',{subject:'actor',evidence_id:'text',field:['location','condition','custody','service','current_activity'],value:'text',authority_ref:'text',instruction_ref:'text'}],
 establish_stock:['Establish inventory',{location:'text',material:'text',quantity:'number',inventory_evidence_ref:'text'}],
 transfer_stock:['Transfer inventory',{from:'text',to:'text',material:'text',quantity:'number',authority_ref:'text'}],
 record_obligation:['Record an obligation',{obligation_id:'text',subject:'actor',description:'textarea',status:['offered','agreed','due','disputed','fulfilled','unknown'],instruction_ref:'text'}],
 record_design:['Record a design',{design_id:'text',name:'text'}],
 receive_order:['Receive an order',{order_id:'text',recipient:'actor',content:'textarea',authority_ref:'text'}],
 record_capacity:['Record site capacity',{capacity_id:'text',site:'text',quantity:'number',unit:['concurrent_people']}],
 commit_activity:['Commit a sourced activity',{activity_id:'text',actors:'actors',site:'text',capacity_id:'text',start:'number',end:'number',role:'text',authority_ref:'text',instruction_ref:'text'}],
 record_delegation:['Record delegated authority',{delegation_id:'text',principal:'actor',delegate:'actor',actors:'actors',site:'text',start:'number',end:'number',role:'text',authority_ref:'text',instruction_ref:'text'}]
};
function mountTools() {
  $('#host-tools').innerHTML = `<h2>Record a world event</h2><p class="note">Every event runs through dependency observation. Single invalid events are rejected. Simultaneous requests retain unresolved intent when they conflict or fail their current preconditions.</p><label>Operation<select id="operation">${Object.entries(operations).map(([id,[name]])=>`<option value="${id}">${name}</option>`).join('')}</select></label><form id="event-form"><div id="fields"></div><label>Source reference<input name="source_ref" required placeholder="Source establishing this event"></label><div class="buttons"><button class="primary">Submit event</button></div></form><details><summary>Submit simultaneous requests as JSON</summary><p class="note">Enter 1–16 objects with op and params. All requests use the same next causal sequence and this campaign’s scope. Shared resources can defer conflicting requests.</p><form id="batch-form"><label>Requests<textarea name="events" required maxlength="80000" aria-label="Simultaneous requests JSON" placeholder='[{"op":"record_design","params":{"design_id":"draft","name":"Draft","source_ref":"session reference"}}]'></textarea></label><div class="buttons"><button class="primary">Submit simultaneous requests</button></div></form></details>`;
  function fields() { $('#fields').innerHTML = Object.entries(operations[$('#operation').value][1]).map(([key,type])=>{
    let control;
    if (type === 'actor' && Object.keys(actors()).length) control = `<select name="${key}">${Object.entries(actors()).map(([id,a])=>`<option value="${esc(id)}">${esc(a.name || id)} · ${esc(id)}</option>`).join('')}</select>`;
    else if (Array.isArray(type)) control = `<select name="${key}">${type.map(v=>`<option value="${v}">${label(v)}</option>`).join('')}</select>`;
    else if (type === 'textarea') control = `<textarea name="${key}" required maxlength="10000"></textarea>`;
    else control = `<input name="${key}" type="${type==='actor'||type==='actors'?'text':type}" required ${type === 'number' ? 'min="0" step="1"' : 'maxlength="2000"'} ${type==='actors'?'placeholder="Actor IDs, comma separated"':''} ${key==='day' ? `value="${current.state.campaign_time?.day || 1}"` : ''}>`;
    return `<label>${label(key)}${control}</label>`;
  }).join(''); }
  fields(); $('#operation').onchange = fields;
  $('#event-form').onsubmit=e=>{e.preventDefault();const op=$('#operation').value,params=Object.fromEntries(new FormData(e.target));for(const [k,t] of Object.entries(operations[op][1])) {if(t==='number')params[k]=Number(params[k]);if(t==='actors')params[k]=params[k].split(',').map(id=>id.trim()).filter(Boolean);}if(op==='register_actor')params.player_controlled=params.player_controlled==='true';submit(op,params);};
  $('#batch-form').onsubmit=e=>{e.preventDefault();try{submitBatch(JSON.parse(new FormData(e.target).get('events')));}catch(err){notice('Invalid requests JSON: '+err.message,true);}};
}

function renderCreatorJournal() {
  const events=[...(current.state.journal || [])].reverse(), pending=Object.entries(current.state.r9?.requests || {}).filter(([,r])=>r.status==='unresolved'), mandates=Object.entries(current.state.r9?.mandates || {});
  $('#content').innerHTML=`<article class="panel"><div class="eyebrow">DURABLE REQUESTS</div><h2>${pending.length} unresolved request${pending.length===1?'':'s'}</h2>${pending.map(([id,r])=>`<details open><summary>${esc(label(r.original.op))} · ${esc(id)}</summary><p>${esc(r.reason || 'Dependency conflict')}</p><pre>${esc(JSON.stringify(r.original,null,2))}</pre></details>`).join('') || '<p>No unresolved requests.</p>'}<h2 class="spacer">Decision authority</h2><p class="note">Record an actual scoped mandate before deciding. Approval rechecks current state and executes later; denial preserves the request without applying it.</p><form id="mandate-form"><label>Mandate ID<input name="mandate_id" required maxlength="200"></label><label>Authorized actor<input name="actor" required maxlength="200"></label><label>Operation rights, comma separated<input name="operations" required placeholder="transfer_stock"></label><label>Authority source reference<input name="source_ref" required maxlength="2000"></label><div class="buttons"><button class="primary">Record mandate</button></div></form>${pending.length?`<h2 class="spacer">Resolve a request</h2><form id="resolve-form"><label>Request<select name="request_id">${pending.map(([id,r])=>`<option value="${esc(id)}">${esc(r.original.op)} · ${esc(id)}</option>`).join('')}</select></label><label>Mandate<select name="mandate_id">${mandates.map(([id,m])=>`<option value="${esc(id)}">${esc(id)} · ${esc(m.actor)}</option>`).join('')}</select></label><label>Authorized actor<input name="actor" required maxlength="200"></label><label>Decision<select name="approve"><option value="true">Approve and execute if valid</option><option value="false">Deny</option></select></label><div class="buttons"><button class="primary" ${mandates.length?'':'disabled'}>Record decision</button></div></form>`:''}<h2 class="spacer">Decision history</h2>${facts(current.state.r9?.decisions)}<h2 class="spacer">${events.length} recorded event${events.length===1?'':'s'}</h2>${events.map(e=>`<details><summary>Sequence ${esc(e.at)} · ${esc(label(e.op.replace(/^ast_/,'')))}</summary><p class="note">${esc(e.id)}</p><pre>${esc(JSON.stringify(e.params,null,2))}</pre></details>`).join('')||'<p>Your first committed event will appear here.</p>'}</article>`;
  $('#mandate-form').onsubmit=e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));data.operations=data.operations.split(',').map(op=>op.trim()).filter(Boolean);mutate('mandate',data);};
  if ($('#resolve-form')) $('#resolve-form').onsubmit=e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));data.decision_id=crypto.randomUUID();data.approve=data.approve==='true';mutate('resolve',data);};
}

function catalogCards(items,kind) {
  return rows(items).map(item=>{
    const details=Object.fromEntries(['id','version','genre_id','library_ids','runtime_operations','specialty_runtime_operations','lookup_operations','profile_requirements','source_files','receiving_binding','lookup_creates_state','automatic_numeric_adoption','numeric_profile_adoption'].filter(key=>key in item).map(key=>[key,item[key]]));
    return `<article class="panel"><span class="badge">${esc(item.type==='campaign_library'?'CAMPAIGN CONTENT LIBRARY':kind)}</span><h2>${esc(item.name || item.title || item.id)}</h2><p>${esc(item.description || item.summary || item.source_status || item.scope || item.certification || '')}</p>${item.status?`<small>${esc(label(item.status.toLowerCase()))}</small>`:''}${(item.limitations || []).map(text=>`<p class="note">${esc(text)}</p>`).join('')}<details><summary>Operations and source references</summary>${facts(details)}</details></article>`;
  }).join('');
}
function renderLibrary() {
  if(workspaceMode!=='creator'){$('#content').innerHTML='<div class="empty">Source-library inspection belongs to the explicit Creator workspace or campaign setup. Reference content does not become character knowledge.</div>';return;}
  const core=library.core || {};
  $('#content').innerHTML=`<article class="panel scene"><div class="eyebrow">INTERACTIVE ROLEPLAYING GAMES SYSTEMS</div><h2>Core ${esc(core.version || '3.3')} is the foundation.</h2><p>Core calls the selected domain routines when needed. Content libraries supply references and campaign material. Each campaign keeps its facts in one world state.</p></article><article class="panel spacer"><h2>Search source content</h2><p class="note">Inspect packaged references and their original status. Looking up a record creates no campaign effects or authority.</p><form id="content-search"><label>Content library<select name="library">${rows(library.content_libraries).map(item=>`<option value="${esc(item.id)}">${esc(item.name || item.id)}</option>`).join('')}</select></label><label>Search text<input name="q" maxlength="2000" placeholder="Name, template, rule or source phrase"></label><div class="buttons"><button class="primary">Search content</button></div></form><div id="content-results"></div></article><h2 class="spacer">Core</h2><div class="cards">${catalogCards([core],'CORE')}</div><h2 class="spacer">Core domain routines</h2><div class="cards">${catalogCards(library.genre_engines,'CORE ROUTINE')}</div><h2 class="spacer">Content libraries</h2><div class="cards">${catalogCards(library.content_libraries,'CONTENT LIBRARY')}</div><h2 class="spacer">Campaign profiles</h2><div class="cards">${catalogCards(library.campaign_profiles,'CAMPAIGN PROFILE')}</div>`;
  $('#content-search').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const query=new URLSearchParams(new FormData(e.target));query.set('limit','30');const result=await api('content?'+query.toString());$('#content-results').innerHTML=`<p class="note">Source status: ${esc(result.source_status)} · ${result.results.length} result${result.results.length===1?'':'s'}</p>${result.results.map(row=>`<details><summary>${esc(Object.values(row.identity || {}).join(' · ') || row.source_file)}${row.line?' · line '+esc(row.line):''}</summary><p class="note">${esc(row.source_file)}</p>${row.source_status_fields?facts(row.source_status_fields):''}<pre>${esc(row.excerpt)}</pre></details>`).join('') || '<p>No matching source records.</p>'}`;}catch(err){notice(err.message,true);}finally{button.disabled=false;}};
}

const LIFECYCLE_LABEL={planned:'Planned',scaffold:'Scaffold',in_development:'In development',functional:'Available',deferred:'Deferred'};
const VIEW_ALIASES={'content-library':'content-library','my-campaigns':'saves',home:'home','character-creation':'content-library',play:'story','hyw-detail':'content-library','starting-periods':'content-library','starting-scenarios':'content-library',character:'story',inventory:'story',story:'story',world:'world',chronicle:'chronicle',creator:'creator','creator-workspace':'creator','creator-tools':'creator',library:'library','engines-libraries':'library','campaign-trash':'trash',trash:'trash'};
function featureView(feature){return feature.view||VIEW_ALIASES[feature.id]||'feature:'+feature.id;}
function routePath(route){return String(route||'').replace(/^#\/?/,'').replace(/^\/|\/$/g,'');}
function currentHash(){return typeof location==='undefined'?'':routePath(location.hash);}
function featureForRoute(path){return features.find(feature=>routePath(feature.route)===path||feature.id===path);}
function featureAllowed(feature){return workspaceMode==='creator'||Array.isArray(feature.availableTo)&&feature.availableTo.includes('player');}
const expandedFeatureBranches=new Set();
function expandFeatureAncestors(id){
  const seen=new Set();let feature=features.find(item=>item.id===id);
  if(feature&&features.some(item=>item.parentId===feature.id))expandedFeatureBranches.add(feature.id);
  while(feature?.parentId&&!seen.has(feature.id)){seen.add(feature.id);expandedFeatureBranches.add(feature.parentId);feature=features.find(item=>item.id===feature.parentId);}
}
function featureNavMarkup(){
  const byParent=parent=>features.filter(feature=>(feature.parentId||null)===parent).sort((a,b)=>(a.order||0)-(b.order||0));
  const item=(feature,depth=0,seen=new Set())=>{if(seen.has(feature.id)||depth>8)return '';const next=new Set(seen).add(feature.id),children=byParent(feature.id),open=expandedFeatureBranches.has(feature.id),container='feature-children-'+feature.id;return '<div class="feature-node" style="--nav-depth:'+depth+'"><div class="feature-row"><button title="'+esc(feature.label)+'" class="feature-link '+(depth?'feature-child':'')+'" data-feature="'+esc(feature.id)+'" aria-current="'+(feature.id===routeFeatureId?'page':'false')+'"><span>'+esc(feature.label)+'</span>'+(feature.lifecycle==='functional'?'':'<small class="badge">'+esc(LIFECYCLE_LABEL[feature.lifecycle]||feature.lifecycle)+'</small>')+'</button>'+(children.length?'<button type="button" class="feature-toggle quiet" data-feature-toggle="'+esc(feature.id)+'" aria-controls="'+esc(container)+'" aria-expanded="'+open+'" aria-label="'+(open?'Hide':'Show')+' sections for '+esc(feature.label)+'">'+(open?'▾':'▸')+'</button>':'')+'</div>'+(children.length?'<div id="'+esc(container)+'" class="feature-children" '+(open?'':'hidden')+'>'+children.map(child=>item(child,depth+1,next)).join('')+'</div>':'')+'</div>';};
  return byParent(null).map(feature=>item(feature)).join('');
}
function drawFeatureNav(){
  const nav=$('#feature-nav');if(!nav)return;nav.innerHTML=featureNavMarkup()||'<p class="note">No sections are available in this workspace.</p>';
  document.querySelectorAll('#feature-nav [data-feature]').forEach(button=>button.onclick=()=>navigateFeature(button.dataset.feature));
  document.querySelectorAll('#feature-nav [data-feature-toggle]').forEach(button=>button.onclick=()=>{const id=button.dataset.featureToggle;expandedFeatureBranches.has(id)?expandedFeatureBranches.delete(id):expandedFeatureBranches.add(id);drawFeatureNav();[...document.querySelectorAll('#feature-nav [data-feature-toggle]')].find(toggle=>toggle.dataset.featureToggle===id)?.focus();});
}
async function loadFeatureNav(options={}){
  const request=++featuresRequest,mode=workspaceMode;features=[];drawFeatureNav();
  try{
    const data=await api('features',undefined,{creator:mode==='creator'});
    if(request!==featuresRequest||mode!==workspaceMode)return false;
    features=(data.features||[]).filter(feature=>featureAllowed(feature));let previous;do{previous=features.length;const ids=new Set(features.map(feature=>feature.id));features=features.filter(feature=>!feature.parentId||ids.has(feature.parentId));}while(features.length!==previous);drawFeatureNav();
    if(options.applyRoute!==false)applyCurrentRoute();return true;
  }catch(error){
    if(request!==featuresRequest||mode!==workspaceMode)return false;
    $('#feature-nav').innerHTML='<p class="note">Navigation could not load: '+esc(error.message)+'</p><button class="quiet" id="retry-navigation">Retry navigation</button>';
    $('#retry-navigation').onclick=()=>loadFeatureNav();return false;
  }
}
function updateViewRoute(next,featureId){
  const hit=featureId?features.find(feature=>feature.id===featureId):features.find(feature=>feature.id===next)||features.find(feature=>featureView(feature)===next);
  routeFeatureId=hit?.id||null;expandFeatureAncestors(routeFeatureId);drawFeatureNav();
  if(typeof location!=='undefined'&&hit){const hash=hit.route||'#/'+hit.id;if(location.hash!==hash)location.hash=hash;}
}
function navigateFeature(id){
  const feature=features.find(item=>item.id===id);if(!feature||!featureAllowed(feature))return;
  changeView(featureView(feature),{featureId:id});
  if(feature.id==='my-campaigns')$('#campaign').focus();if(['character','inventory'].includes(feature.id))openInspector(feature.id);
}
function applyCurrentRoute(){
  const path=currentHash();if(!path){if(routeFeatureId!==null){routeFeatureId=null;changeView(current?'story':'home',{route:false});drawFeatureNav();}return;}
  const feature=featureForRoute(path);
  if(!feature){routeFeatureId=null;changeView('feature:unavailable',{route:false});return;}
  const next=featureView(feature);if(routeFeatureId===feature.id&&view===next)return;
  routeFeatureId=feature.id;expandFeatureAncestors(feature.id);changeView(next,{route:false});drawFeatureNav();if(['character','inventory'].includes(feature.id)&&current)openInspector(feature.id);
}
let historicalReferenceRequest=0;
let historicalReferenceQuery={collection:'chronology',q:'',offset:0};
function historicalReferenceActive(){return workspaceMode==='creator'&&view==='feature:historical-reference-library';}
function historicalReferenceUnavailable(info){
  const states={not_attached:['No archive attached','No historical archive is attached on this installation.'],incomplete:['Archive incomplete','The Catalog archive is incomplete. Historical records are unavailable until every required part is present.'],corrupt:['Archive verification failed','The archive failed verification. Historical records are unavailable until the source is repaired.'],unavailable:['Archive unavailable','The selected archive cannot be read on this installation.']};
  const [title,message]=states[info.status]||states.unavailable;
  $('#content').innerHTML='<section class="panel"><span class="eyebrow">CREATOR REFERENCE · READ ONLY</span><h2>Historical Details</h2><h3>'+esc(title)+'</h3><p>'+esc(info.notice||message)+'</p><p class="note">Archive metadata alone is not the historical archive. A complete Catalog archive or an explicitly attached local ZIP is required. Browsing creates no campaign facts or character knowledge.</p><button class="quiet" id="reference-retry">Check again</button></section>';
  $('#reference-retry').onclick=renderHistoricalReference;
}
async function renderHistoricalReference(){
  if(!historicalReferenceActive())return;
  const request=++historicalReferenceRequest;
  $('#content').innerHTML='<section class="panel"><p>Opening Historical Details…</p></section>';
  try{
    const info=await api('historical-reference',undefined,{creator:true});
    if(request!==historicalReferenceRequest||!historicalReferenceActive())return;
    if(info.status!=='attached_read_only'){historicalReferenceUnavailable(info);return;}
    const collections=info.collections||[];
    if(!collections.some(item=>item.id===historicalReferenceQuery.collection))historicalReferenceQuery.collection=collections[0]?.id||'';
    $('#content').innerHTML='<section class="panel"><span class="eyebrow">CREATOR REFERENCE · READ ONLY</span><h2>Historical Details</h2><h3>'+esc(info.title)+(info.edition?' · '+esc(info.edition):'')+'</h3><p class="reference-note">'+esc(info.notice)+'</p><p>'+esc(info.scope||'')+'</p><p class="note">'+esc(info.source_kind==='catalog_multipart'?'Complete Catalog archive verified for read-only browsing.':'Explicitly attached local ZIP · read-only reference.')+'</p>'+(collections.length?'<form id="historical-reference-search" class="reference-search"><label>Collection<select id="reference-collection">'+collections.map(item=>'<option value="'+esc(item.id)+'">'+esc(item.title)+'</option>').join('')+'</select></label><label>Find a person, place or subject<input id="reference-query" type="search" maxlength="200" placeholder="Henry, Agincourt, 1415…"></label><button class="primary" type="submit">Search archive</button></form>':'<p class="note">No searchable collections are supplied by this archive.</p>')+'<p class="note">Dates, estimates and disputed identities keep their source wording. Results do not establish availability in a campaign.</p><button class="quiet" id="reference-retry">Check archive again</button><div id="historical-reference-results" aria-live="polite"></div></section>';
    $('#reference-retry').onclick=renderHistoricalReference;
    if(!collections.length)return;
    $('#reference-collection').value=historicalReferenceQuery.collection;$('#reference-query').value=historicalReferenceQuery.q;
    $('#historical-reference-search').onsubmit=event=>{event.preventDefault();if($('#inspect-dialog').open)$('#inspect-dialog').close();historicalReferenceQuery={collection:$('#reference-collection').value,q:$('#reference-query').value,offset:0};return searchHistoricalReference();};
    await searchHistoricalReference();
  }catch(error){if(request!==historicalReferenceRequest||!historicalReferenceActive())return;historicalReferenceUnavailable({status:'unavailable',notice:error.message});}
}
async function searchHistoricalReference(){
  if(!historicalReferenceActive()||!$('#historical-reference-results'))return;
  const request=++historicalReferenceRequest,selection={...historicalReferenceQuery};
  $('#historical-reference-results').innerHTML='<p>Searching source records…</p>';
  try{
    const params=new URLSearchParams({...selection,limit:20});
    const result=await api('historical-reference/search?'+params.toString(),undefined,{creator:true});
    if(request!==historicalReferenceRequest||!historicalReferenceActive()||!$('#historical-reference-results'))return;
    const records=result.results||[];
    $('#historical-reference-results').innerHTML='<p class="note">'+esc(records.length?'Showing matches '+(selection.offset+1)+'–'+(selection.offset+records.length):'No source records match this search.')+'</p>'+records.map(row=>'<article class="record-card"><h3>'+esc(row.title)+'</h3><small>'+esc(row.source_id??row.record_type)+'</small>'+'<p class="note">'+esc(row.dates?.date_text||row.dates?.period_text||(row.dates?.year!==undefined?String(row.dates.year):''))+'</p><p>'+esc(row.excerpt||'')+'</p><details><summary>Source qualifications</summary>'+facts(row.source_status)+facts(row.dates)+'</details><button class="quiet" data-reference-row="'+esc(row.row)+'">Read source record & citations</button></article>').join('')+'<div class="buttons"><button id="reference-previous" class="quiet" '+(selection.offset?'':'disabled')+'>Previous</button><button id="reference-next" class="quiet" '+(result.has_more?'':'disabled')+'>Next</button></div>';
    document.querySelectorAll('[data-reference-row]').forEach(button=>button.onclick=()=>inspectHistoricalReference(selection.collection,Number(button.dataset.referenceRow)));
    $('#reference-previous').onclick=()=>{historicalReferenceQuery={...selection,offset:Math.max(0,selection.offset-20)};return searchHistoricalReference();};
    $('#reference-next').onclick=()=>{if(result.has_more){historicalReferenceQuery={...selection,offset:result.next_offset};return searchHistoricalReference();}};
  }catch(error){if(request!==historicalReferenceRequest||!historicalReferenceActive()||!$('#historical-reference-results'))return;$('#historical-reference-results').innerHTML='<p class="reference-note">'+esc(error.message)+'</p><button class="quiet" id="reference-search-retry">Retry search</button>';$('#reference-search-retry').onclick=searchHistoricalReference;}
}
function historicalCitationMarkup(source){
  const record=source.record||{};let payload={};try{payload=JSON.parse(record.payload_json||'{}');}catch{}
  const url=safeHttpUrl(record.url||payload.url),title=record.title||payload.title||source.id;
  return '<section><h4>'+(url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(title)+'</a>':esc(title))+'</h4><p>'+esc(payload.citation||'')+'</p>'+facts({source_id:source.id,status:source.status,rights_status:record.rights_status||payload.rights_status||'Not established',access_status:record.access_status||payload.access_status||'Not established'})+(source.rights||[]).map(right=>'<p class="note">'+esc(right.disposition)+' · '+esc(right.scope||'')+'</p>').join('')+'</section>';
}
async function inspectHistoricalReference(collection,row){
  if(!historicalReferenceActive())return;
  const request=++inspectorRequest;
  $('#inspect-title').textContent='Historical source · Creator reference';$('#inspect-content').innerHTML='<p>Reading the source record…</p>';if(!$('#inspect-dialog').open)$('#inspect-dialog').showModal();
  try{
    const result=await api('historical-reference/record?'+new URLSearchParams({collection,row}),undefined,{creator:true});
    if(request!==inspectorRequest||!historicalReferenceActive()||!$('#inspect-dialog').open)return;
    $('#inspect-content').innerHTML='<h3>'+esc(result.title)+'</h3><p class="reference-note">'+esc(result.notice)+'</p>'+'<p>'+esc(result.dates?.date_text||result.dates?.period_text||'')+'</p><p>'+esc(result.record?.payload?.statement||result.record?.statement||result.record?.significance_text||'')+'</p><h3>Citations and rights</h3>'+((result.sources||[]).map(historicalCitationMarkup).join('')||'<p class="note">No resolved citation is supplied for this record. Original references remain in the source payload.</p>')+'<details><summary>Source qualifications and date fields</summary>'+facts(result.source_status)+facts(result.dates)+'</details><details><summary>Original record and provenance</summary><pre class="reference-source-record">'+esc(JSON.stringify(result.record,null,2))+'</pre>'+facts(result.reference)+'</details>';
  }catch(error){if(request!==inspectorRequest||!historicalReferenceActive()||!$('#inspect-dialog').open)return;$('#inspect-content').innerHTML='<p>'+esc(error.message)+'</p><button class="quiet" id="reference-record-retry">Retry source record</button>';$('#reference-record-retry').onclick=()=>inspectHistoricalReference(collection,row);}
}
function renderFeature(id){
  const feature=features.find(item=>item.id===id&&featureAllowed(item));
  if(feature&&workspaceMode==='creator'&&creatorDraftSections.includes(id)){renderCreatorDraftPreview();return;}
  if(feature&&workspaceMode==='creator'&&id==='providers-models'){renderAssistanceStatus();return;}
  if(feature&&workspaceMode==='creator'&&id==='usage-budgets'){renderAIUsage();return;}
  if(feature&&workspaceMode==='creator'&&id==='historical-reference-library'){renderHistoricalReference();return;}
  if(feature&&workspaceMode==='creator'&&['historical-comparison','historical-inspector'].includes(id)){renderHistoricalPlans(id);return;}
  if(!feature){$('#content').innerHTML='<div class="empty"><h2>Section unavailable</h2><p>This route is not available in the current workspace.</p></div>';return;}
  const children=features.filter(item=>item.parentId===id),dependencies=(feature.dependencyIds||[]).map(dep=>features.find(item=>item.id===dep)?.label).filter(Boolean),status=LIFECYCLE_LABEL[feature.lifecycle]||feature.lifecycle;
  $('#content').innerHTML='<article class="panel planned-feature"><span class="eyebrow">'+esc(status)+'</span><h2>'+esc(feature.label)+'</h2><p>'+esc(feature.description)+'</p><p class="reference-note">'+(feature.lifecycle==='functional'?'This registered section has no dedicated controls in this build. Inspecting it changes no saved campaign.':'This is a reserved section, not an operational feature. It creates no records, balances, transactions or campaign effects.')+'</p>'+(dependencies.length?'<p class="note">Depends on: '+esc(dependencies.join(', '))+'</p>':'')+children.map(child=>'<button class="section-link quiet" data-feature-child="'+esc(child.id)+'"><strong>'+esc(child.label)+'</strong><small>'+esc(LIFECYCLE_LABEL[child.lifecycle]||child.lifecycle)+' · '+esc(child.description)+'</small></button>').join('')+'</article>';
  document.querySelectorAll('[data-feature-child]').forEach(button=>button.onclick=()=>navigateFeature(button.dataset.featureChild));
}
function scenarioReferencesMarkup(entry){const references=entry.starting_scenario_references||entry.scenario_references||entry.scenarios||[];return references.map(scenario=>'<section class="scenario-reference"><strong>'+esc(scenario.title||scenario.id)+'</strong><span class="badge">'+esc(scenario.ready===true&&scenario.playable===true?'Available for review':label(scenario.status||'Reference only'))+'</span><p class="note">'+esc(scenario.reason||scenario.readiness||(scenario.ready===true&&scenario.playable===true?'Review this scenario through the entry’s Start new playthrough button.':'This scenario is a reference and cannot start a new playthrough.'))+'</p></section>').join('');}
function libraryEntries(data){return (data.campaigns||[]).flatMap(campaign=>(campaign.periods||[]).flatMap(period=>(period.entries||[]).map(entry=>({...entry,campaign_id:campaign.id}))));}
function verifiedLibraryEntry(entry){return entry.playable===true&&/^[a-f0-9]{64}$/i.test(entry.snapshot_sha256||'');}
function historicalEntryOptions(entries,periods=[],featured=[]){
  const option=entry=>'<option value="'+esc(entry.id)+'">'+esc(entry.year)+' · '+esc(entry.title)+(featured.includes(entry.year)?' · primary start':'')+'</option>';
  const grouped=periods.length?periods.map(period=>'<optgroup label="'+esc(period.name)+'">'+entries.filter(entry=>entry.period_id===period.id||(period.entries||[]).some(item=>item.id===entry.id)).map(option).join('')+'</optgroup>').join(''):entries.map(option).join('');
  return '<option value="">Choose an entry point…</option>'+grouped;
}
function campaignWorldCard(campaign){
  return '<article class="panel library-campaign"><div class="library-campaign-heading"><span class="eyebrow">FANTASY CAMPAIGN WORLD · '+esc(campaign.period)+'</span><h2>'+esc(campaign.title)+'</h2><p>'+esc(campaign.summary)+'</p><p class="note">'+esc(campaign.readiness)+'</p></div><button type="button" class="quiet" data-inspect-world="'+esc(campaign.reference_id)+'">Read world guide</button></article>';
}
function mapReferenceMarkup(map){
  const entries=map.entries||[];
  return '<details><summary>'+esc(map.title)+' · '+esc(entries.length?entries.length+' map-key entries':'Terrain reference')+'</summary>'+(entries.length?'<p class="note">Transcribed from the original reference map.</p><ol>'+entries.map(entry=>'<li value="'+esc(entry.printed_number)+'">'+esc(entry.label)+(entry.transcription_note?'<small> · '+esc(entry.transcription_note)+'</small>':'')+'</li>').join('')+'</ol>':'')+(map.notes||[]).map(note=>'<p class="note">'+esc(note)+'</p>').join('')+'</details>';
}
function worldGuideSectionsMarkup(world,query=''){
  const terms=query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean),sections=world.guide?.sections||[],fold=sections.length>10;
  return sections.filter(section=>terms.every(term=>[section.title,...section.paragraphs].join(' ').toLocaleLowerCase().includes(term))).map((section,index)=>{
    const paragraphs=(section.paragraphs||[]).map(text=>'<p>'+esc(text)+'</p>').join('');
    return fold?'<details class="world-guide-chapter" '+(terms.length||index<2?'open':'')+'><summary>'+esc(section.title)+'</summary>'+paragraphs+'</details>':'<section><h3>'+esc(section.title)+'</h3>'+paragraphs+'</section>';
  }).join('')||'<p class="note">No guide sections match that search.</p>';
}
function campaignWorldMarkup(world){
  const guide=world.guide||{},longGuide=(guide.sections||[]).length>10;
  return '<span class="eyebrow">CAMPAIGN WORLD · '+esc(world.reference_period)+' · v'+esc(world.version||'')+'</span><h3>'+esc(world.title)+'</h3><p>'+esc(guide.subtitle||'')+'</p>'+(longGuide?'<label>Search the adopted world guide<input type="search" id="world-guide-search" placeholder="A culture, place, religion or character"></label><p class="note">'+esc(guide.sections.length)+' guide sections. Open a chapter to read more; searching expands matching chapters.</p>':'')+'<div id="world-guide-sections">'+worldGuideSectionsMarkup(world)+'</div>'+(guide.map_catalogues||[]).map(mapReferenceMarkup).join('')+'<p class="reference-note">'+esc(guide.scope_note||'Out-of-character world reference.')+'</p>';
}
async function inspectCampaignWorld(id){
  const request=++inspectorRequest,mode=workspaceMode;$('#inspect-title').textContent='Campaign world · out of character';$('#inspect-content').innerHTML='<p>Loading the world guide…</p>';if(!$('#inspect-dialog').open)$('#inspect-dialog').showModal();
  try{const result=await api('campaign-world/'+encodeURIComponent(id),undefined,{creator:false});if(request!==inspectorRequest||mode!==workspaceMode||!$('#inspect-dialog').open)return;$('#inspect-content').innerHTML=campaignWorldMarkup(result);const search=$('#world-guide-search');if(search)search.oninput=()=>{if(request===inspectorRequest&&$('#inspect-dialog').open)$('#world-guide-sections').innerHTML=worldGuideSectionsMarkup(result,search.value);};}catch(error){if(request===inspectorRequest&&mode===workspaceMode&&$('#inspect-dialog').open)$('#inspect-content').innerHTML='<p>'+esc(error.message)+'</p>';}
}
async function renderContentLibrary(){
  const request=++contentLibraryRequest,mode=workspaceMode;$('#content').innerHTML='<div class="empty">Loading the Content Library…</div>';
  try{
    const data=await api('content-library',undefined,{creator:false});if(request!==contentLibraryRequest||view!=='content-library'||mode!==workspaceMode)return;
    approvedEntries=new Map(libraryEntries(data).filter(verifiedLibraryEntry).map(entry=>[entry.id,entry]));
    const currentMarkup='<section class="library-hero"><span class="eyebrow">THE CONTENT LIBRARY</span><h2>Explore a world.<br>Find a story.</h2><p>Browse campaign worlds and their starting references.</p><span class="hero-rule" aria-hidden="true"></span></section>'+(data.campaigns||[]).map(campaign=>campaign.kind==='settlement_system'?riseCard(campaign):campaign.kind==='campaign_world'?campaignWorldCard(campaign):'<article class="panel library-campaign"><div class="library-campaign-heading"><span class="eyebrow">HISTORICAL CAMPAIGN · '+esc(campaign.period)+'</span><h2>'+esc(campaign.title)+'</h2><p>'+esc(campaign.summary)+'</p><p class="note">'+esc(campaign.playable_entry_count)+' starting references available. Each explains its evidence and remaining uncertainties.</p></div><label for="library-entry-'+esc(campaign.id)+'">Choose your entry point</label><select id="library-entry-'+esc(campaign.id)+'" data-library-entry-select="'+esc(campaign.id)+'">'+historicalEntryOptions((campaign.periods||[]).flatMap(period=>period.entries||[]),campaign.periods,campaign.featured_years||[])+'</select><div id="library-detail-'+esc(campaign.id)+'" class="selected-entry-detail" aria-live="polite"><p class="note">Select a year to see its description, starting situation and available scenarios.</p></div></article>').join('')+'<p class="note">'+esc(data.note||'Campaign references do not become character knowledge.')+'</p>';
    if(data.portfolio){
      $('#content').innerHTML=campaignCatalogueMarkup(data)+'<details id="catalogue-current-starts" class="panel catalogue-existing-starts"><summary>Current starting references & world guides</summary>'+currentMarkup+'</details>';
      bindCampaignCatalogue();
    }else $('#content').innerHTML=currentMarkup;
    document.querySelectorAll('[data-library-entry-select]').forEach(picker=>{
      picker.value='';let selectionRequest=0;
      const campaign=(data.campaigns||[]).find(item=>item.id===picker.dataset.libraryEntrySelect),entries=(campaign.periods||[]).flatMap(period=>period.entries||[]);
      picker.onchange=async()=>{
        const selected=++selectionRequest,id=picker.value,target=$('#library-detail-'+campaign.id),entry=entries.find(item=>item.id===id);
        if(!entry){target.innerHTML='<p class="note">Select a year to see its description, starting situation and available scenarios.</p>';return;}
        target.innerHTML='<p class="note">Loading the selected starting point…</p>';
        try{
          const preview=await api('historical-entry/'+encodeURIComponent(id),undefined,{creator:false});
          if(selected!==selectionRequest||request!==contentLibraryRequest||view!=='content-library'||mode!==workspaceMode||picker.value!==id)return;
          if(preview.entry?.id!==id)throw Error('The opening response identifies another entry. Select the starting point again.');
          if(preview.ready&&(!verifiedLibraryEntry(entry)||preview.snapshot_sha256!==entry.snapshot_sha256))throw Error('The opening reference changed. Refresh the Content Library before starting.');
          target.innerHTML='<article class="historical-preview"><span class="eyebrow">'+esc(entry.year)+' ENTRY POINT</span><h3>'+esc(entry.title)+'</h3><p>'+esc(entry.description||'')+'</p>'+(preview.snapshot?historicalSnapshotMarkup(preview.snapshot):'<p class="note">A supported opening is not available for this reference.</p>')+scenarioReferencesMarkup(entry)+(preview.ready&&verifiedLibraryEntry(entry)?'<button class="primary" data-start-entry="'+esc(id)+'">Start new playthrough</button>':'<p class="note">This entry is available for reference only.</p>')+'</article>';
          const start=target.querySelector('[data-start-entry]');if(start)start.onclick=()=>{const approved=approvedEntries.get(id);if(approved&&!busy)openCreateDialog(approved);};
        }catch(error){if(selected===selectionRequest&&request===contentLibraryRequest&&view==='content-library'&&mode===workspaceMode&&picker.value===id)target.innerHTML='<p class="note">'+esc(error.message)+'</p>';}
      };
    });
    bindLibraryControls();bindPreviewJourneys();
  }catch(error){if(request!==contentLibraryRequest||view!=='content-library'||mode!==workspaceMode)return;$('#content').innerHTML='<div class="empty"><p>'+esc(error.message)+'</p><button id="retry-content-library" class="quiet">Retry Content Library</button></div>';$('#retry-content-library').onclick=renderContentLibrary;}
}
function bindLibraryControls(){
  document.querySelectorAll('[data-rise-setup]').forEach(button=>button.onclick=()=>{if($('#inspect-dialog').open)$('#inspect-dialog').close();openRiseSetup();});
  document.querySelectorAll('[data-start-entry]').forEach(button=>button.onclick=()=>{const entry=approvedEntries.get(button.dataset.startEntry);if(entry){if($('#inspect-dialog').open)$('#inspect-dialog').close();openCreateDialog(entry);}});
  document.querySelectorAll('[data-inspect-entry]').forEach(button=>button.onclick=()=>inspectLibraryEntry(button.dataset.inspectEntry));
  document.querySelectorAll('[data-inspect-world]').forEach(button=>button.onclick=()=>inspectCampaignWorld(button.dataset.inspectWorld));
}
async function inspectLibraryEntry(id){
  const request=++inspectorRequest,mode=workspaceMode;$('#inspect-title').textContent='Starting reference · out of character';$('#inspect-content').innerHTML='<p>Loading the selected reference…</p>';if(!$('#inspect-dialog').open)$('#inspect-dialog').showModal();
  try{const result=await api('historical-entry/'+encodeURIComponent(id),undefined,{creator:false});if(request!==inspectorRequest||mode!==workspaceMode||!$('#inspect-dialog').open)return;$('#inspect-content').innerHTML='<h3>'+esc(result.entry?.title||id)+'</h3><p>'+esc(result.entry?.description||'')+'</p>'+(result.snapshot?historicalSnapshotMarkup(result.snapshot):'<p class="reference-note">Proposed reference. Opening date and detailed snapshot are not yet verified; this entry cannot create a playthrough.</p>');}catch(error){if(request===inspectorRequest&&$('#inspect-dialog').open)$('#inspect-content').innerHTML='<p>'+esc(error.message)+'</p>';}
}
function storySequence(entry){
  // These are causal/receipt positions. Never sort by elapsed time or civil dates.
  return [entry.sequence,entry.at,entry.received_at,entry.recorded_at].find(Number.isSafeInteger);
}
function chronologicalEntries(entries){
  return [...entries].sort((a,b)=>{
    const first=storySequence(a),second=storySequence(b);
    return first===undefined?(second===undefined?0:1):second===undefined?-1:first-second;
  });
}
function storyEntries(){
  const entries=rows(current?.story||current?.chronicle);
  return chronologicalEntries(entries.length?entries:(current?.settlement?.receipts||[]).map((entry,index)=>({...entry,id:'received:'+index,kind:'settlement_observation',title:'Received record'})));
}
function storyDisplayEntries(){
  let entries=storyEntries();
  const outcomes=(current?.completed_actions||[]).filter(result=>result.actor===current.actor_id&&['completed_successfully','completed_unsuccessfully'].includes(result.status)&&typeof result.outcome?.summary==='string');
  for(const result of outcomes){
    const text=routineOutcome(result,{elapsed:true,presentation:true}),request=result.request_id,event=result.receipt?.event_id;
    const related=entry=>Boolean(request&&(entry.id==='outcome:'+request||entry.id==='settlement-receipt:'+request||entry.id==='settlement-receipt:'+request+':inspection')||event&&(entry.source_refs?.includes(event)||entry.id==='settlement-receipt:'+event||entry.id==='settlement-receipt:'+event+':inspection'));
    // A received presentation can replace its exact transcript fragments only.
    // Keep any additional evidence/source-gap records, even at the same sequence.
    const covered=entries.filter(entry=>related(entry)&&entry.source_available!==false&&!entry.source_gap&&typeof entry.text==='string'&&entry.text.trim()&&text.includes(entry.text.trim()));
    entries=entries.filter(entry=>!covered.includes(entry));
    entries.push({id:'result:'+request,kind:result.kind||'action_completed',title:result.kind==='communication'?'Received communication · '+label(result.communication?.status||'received'):result.kind==='process_phase'?'Process phase · '+label(result.process?.status||'received'):result.status==='completed_unsuccessfully'?'YOUR ATTEMPT · UNSUCCESSFUL':'Your action',
      text,status:result.status,recorded_at:result.recorded_sequence??covered[0]?.recorded_at,
      source_refs:[...new Set([...covered.flatMap(entry=>entry.source_refs||[]),...(event?[event]:[])])],source_available:true,result,lastOutcome:result===outcomes.at(-1)});
  }
  return chronologicalEntries(entries);
}
function storyToolsMarkup(extra=''){
  return `<details class="story-tools"><summary>Find a moment & story details</summary><label class="sr-only" for="story-search">Search available scene records</label><input id="story-search" type="search" placeholder="Find a moment in your story…"><button id="jump-latest" class="quiet" type="button">Latest ↓</button>${extra}</details>`;
}
function bindStoryFeed(){
  const entries=storyDisplayEntries(),key='irgs-bookmarks:'+current.id,bookmarks=new Set(readLocal(key,[]));
  const draw=()=>{
    const query=$('#story-search').value.toLowerCase(),filtered=entries.filter(entry=>`${entry.text||''} ${entry.title||''}`.toLowerCase().includes(query));
    $('#story-feed').innerHTML=filtered.map(entryMarkup).join('')||'<p class="story-empty">No matching story entries are available.</p>';
    document.querySelectorAll('[data-bookmark]').forEach(button=>{
      const update=()=>{button.setAttribute('aria-pressed',String(bookmarks.has(button.dataset.bookmark)));button.textContent=bookmarks.has(button.dataset.bookmark)?'Bookmarked':'Bookmark';};
      update();button.onclick=()=>{bookmarks.has(button.dataset.bookmark)?bookmarks.delete(button.dataset.bookmark):bookmarks.add(button.dataset.bookmark);writeLocal(key,[...bookmarks]);update();};
    });
  };
  $('#story-search').oninput=draw;draw();$('#jump-latest').onclick=()=>$('#feed-end').scrollIntoView({behavior:'auto',block:'start'});
}
function responseChoices(){return workspaceMode==='player'&&current?.response_prompt?.source_status==='received_prompt'&&Array.isArray(current?.response_choices)?current.response_choices.filter(choice=>choice&&choice.kind==='declaration'&&typeof choice.id==='string'&&choice.id&&typeof choice.text==='string'&&choice.text.trim()):[];}
function responseChoicesMarkup(){
  if(workspaceMode!=='player'||current?.response_prompt?.source_status!=='received_prompt')return '';
  const prompt=current.response_prompt,choices=responseChoices();return `<section class="response-choices" aria-labelledby="response-choices-title"><span class="eyebrow">YOUR RESPONSE</span><h3 id="response-choices-title">${esc(prompt.title||'How do you respond?')}</h3>${prompt.description?`<p>${esc(prompt.description)}</p>`:''}<p class="note">Suggested approaches may fail, carry risks or prove unsuitable. Being listed does not guarantee success.</p><p class="note">Choose a suggested answer to edit below, or write your own response. Selecting an answer sends nothing. These are declarations of intent; choosing one establishes no outcome or elapsed time.</p><div class="response-choice-list">${choices.map((choice,index)=>`<button type="button" class="quiet" data-response-choice="${index}"><strong>${esc(choice.label||'Suggested response')}</strong><span>${esc(choice.text)}</span></button>`).join('')}</div><button type="button" id="write-own-response" class="quiet">Write your own response</button></section>`;
}
function focusOwnResponse(){if(workspaceMode!=='player'||!current?.actor_id)return;$('#own-response-panel').open=true;$('#declaration').focus();$('#declaration').scrollIntoView({behavior:'auto',block:'nearest'});}
function chooseResponse(choiceId,campaign,actor,expectedText){
  if(current?.id!==campaign||current?.actor_id!==actor||!actor)return;
  const choice=responseChoices().find(item=>item.id===choiceId&&item.text===expectedText);if(!choice)return;
  $('#declaration').value=choice.text;stashDraft();syncComposer();focusOwnResponse();notice(routineText('draft.suggested'));
}
function supportedActions(){return workspaceMode==='player'&&Array.isArray(current?.supported_actions)?current.supported_actions.filter(action=>action&&['issue_equipment','scene_action'].includes(action.kind)&&typeof action[action.kind==='scene_action'?'action_id':'order_id']==='string'&&action[action.kind==='scene_action'?'action_id':'order_id']&&typeof action.text==='string'&&action.text.trim()):[];}
function currentPlayReadiness(){
  if(current?.play_readiness)return current.play_readiness;
  const pending=Boolean(current?.pending_declaration),count=supportedActions().length+(current?.settlement?.actions||[]).length,starts=(current?.process_control?.start_options||[]).length,communications=(current?.communication_control?.channels||[]).reduce((sum,channel)=>sum+channel.participants.reduce((total,person)=>total+person.supported_commands.length,0),0);
  return {status:!current?.actor_id||current.character_available===false?'unavailable':pending?'pending_declaration':count||starts||communications?'supported_slice':'declaration_only',action_count:pending?0:count,process_start_count:pending?0:starts};
}
function assistanceContextCopy(){
  if(current?.assistance?.available===true)return 'Review a proposal in your response composer before accepting an action.';
  const status=currentPlayReadiness().status;
  return status==='supported_slice'?'AI assistance is not connected. Your listed actions use local rules and require no model.':status==='pending_declaration'?'Your intent is saved but unresolved. You can withdraw it to check the currently supported actions. No automatic resolution or provider request is running.':status==='unavailable'?'No available player character is selected. Inspect your received records or choose a saved story.':'No executable actions or process starts are currently available for this character. You can inspect received records and save unresolved intent. AI assistance is not connected.';
}
function playReadinessMarkup(){
  const status=currentPlayReadiness().status;if(status==='supported_slice')return '';
  const title=status==='pending_declaration'?'Intent awaiting resolution':status==='unavailable'?'Player character unavailable':'Declaration / reference checkpoint';
  return `<section class="panel play-readiness" aria-label="Current playability"><h3>${esc(title)}</h3><p>${esc(assistanceContextCopy())}</p>${status==='declaration_only'?'<p>A historical snapshot and an opening description do not supply a playable situation. To use the supported local slice, review the explicitly offered actor-bound contexts or a new human’s fictional opening in the Library. Your current story stays saved.</p><button type="button" class="quiet" id="browse-supported-start">Review other starting choices</button>':''}</section>`;
}
function actionCapabilityNote(){
  if(current?.pending_declaration)return 'Your exact intent is saved and unresolved. Withdraw it to check the currently supported actions; withdrawal executes nothing and advances no time.';
  if(current?.capabilities?.playable_opening)return 'Supported attempts here: '+supportedActions().map(item=>item.title).join('; ')+'. Each uses its selected local rule. Freeform declarations remain saved intent; general combat, narration and civil-calendar advancement are unavailable.';
  if(current?.capabilities?.supported_action_resolution)return 'Received equipment orders can be attempted using the listed action; authority and stock are checked on submission. Freeform declarations remain saved intent; general action resolution, narration and time advancement are not connected.';
  return !current?.capabilities?.action_resolution?'Freeform declarations cannot be resolved yet. You can save your exact intent, inspect available records or withdraw a pending declaration.':'The host preserves declarations and received records. A general narrator is not connected.';
}
function supportedActionsMarkup(){
  const actions=supportedActions();if(!actions.length)return '';
  const opening=actions.some(action=>action.kind==='scene_action');
  return `<section class="supported-actions" aria-labelledby="supported-actions-title"><div class="decision-heading"><span class="eyebrow">THE NEXT MOVE IS YOURS</span><h3 id="supported-actions-title">${opening?'What will you do?':'Your received orders'}</h3></div><p class="choice-guidance">${opening?'Listed approaches can fail. Read the attempt, then review your next move. Selecting an action sends nothing.':'Review an order before confirming it. Authority and available stock are checked on submission.'}</p><div class="adventure-choices">${actions.map((action,index)=>`<article class="supported-action"><button type="button" class="adventure-choice" data-supported-action="${index}" aria-label="${esc(action.title||'Attempt action')}"><span class="choice-number" aria-hidden="true">${String(index+1).padStart(2,'0')}</span><span class="choice-copy"><strong>${esc(action.title||'Attempt action')}</strong>${action.description?`<span>${esc(action.description)}</span>`:''}<small class="record">${esc(action.text)}</small></span><span class="choice-arrow" aria-hidden="true">→</span></button></article>`).join('')}</div></section>`;
}

function openingElapsedMarkup(){
  const elapsed=current?.elapsed_time,selected=elapsed?.axis==='authored-opening-seconds'||(current?.capabilities?.elapsed_scope==='selected_start_context'&&current?.start_context?.schema_version==='irgs-start-readiness-1');if(!current?.capabilities?.playable_opening||!selected||!Number.isSafeInteger(elapsed?.seconds)||elapsed.seconds<0)return '';
  return `<p class="opening-elapsed"><span aria-hidden="true">◷</span> ${esc(elapsed.seconds)} seconds elapsed in this selected local context</p>`;
}
function openingMarkup(){const opening=current?.opening;if(!opening||!Array.isArray(opening.blocks))return '';const fresh=opening.status==='awaiting_first_action';return `<details class="opening-presentation" ${fresh?'open':''}><summary>${fresh?'Before your first move':'Where your story began'}</summary>${opening.blocks.filter(block=>!['character','scene','first_decision'].includes(block.kind)).map(block=>`${block.status?`<span class="badge">${esc(label(block.status))}</span>`:''}<p>${esc(block.text||'')}</p>`).join('')}${fresh?'':'<p class="note">Your original opening. The Chronicle records what has happened since.</p>'}</details>`;}
function renderHome(){renderPreviewHome();}

let historyPlanningRequest=0;
function referenceDate(date){if(!date)return 'Date not established';if(typeof date==='string')return date;return [date.start||date.date||'Date unknown',date.end&&date.end!==date.start?'to '+date.end:null,date.calendar,date.precision?date.precision+' precision':null].filter(Boolean).join(' · ');}
async function renderHistoricalPlans(featureId){
  if(workspaceMode!=='creator')return;const request=++historyPlanningRequest,campaign=current?.id,mode=workspaceMode;
  if(!campaign){$('#content').innerHTML='<section class="panel"><h2>Historical reference & prospective assessment</h2><p>Select a saved campaign first. This Creator view performs no installation, scheduling or execution.</p></section>';return;}
  $('#content').innerHTML='<p class="note">Loading Creator-only historical references…</p>';
  try{
    const [baseline,preview]=await Promise.all([api('historical-baseline',undefined,{creator:true}),api('historical-plans/'+encodeURIComponent(campaign),undefined,{creator:true})]);
    if(request!==historyPlanningRequest||workspaceMode!==mode||current?.id!==campaign||view!=='feature:'+featureId)return;
    const byId=new Map((baseline.events||[]).map(event=>[event.id,event])),plans=[...(preview.plans||[]),...(preview.held_at_cutoff||[])];
    $('#content').innerHTML='<section class="panel"><span class="eyebrow">CREATOR REFERENCE · READ ONLY</span><h2>Historical reference, prospective assessment and actual records</h2><p class="reference-note">Execution unavailable. These are sourced references and conditional assessments, not installed schedules, character knowledge or events that have occurred.</p>'+facts({status:preview.status,cutoff:preview.cutoff?.date||preview.cutoff?.reason||preview.cutoff?.ordinal||'Unbound',calendar_execution:preview.calendar_execution_bound===true?'Bound':'Unbound',resolver:preview.resolver_bound===true?'Bound':'Unbound'})+'<p>'+esc(preview.note||'Historical expectations never replace actual campaign facts.')+'</p></section><section class="panel"><h3>Immutable historical baseline</h3><p class="note">The following documented history and research proposals are reference assertions. Their inclusion does not establish occurrence in this playthrough.</p>'+(baseline.events||[]).map(event=>'<details><summary>'+esc(event.title)+' · '+esc(referenceDate(event.date))+'</summary><p>'+esc(event.description)+'</p>'+facts({research_status:event.research_status,classification:event.classification})+(event.historical_outcome_reference?'<p class="note">Historical outcome reference: '+esc(event.historical_outcome_reference.statement)+'</p>':'')+'<small>'+esc((event.source_refs||[]).join(' · '))+'</small></details>').join('')+'</section><section class="panel"><h3>Prospective assessment · not installed</h3>'+plans.map(plan=>{const assessment=plan.assessment||{};return '<details><summary>'+esc(plan.title||byId.get(plan.baseline_event_id)?.title||plan.baseline_event_id)+' · '+esc(label(plan.status))+'</summary><p>'+esc(referenceDate(plan.date))+'</p><p>'+esc(assessment.reason||'Assessment only; execution is unavailable.')+'</p>'+facts({window_relation:plan.window_relation,causal_completeness:assessment.causal_completeness||'Not certified',actual_outcome:assessment.actual_outcome??'Not established'})+(assessment.conditions||[]).map(condition=>'<p class="note">'+esc(condition.id||condition.type||'Condition')+' · '+esc(condition.requirement||'unspecified')+' · '+esc(condition.result||'unknown')+'</p>').join('')+'</details>';}).join('')+'</section><section class="panel"><h3>Actual campaign occurrence links</h3>'+((preview.actual_occurrence_refs||[]).length?'<p>'+esc(preview.actual_occurrence_refs.join(' · '))+'</p><p class="note">Explicit journal references only. These links do not independently verify a historical outcome.</p>':'<p class="note">No actual occurrence links are supplied. Reference plans have not been turned into campaign events.</p>')+'</section><section class="panel"><h3>Sources</h3>'+(baseline.sources||[]).map(source=>{const url=safeHttpUrl(source.url);return '<p>'+(url?'<a target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">'+esc(source.title)+'</a>':esc(source.title))+'</p>';}).join('')+'</section>';
  }catch(error){if(request!==historyPlanningRequest||workspaceMode!==mode||current?.id!==campaign||view!=='feature:'+featureId)return;$('#content').innerHTML='<section class="panel"><p>'+esc(error.message)+'</p><button class="quiet" id="retry-historical-plans">Retry historical reference</button></section>';$('#retry-historical-plans').onclick=()=>renderHistoricalPlans(featureId);}
}
function syncComposer(){
  syncActionReview();
  syncAssistanceControls();
  syncCommunicationControls();
  syncIntentControls();
  const player=workspaceMode==='player'&&current&&!loadingCampaign&&view==='story';$('#composer-form').hidden=!player;renderRoutineDrafts(player);
  $('#own-response-panel').hidden=!player;if(player&&(current.pending_declaration||transportPending))$('#own-response-panel').open=true;
  const accepted=current?.pending_declaration,allowed=Boolean(current?.capabilities?.can_declare)&&!accepted&&!transportPending&&!soloAttempt;
  $('#send-declaration').disabled=busy||!player||!allowed||!$('#declaration').value.trim();
  $('#retry-action').hidden=!transportPending;$('#retry-action').disabled=busy;
  $('#withdraw-action').hidden=!accepted||Boolean(transportPending);$('#withdraw-action').disabled=busy;
  document.querySelectorAll('[data-supported-action]').forEach(button=>button.disabled=busy||!player||!current?.actor_id||current.character_available===false||Boolean(accepted)||Boolean(transportPending));
  document.querySelectorAll('[data-rise-action]').forEach(button=>button.disabled=busy||!player||Boolean(accepted)||Boolean(transportPending));
  document.querySelectorAll('[data-process-command], [data-process-start]').forEach(button=>button.disabled=busy||!player||Boolean(accepted)||Boolean(transportPending)||Boolean(soloAttempt));
  $('#composer-help').textContent=preferences.submitKey==='enter'?'Enter to submit · Shift+Enter for a new line':'Enter for a new line · Ctrl/Cmd+Enter to submit';
  $('#draft-state').textContent=routineText($('#declaration').value?'draft.saved':'draft.empty');
  $('#action-state').textContent=routineText(busy?'request.busy':transportPending?'request.confirmation':accepted?(current.capabilities?.action_resolution?'request.pending':'request.unresolved'):!current?.actor_id?'actor.required':current.character_available===false?'actor.unavailable':'request.ready');
}
function storeTransport(pending){transportPending=pending;const key=pendingKey();if(key)writeLocal(key,pending);syncComposer();}
async function lookupAction(pending){return api('action-result/'+encodeURIComponent(pending.body.id)+'/'+encodeURIComponent(pending.body.request_id)+'?actor_id='+encodeURIComponent(pending.body.actor));}
async function finishAction(pending,result){
  if(current?.id!==pending.body.id||current?.actor_id!==pending.body.actor)return;
  storeTransport(null);if(pending.endpoint==='declaration'&&$('#declaration').value===pending.body.declaration){$('#declaration').value='';stashDraft();}
  const loaded=await openCampaign(pending.body.id,{actorId:pending.body.actor});
  if(!loaded||current?.id!==pending.body.id||current?.actor_id!==pending.body.actor)return;
  notice(['completed_successfully','completed_unsuccessfully'].includes(result.status)?routineOutcome(result):routineText(result.status==='withdrawn'?'request.withdrawn':current.capabilities?.action_resolution?'request.recorded':'request.recorded_unresolved'));
}
async function deliverAction(pending,checkFirst=false){
  if(busy)return;setBusy(true);
  try{
    if(checkFirst){try{const found=await lookupAction(pending);await finishAction(pending,found);return;}catch(error){if(error.status!==404)throw error;}}
    try{const result=await api(pending.endpoint,pending.body,{creator:false});await finishAction(pending,result);}
    catch(error){
      try{const found=await lookupAction(pending);await finishAction(pending,found);}
      catch(checkError){
        if(checkError.status===404&&error.status&&error.status<500){storeTransport(null);await openCampaign(pending.body.id,{actorId:pending.body.actor});notice(routineRecipe('request.rejected',{'request.rejected':{reason:error.message}}),true);}
        else{notice(routineRecipe('recovery.uncertain'),true);$('#connection-state').textContent=routineText('recovery.connection');}
      }
    }
  }catch(error){notice(error.message,true);}finally{setBusy(false);}
}
async function submitDeclaration(){
  if(busy||!current?.capabilities?.can_declare||current.pending_declaration||transportPending||soloAttempt)return;
  const declaration=$('#declaration').value;if(!declaration.trim())return;
  stashDraft();const pending={endpoint:'declaration',body:{id:current.id,revision:current.revision,request_id:crypto.randomUUID(),actor:current.actor_id,declaration}};storeTransport(pending);await deliverAction(pending);
}
async function submitSupportedAction(actionId,campaign,actor,kind='issue_equipment',expectedText=null){
  if(busy||workspaceMode!=='player'||!current||current.id!==campaign||current.actor_id!==actor||!actor||current.character_available===false||current.pending_declaration||transportPending)return;
  const identifier=kind==='scene_action'?'action_id':'order_id',action=supportedActions().find(item=>item.kind===kind&&item[identifier]===actionId&&(expectedText===null||item.text===expectedText));if(!action)return;
  stashDraft();const pending={endpoint:'action',body:{id:current.id,revision:current.revision,request_id:crypto.randomUUID(),actor:current.actor_id,kind:action.kind,[identifier]:action[identifier],text:action.text}};storeTransport(pending);await deliverAction(pending);
}
async function withdrawDeclaration(){
  const action=current?.pending_declaration;if(busy||!action||transportPending)return;
  const pending={endpoint:'withdraw-declaration',body:{id:current.id,revision:current.revision,request_id:crypto.randomUUID(),actor:current.actor_id,action_request_id:action.request_id}};storeTransport(pending);await deliverAction(pending);
}
function applyPreferences(){
  preferences.theme=['dark','light','parchment'].includes(preferences.theme)?preferences.theme:'parchment';preferences.font=preferences.font==='sans'?'sans':'serif';
  preferences.fontSize=Math.max(16,Math.min(26,Number(preferences.fontSize)||18));preferences.lineHeight=Math.max(1.4,Math.min(2.2,Number(preferences.lineHeight)||1.8));preferences.width=Math.max(560,Math.min(1000,Number(preferences.width)||740));
  document.body.dataset.reading=preferences.theme;document.body.dataset.motion=preferences.motion==='reduce'?'reduce':'system';document.body.dataset.mechanics=preferences.mechanics==='expanded'?'expanded':'concise';
  document.documentElement.style.setProperty('--reading-font',preferences.font==='serif'?'"Newsreader", Georgia, Cambria, serif':'"Instrument Sans", "Segoe UI", system-ui, sans-serif');document.documentElement.style.setProperty('--reading-size',preferences.fontSize+'px');document.documentElement.style.setProperty('--reading-line',preferences.lineHeight);document.documentElement.style.setProperty('--reading-width',preferences.width+'px');
  $('#font-size-value').textContent=preferences.fontSize+' px';$('#line-height-value').textContent=preferences.lineHeight;$('#reading-width-value').textContent=preferences.width+' px';writeLocal('irgs-reading-preferences',preferences);syncPreviewReadingControls();syncComposer();
}
function openSettings(){for(const [key,value] of Object.entries(preferences)){const control=$('#preferences-form').elements.namedItem(key);if(control)control.value=value;}applyPreferences();$('#preferences-dialog').showModal();}
async function ensureCatalog(){if(!rows(library.campaign_profiles).length)library=await api('catalog');return library;}
async function renderTrash(){
  $('#content').innerHTML='<div class="empty">Loading Campaign Trash…</div>';
  try{const data=await api('trash');if(view!=='trash')return;$('#content').innerHTML=`<article class="panel"><span class="eyebrow">RECOVERABLE CAMPAIGNS</span><h2>${data.campaigns.length} campaign${data.campaigns.length===1?'':'s'} in Trash</h2><p>Restore returns the exact saved campaign, including its history and pending decisions.</p>${data.campaigns.map(campaign=>`<div class="list-row trash-row"><div><strong>${esc(campaign.name)}</strong><small>Revision ${esc(campaign.revision)}</small></div><button class="quiet" data-restore="${esc(campaign.id)}" data-revision="${campaign.revision}">Restore campaign</button></div>`).join('')||'<p class="note">Trash is empty.</p>'}</article>`;document.querySelectorAll('[data-restore]').forEach(button=>button.onclick=async()=>{if(busy)return;setBusy(true);try{const result=await api('restore',{id:button.dataset.restore,revision:Number(button.dataset.revision)});await refreshList(result.id);view='story';await openCampaign(result.id);notice(routineText('campaign.restored'));}catch(error){notice(error.message,true);}finally{setBusy(false);}});}catch(error){notice(error.message,true);}
}
function validHistoricalPreview() {
  return !historicalLoading && historicalPreview?.ready===true && Boolean(historicalPreview.snapshot)
    && historicalPreview.entry?.id===historicalEntryId && historicalPreview.request===historicalRequest
    && (workspaceMode==='creator'||approvedEntries.get(historicalEntryId)?.snapshot_sha256===historicalPreview.snapshot_sha256)
    && typeof historicalPreview.snapshot_sha256==='string' && /^[a-f0-9]{64}$/i.test(historicalPreview.snapshot_sha256);
}
function resetHistoricalSetup() {
  historicalRequest+=1;historicalEntryId=null;historicalPreview=null;historicalLoading=false;
  $('#historical-setup').hidden=true;$('#create-dialog').classList.toggle('historical-mode',false);syncCreateControls();
}
function historicalRequestCurrent(request,id) {return request===historicalRequest && $('#create-profile').value==='__hyw' && $('#create-dialog').open && (!id || historicalEntryId===id);}
function renderHistoricalChoices() {
  const entries=historicalCatalogue.entries||[],picker=$('#historical-entry-select');
  picker.innerHTML=historicalEntryOptions(entries,historicalCatalogue.periods||[],historicalCatalogue.featured_years||[]);picker.value=historicalEntryId||'';
  $('#historical-count').textContent=`${entries.length} entry points · choose one to explore`;
  picker.onchange=()=>{
    if(busy)return;
    if(picker.value)return selectHistoricalEntry(picker.value);
    historicalRequest+=1;historicalEntryId=null;historicalPreview=null;historicalLoading=false;startingOptions=null;reviewSelection=null;startingRequest+=1;
    $('#historical-preview').innerHTML='<p class="note">Select an entry point to read its description and details.</p>';syncCreateControls();
  };syncCreateControls();
}
async function showHistoricalSetup(preferredId=null) {
  const request=++historicalRequest;historicalEntryId=null;historicalPreview=null;historicalLoading=true;
  $('#historical-setup').hidden=false;$('#create-dialog').classList.toggle('historical-mode',true);
  $('#historical-preview').innerHTML='<p class="note">Loading historical entry points…</p>';syncCreateControls();
  try {
    const catalogue=historicalCatalogue || await api('historical-campaigns');
    if(!historicalRequestCurrent(request))return false;
    historicalCatalogue=catalogue;renderHistoricalChoices();
    const selected=preferredId||setupEntryContext?.entry_id;
    if(!selected){historicalLoading=false;$('#historical-preview').innerHTML='<p class="note">Select an entry point to read its description and details.</p>';syncCreateControls();return true;}
    const preferred=catalogue.entries.find(entry=>entry.id===selected);
    if(!preferred)throw new Error('The selected entry is unavailable in this catalogue. Refresh the Content Library.');
    return await selectHistoricalEntry(preferred.id);
  } catch(err) {
    if(historicalRequestCurrent(request)){historicalLoading=false;$('#historical-preview').innerHTML=`<p class="note">${esc(err.message)}</p>`;syncCreateControls();}
    return false;
  }
}
async function selectHistoricalEntry(id,preserveError=false) {
  if(busy || $('#create-profile').value!=='__hyw' || !$('#create-dialog').open)return false;
  if(!(historicalCatalogue?.entries || []).some(entry=>entry.id===id))return false;
  const request=++historicalRequest;historicalEntryId=id;historicalPreview=null;historicalLoading=true;startingOptions=null;reviewSelection=null;startingRequest+=1;
  if(!preserveError)$('#create-error').textContent='';
  $('#historical-entry-select').value=id;
  $('#historical-preview').innerHTML='<p class="note">Loading the selected opening reference…</p>';syncCreateControls();
  try {
    const result=await api('historical-entry/'+encodeURIComponent(id));
    if(!historicalRequestCurrent(request,id))return false;
    if(result.entry?.id!==id)throw new Error('Historical entry identity mismatch. Select the entry again.');
    historicalPreview={...result,request};historicalLoading=false;if(workspaceMode==='player'&&result.ready&&approvedEntries.get(id)?.snapshot_sha256!==result.snapshot_sha256)throw new Error('The opening reference changed. Refresh the Content Library and review the starting point again.');
    const entry=result.entry;
    $('#historical-preview').innerHTML=`<article class="historical-preview"><div class="eyebrow">${esc(entry.year)} ENTRY POINT</div><h3>${esc(entry.title)}</h3><p>${esc(entry.description || '')}</p>${result.snapshot?historicalSnapshotMarkup(result.snapshot):'<p class="reference-note">Opening date and detailed snapshot not yet verified. This is catalogue reference material; campaign creation remains unavailable for this entry.</p>'}${validHistoricalPreview()?'<p class="ready-note">Starting reference available. Review its scope, choose your character, and confirm before saving.</p>':'<p class="note">This entry is available for inspection. A ready, verified opening snapshot is required for creation.</p>'}</article>`;
    syncCreateControls();return true;
  } catch(err) {
    if(historicalRequestCurrent(request,id)){historicalLoading=false;historicalPreview=null;$('#historical-preview').innerHTML=`<p class="note">${esc(err.message)}</p>`;syncCreateControls();}
    return false;
  }
}

function wizardBase(){
  const profile=$('#create-profile').value;
  if(profile!=='__hyw'){if(workspaceMode!=='creator')throw new Error('Choose an approved campaign from the Content Library.');return {profile_id:profile};}
  if(!validHistoricalPreview())throw new Error('Choose a ready, verified opening snapshot before continuing.');
  return {profile_id:'military',scenario_id:'hundred-years-war',entry_id:historicalEntryId,snapshot_sha256:historicalPreview.snapshot_sha256};
}
function setupOriginKey(){try{return JSON.stringify(wizardBase());}catch{return null;}}
function validStartingOptions(){return !startingLoading&&startingOptions?.available===true&&startingOptions.queryKey===setupOriginKey()&&startingOptions.request===startingRequest&&startingOptions.default_scenario_id===$('#starting-scenario').value&&/^[a-f0-9]{64}$/i.test(startingOptions.selection_digest||'');}
function invalidateReview(){
  syncPreviewCharacter();reviewSelection=null;startPreviewRequest+=1;startCheckLoading=false;
  $('#confirm-declaration-start').checked=false;syncStartGuidance();syncCreateControls();
}
function syncStartGuidance(){
  const target=$('#start-readiness-guidance');if(!target)return;
  if($('#character-kind').value==='existing'){
    target.textContent=existingPlayableOpenings().length?'This person has an optional sourced context below. Choose it explicitly to review its bounded attempts. Leaving it unselected keeps declaration / reference mode.':'No executable context is offered for this person at this checkpoint. Review will confirm declaration / reference use; no other person’s context or new-character fiction can be borrowed.';return;
  }
  const authored=$('#character-kind').value==='new'&&Boolean($('#character-opening')?.value);
  target.textContent=authored?'You selected an authored fictional opening. Review will check the actions actually available to this new character.':'Reference readiness and character eligibility do not establish executable play. Review will check this exact character and start. A start with no executable actions requires a deliberate declaration / reference choice. New human characters can instead select an available fictional opening below.';
}
function syncCreateControls(){
  const historical=$('#create-profile').value==='__hyw',pendingReview=Boolean(reviewSelection?.recovery);
  $('#create-profile').disabled=busy||workspaceMode==='player';$('#cancel-create').disabled=busy;$('#historical-entry-select').disabled=busy;
  document.querySelectorAll('#historical-setup button').forEach(button=>button.disabled=busy);
  document.querySelectorAll('[data-setup-step]').forEach(section=>section.hidden=Number(section.dataset.setupStep)!==wizardStep);
  document.querySelectorAll('#setup-progress li').forEach((item,index)=>{if(index===wizardStep)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');});
  $('#setup-back').hidden=wizardStep===0||pendingReview;$('#setup-back').disabled=busy;
  $('#setup-next').hidden=wizardStep===3;$('#setup-next').disabled=busy||startCheckLoading||(wizardStep===1&&historical&&!validHistoricalPreview())||(wizardStep===2&&!validStartingOptions());
  $('#setup-next').textContent=wizardStep===0?'Choose starting point →':wizardStep===1?'Choose character →':'Review campaign →';
  $('#create-submit').hidden=wizardStep!==3;$('#create-submit').disabled=busy||wizardStep!==3||!reviewSelection||(!pendingReview&&reviewSelection.readiness?.status==='declaration_only'&&!$('#confirm-declaration-start').checked);$('#create-submit').textContent=pendingReview?'Check / retry campaign creation':reviewSelection?.readiness?.status==='declaration_only'?'Create declaration / reference campaign':'Start campaign';
  $('#declaration-start-consent').hidden=wizardStep!==3||pendingReview||reviewSelection?.readiness?.status!=='declaration_only';
  $('#create-dialog').dataset.step=String(wizardStep);syncPreviewCharacter();$('#create-title').textContent=['Name your adventure','Choose your moment','Forge your character','Your story begins here'][wizardStep];$('#create-step-intro').textContent=['A world to enter. A life to make your own.','Choose where history leaves off and your story begins.','Create a character or step into an existing life.','Review your place in the world before taking the first step.'][wizardStep];
}
function setupDescriptionMarkup(description){
  if(!description)return '';
  const body=typeof description==='string'?`<p>${esc(description)}</p>`:description.entry_guide?entryGuideMarkup(description.entry_guide):description.immediate_situation||description.player_options||description.practical_pressures?entryGuideMarkup(description):textItems(description.summary||description.briefing||description.description).map(value=>`<p>${esc(value)}</p>`).join('');
  return `<details class="setting-details"><summary>Read the starting situation</summary>${body}</details>`;
}

function entryGuideMarkup(guide){
  if(!guide)return '';
  return `<section class="entry-guide"><h3>Before you start</h3>${textItems(guide.summary).map(text=>`<p>${esc(text)}</p>`).join('')}${[['immediate_situation','The immediate situation'],['player_options','Ways to enter this world'],['practical_pressures','Practical pressures'],['not_yet_established','What still needs to be established']].map(([key,title])=>textItems(guide[key]).length?`<details><summary>${title}</summary>${textItems(guide[key]).map(text=>`<p>${esc(text)}</p>`).join('')}</details>`:'').join('')}${guide.future_rule?`<p class="reference-note">${esc(guide.future_rule)}</p>`:''}</section>`;
}
function startingCharacters(){return startingOptions?.characters||startingOptions?.entities?.characters||[];}
function startingFactions(){return startingOptions?.factions||startingOptions?.entities?.factions||[];}
function factionRepresentatives(faction){return Array.isArray(faction?.control?.actor_ids)?startingCharacters().filter(character=>character.exists===true&&faction.control.actor_ids.includes(character.id)):[];}
function eligibleFactions(){return startingFactions().filter(faction=>faction.eligible===true&&factionRepresentatives(faction).length);}
async function loadStartingOptions(scenarioId=null){
  startPreviewRequest+=1;startCheckLoading=false;
  let base;try{base=wizardBase();}catch(error){$('#create-error').textContent=error.message;return;}
  const key=JSON.stringify(base),request=++startingRequest,priorKind=$('#character-kind').value,priorActor=$('#starting-character').value,priorFaction=$('#starting-faction').value;
  startingLoading=true;startingOptions=null;reviewSelection=null;$('#starting-context').innerHTML='<p>Loading dated character and faction availability…</p>';syncCreateControls();
  try{
    const result=await api('starting-options?'+new URLSearchParams({...base,...(scenarioId?{starting_scenario_id:scenarioId}:{})}).toString());
    if(request!==startingRequest||setupOriginKey()!==key||!$('#create-dialog').open)return;
    if(result.available!==true)throw new Error(result.reason||'No verified starting configuration is available.');
    startingOptions={...result,queryKey:key,request};startingLoading=false;
    const scenarios=result.scenarios||[],characters=result.characters||result.entities?.characters||[],factions=result.factions||result.entities?.factions||[],eligible=characters.filter(character=>character.eligible===true);
    $('#starting-context').innerHTML=`<span class="eyebrow">SOLO STARTING OPTIONS</span><h3>${esc(result.as_of?.label||'Profile setup')}</h3><p class="note">Availability comes from this selected starting point. Existence and participation do not grant player control.</p>${setupDescriptionMarkup(result.entry_description)}`;
    $('#starting-scenario').innerHTML=scenarios.map(scenario=>`<option value="${esc(scenario.id)}">${esc(scenario.title)}</option>`).join('');$('#starting-scenario').value=result.default_scenario_id||scenarios[0]?.id||'';
    const factionChoices=eligibleFactions();
    $('#character-kind').innerHTML=`${result.character_creation_allowed?'<option value="new">Create your own character</option>':''}${eligible.length?'<option value="existing">Choose an eligible existing character</option>':''}${factionChoices.length?'<option value="faction">Choose a policy-authorized faction</option>':''}`;
    $('#starting-character').innerHTML=characters.map(character=>`<option value="${esc(character.id)}" ${character.eligible?'':'disabled'}>${esc(character.name)}${character.eligible?'':' · unavailable'}</option>`).join('');
    $('#starting-character').value=eligible.some(character=>character.id===priorActor)?priorActor:eligible.find(character=>character.id==='AST-01')?.id||eligible[0]?.id||'';
    $('#starting-faction').innerHTML=factionChoices.map(faction=>`<option value="${esc(faction.id)}">${esc(faction.name)}</option>`).join('');$('#starting-faction').value=factionChoices.some(faction=>faction.id===priorFaction)?priorFaction:factionChoices[0]?.id||'';
    $('#character-kind').value=base.profile_id==='ast'&&eligible.some(character=>character.id==='AST-01')?'existing':priorKind==='faction'&&factionChoices.some(faction=>faction.id===priorFaction)?'faction':priorKind==='existing'&&eligible.some(character=>character.id===priorActor)?'existing':result.character_creation_allowed?'new':eligible.length?'existing':factionChoices.length?'faction':'';
    const priorOrganization=$('#character-organization').value;$('#character-organization').innerHTML='<option value="">No organization selected</option>'+factions.filter(organization=>organization.exists===true).map(organization=>`<option value="${esc(organization.id)}">${esc(organization.name)} · recruitment unknown</option>`).join('');$('#character-organization').value=factions.some(organization=>organization.exists===true&&organization.id===priorOrganization)?priorOrganization:'';
    $('#starting-factions').innerHTML=factions.map(faction=>`<article class="record-card"><h3>${esc(faction.name)}</h3><p class="faction-state">Exists: ${faction.exists===true?'yes':faction.exists===false?'no':'unknown'} · Participation: ${esc(label(faction.participation||'unknown'))} · Control eligible: ${faction.eligible?'yes':'no'}</p><p class="note">${esc(faction.eligibility_reason||'Control requires a sourced policy.')}</p></article>`).join('')||'<p class="note">No dated faction records are supplied for this setup. New institutions must be established through the selected rules.</p>';
    renderPlayableOpeningPicker();updateCharacterFields();syncCreateControls();
  }catch(error){if(request===startingRequest){startingLoading=false;startingOptions=null;$('#starting-context').innerHTML=`<p class="reference-note">${esc(error.message)}</p>`;syncCreateControls();}}
}
function playableOpenings(){return Array.isArray(startingOptions?.playable_openings)?startingOptions.playable_openings.filter(opening=>opening&&typeof opening.id==='string'&&opening.id):[];}
function ensureOpeningPicker(){
  if(!$('#existing-character-opening')){
    $('#existing-character-fields').insertAdjacentHTML('beforeend','<section id="existing-opening-section" class="playable-opening-selection" hidden><h3>Optional sourced starting context</h3><p class="note">Choose a context reviewed for this exact person and checkpoint. It is never added automatically and grants only its listed attempts.</p><label>Starting context<select id="existing-character-opening"><option value="">Declaration / reference only · no operational context</option></select></label><div id="existing-opening-review"></div></section>');
    $('#existing-character-opening').onchange=()=>{renderExistingOpeningReview();invalidateReview();};
  }
  if($('#character-opening'))return;
  $('#new-character-fields').insertAdjacentHTML('beforeend','<section id="character-opening-section" class="playable-opening-selection" hidden><h3>Choose how to begin</h3><p class="note">This adds an authored fictional local situation to the historical starting world. It is separate from historical evidence and your background testimony.</p><label>Opening situation<select id="character-opening"><option value="">Declaration / reference only · no authored opening</option></select></label><div id="character-opening-review"></div></section>');
  $('#character-opening').onchange=()=>{renderOpeningChoiceReview();invalidateReview();};
}
function existingPlayableOpenings(actor=$('#starting-character').value){
  return (startingOptions?.existing_character_openings||[]).filter(item=>item?.actor_id===actor&&typeof item.id==='string'&&item.id);
}
function renderExistingOpeningReview(){const opening=existingPlayableOpenings().find(item=>item.id===$('#existing-character-opening').value);$('#existing-opening-review').innerHTML=openingChoiceMarkup(opening);}
function renderExistingOpeningPicker(){
 const picker=$('#existing-character-opening'),prior=picker.value,openings=$('#character-kind').value==='existing'?existingPlayableOpenings():[];
 $('#existing-opening-section').hidden=!openings.length;picker.disabled=$('#character-kind').value!=='existing';
 picker.innerHTML='<option value="">Declaration / reference only · no operational context</option>'+openings.map(item=>`<option value="${esc(item.id)}">${esc(item.title)} · sourced context</option>`).join('');
 picker.value=openings.some(item=>item.id===prior)?prior:'';renderExistingOpeningReview();
}
function openingChoiceMarkup(opening){
  if(!opening)return '<p class="note">No local situation, location, possessions or elapsed-time rule will be added.</p>';
  return `<div class="opening-choice-review"><h4>${esc(opening.title||opening.id)}</h4><p>${esc(opening.description||'')}</p>${['requirements','review','scope'].map(key=>(key==='review'&&opening[key]&&!Array.isArray(opening[key])&&typeof opening[key]==='object'?Object.entries(opening[key]).map(([name,value])=>label(name)+': '+String(value)):textItems(opening[key])).map(text=>`<p class="note">${esc(text)}</p>`).join('')).join('')}</div>`;
}
function renderOpeningChoiceReview(){const opening=playableOpenings().find(item=>item.id===$('#character-opening')?.value);if($('#character-opening-review'))$('#character-opening-review').innerHTML=openingChoiceMarkup(opening);}
function renderPlayableOpeningPicker(){
  ensureOpeningPicker();const prior=$('#character-opening').value,openings=playableOpenings();$('#character-opening-section').hidden=!openings.length;
  $('#character-opening').innerHTML='<option value="">Declaration / reference only · no authored opening</option>'+openings.map(opening=>`<option value="${esc(opening.id)}">${esc(opening.title||opening.id)} · authored fiction</option>`).join('');
  $('#character-opening').value=openings.some(opening=>opening.id===prior)?prior:'';renderOpeningChoiceReview();
}
function updateCharacterFields(){
  ensureOpeningPicker();const kind=$('#character-kind').value,isNew=kind==='new';$('#new-character-fields').hidden=!isNew;$('#existing-character-fields').hidden=kind!=='existing';$('#faction-character-fields').hidden=kind!=='faction';
  const selectionKey=JSON.stringify([setupOriginKey(),$('#starting-scenario').value,kind,isNew?null:$('#starting-character').value]);
  if(selectionKey!==openingSelectionKey){$('#character-opening').value='';$('#existing-character-opening').value='';openingSelectionKey=selectionKey;renderOpeningChoiceReview();}
  renderExistingOpeningPicker();
  for(const id of ['new-character-name','new-character-species','new-character-background','character-opening',...BACKGROUND_FIELDS])$('#'+id).disabled=!isNew;
  $('#new-character-name').required=isNew;$('#new-character-species').required=isNew;
  const character=(startingOptions?.characters||startingOptions?.entities?.characters||[]).find(item=>item.id===$('#starting-character').value);
  $('#character-eligibility').textContent=character?.eligibility_reason||'Only an eligible individual can be selected.';$('#existing-character-background').innerHTML=character?'<h3>Preserved character identity</h3>'+facts(character.identity||{name:character.name,species:character.species||'as recorded'})+'<p class="note">This selected identity and its source checkpoint are preserved. Existing characters are not rewritten by the optional new-character fields.</p>':'';updateFactionFields();invalidateReview();
}
function updateFactionFields(){
  const faction=eligibleFactions().find(item=>item.id===$('#starting-faction').value),prior=$('#faction-representative').value,representatives=factionRepresentatives(faction);
  $('#faction-representative').innerHTML=representatives.map(character=>`<option value="${esc(character.id)}">${esc(character.name)}</option>`).join('');$('#faction-representative').value=representatives.some(character=>character.id===prior)?prior:representatives[0]?.id||'';
  $('#faction-control-policy').innerHTML=faction?`${facts({control_mode:faction.control.mode,permitted_powers:faction.control.powers?.join(', ')||'None supplied',policy_reason:faction.eligibility_reason||'As recorded',policy_source:faction.eligibility_source_ref||'Not supplied'})}<p class="note">Only this policy’s listed powers apply through its permitted representative. Institutional commands still require their actual authority and resources.</p>`:'No eligible faction with a permitted existing representative is available.';invalidateReview();
}
const BACKGROUND_GROUPS={identity:{origin:'character-origin',birthplace:'character-birthplace',nationality:'character-nationality',culture:'character-culture'},life_path:{family:'character-family',upbringing:'character-upbringing',education:'character-education'},career:{arrangement:'character-arrangement',relationship_stage:'character-relationship-stage',organization_id:'character-organization',aspiration:'character-aspiration'}};
const BACKGROUND_FIELDS=Object.values(BACKGROUND_GROUPS).flatMap(fields=>Object.values(fields));
function newCharacterDetails(){
  const details={};for(const [group,fields]of Object.entries(BACKGROUND_GROUPS)){const values=Object.fromEntries(Object.entries(fields).map(([key,id])=>[key,$('#'+id).value]).filter(([,value])=>value.trim()));if(group==='career'&&values.arrangement==='independent'&&values.relationship_stage==='undecided'&&!values.organization_id&&!values.aspiration)continue;if(Object.keys(values).length)details[group]=values;}return details;
}
function careerValueLabel(value){return ({independent:'Independent / unaffiliated',mercenary:'Mercenary / contractor',retinue:'Retinue / military service',civilian:'Civilian profession',institutional:'Institutional / scholarly service',undecided:'Undecided',seeking:'Seeking an opportunity',offer_claimed:'Reported offer · unconfirmed',current_claimed:'Reported current position · unconfirmed',former:'Former service · user account',membership_claimed:'Reported membership · unconfirmed'})[value]||value;}
function backgroundDetailsMarkup(details){
  if(!details)return '';const data=details.details||details,parts=[['identity','Declared identity & origin'],['life_path','Declared life path'],['career','Starting career intent · unconfirmed']].filter(([group])=>data[group]&&Object.keys(data[group]).length);if(!parts.length)return '';
  return '<section class="background-testimony"><h3>User testimony</h3><p class="note">These declarations establish no other people, property, proficiency, employment, contract, nationality rule or authority.</p>'+parts.map(([group,title])=>'<section><h4>'+title+'</h4>'+Object.entries(data[group]).map(([key,value])=>'<div class="list-row"><small>'+esc(label(key==='organization_id'?'organization reference':key))+'</small><p class="record">'+esc(group==='career'&&['arrangement','relationship_stage'].includes(key)?careerValueLabel(value):value)+'</p></div>').join('')+'</section>').join('')+'</section>';
}
function selectedCharacter(){
  if(!validStartingOptions())throw new Error('Refresh the verified starting options before reviewing this campaign.');
  if($('#character-kind').value==='existing'){
    const character=(startingOptions.characters||startingOptions.entities?.characters||[]).find(item=>item.id===$('#starting-character').value&&item.eligible===true);
    if(!character)throw new Error('Choose an eligible existing character.');
    const openingId=$('#existing-character-opening').value;
    if(openingId&&!existingPlayableOpenings(character.id).some(item=>item.id===openingId))throw new Error('Choose a context offered for this exact person, or leave it unselected.');
    return {kind:'existing',actor_id:character.id,...(openingId?{opening_id:openingId}:{})};
  }
  if($('#character-kind').value==='faction'){
    const faction=eligibleFactions().find(item=>item.id===$('#starting-faction').value),actor=$('#faction-representative').value;
    if(!faction||!factionRepresentatives(faction).some(character=>character.id===actor))throw new Error('Choose an eligible faction and its explicitly permitted existing representative.');
    return {kind:'faction',entity_id:faction.id,actor_id:actor};
  }
  if($('#character-kind').value!=='new')throw new Error('Choose a permitted player character or control policy.');
  if(!startingOptions.character_creation_allowed)throw new Error('Character creation is unavailable for this starting point.');
  const name=$('#new-character-name').value.trim(),species=$('#new-character-species').value.trim();if(!name||!species)throw new Error('Enter the character’s name and species.');
  const openingId=$('#character-opening')?.value||'';if(openingId&&!playableOpenings().some(opening=>opening.id===openingId))throw new Error('Choose an available authored opening or leave it unselected.');
  return {kind:'new',name,species,background:$('#new-character-background').value,...newCharacterDetails(),...(openingId?{opening_id:openingId}:{})};
}
function reviewedChoice(){
  const name=$('#campaign-name').value.trim();if(!name)throw new Error('Name the campaign before continuing.');
  const scenario=$('#starting-scenario').value;if(!(startingOptions?.scenarios||[]).some(item=>item.id===scenario))throw new Error('Choose an available solo scenario.');
  return {...wizardBase(),name,starting_scenario_id:scenario,selection_digest:startingOptions.selection_digest,character:selectedCharacter()};
}
function readinessReviewMarkup(readiness,recovery){
  if(recovery)return '<p class="reference-note">Recover the original reviewed creation request. This check does not change its selected start or add a new opening.</p>';
  if(readiness?.status==='supported_slice')return `<section class="capability-note" aria-label="Selected start playability"><h3>Supported local slice</h3><p>${esc(readiness.action_count)} executable action choices and ${esc(readiness.process_start_count)} process starts are currently offered to this character. Each is an attempt checked by Core when confirmed.</p><p>General combat, freeform resolution, automatic narration and calendar advancement remain unavailable.</p></section>`;
  return '<section class="capability-note" aria-label="Selected start playability"><h3>Declaration / reference only</h3><p>This selected character and start currently offer no executable actions or process starts. You can inspect received records and save exact intent; that intent remains unresolved and advances no elapsed time.</p><p>Use Back to review an offered actor-bound context or a new human character’s fictional opening for a supported local slice. An existing historical person will keep their actual records and will receive no courier setup automatically.</p></section>';
}
function renderReview(payload,recovery=false){
  const character=payload.character||{},existing=startingCharacters().find(item=>item.id===character.actor_id),faction=startingFactions().find(item=>item.id===character.entity_id);
  const characterName=character.kind==='new'?character.name:existing?.name||character.actor_id;
  const chosenOpening=character.opening_id?(character.kind==='new'?playableOpenings():existingPlayableOpenings(character.actor_id)).find(opening=>opening.id===character.opening_id):null;
  const openingReview=character.opening_id?`<section class="playable-opening-review"><span class="eyebrow">${character.kind==='new'?'AUTHORISED FICTIONAL OPENING':'EXPLICIT SOURCED STARTING CONTEXT'}</span>${chosenOpening?openingChoiceMarkup(chosenOpening):`<p>Retained opening selection: ${esc(character.opening_id)}. Its exact setup will be validated by the host. The prior request identity and choices remain unchanged.</p>`}</section>`:'';
  const control=character.kind==='new'?{mode:'individual',powers:['declare_own_intent']}:(character.kind==='faction'?faction:existing)?.control;
  const summary={profile:payload.scenario_id==='hundred-years-war'?'Century of Conflict: The Hundred-Years’ War':label(payload.profile_id),starting_point:startingOptions?.as_of?.label||payload.entry_id||'Profile checkpoint',character:characterName,species:character.species||existing?.species||existing?.identity?.species||'as recorded',scenario:payload.starting_scenario_id||'individual',...(character.kind==='faction'?{faction:faction?.name||character.entity_id}:{}),control_mode:control?.mode?label(control.mode):'Policy terms not loaded',permitted_powers:Array.isArray(control?.powers)?control.powers.join(', ')||'None supplied':'Not loaded; the retained selection will be checked by the host'};
  $('#setup-review').innerHTML=`<span class="eyebrow">SOLO CAMPAIGN REVIEW</span><h2>${esc(payload.name)}</h2>${readinessReviewMarkup(reviewSelection?.readiness,recovery)}${recovery?'<p class="reference-note">A previous Start request has an unconfirmed receipt. Retry this exact request to recover the same campaign. Its identity and choices are retained.</p>':''}<div class="setup-summary">${facts(summary)}</div>${openingReview}${character.kind==='faction'&&faction?`<p class="note">${esc(faction.eligibility_reason||'As recorded in the selected control policy.')}</p>${facts({control_policy_source:faction.eligibility_source_ref||'Not supplied'})}`:''}${character.kind==='new'&&character.background?`<h3>User-declared background</h3><p class="record">${esc(character.background)}</p><p class="note">This declaration supplies background testimony; capabilities and possessions require their own established records.</p>`:''}${character.kind==='new'?backgroundDetailsMarkup(character):''}${setupDescriptionMarkup(startingOptions?.entry_description)}<p class="reference-note">${character.kind==='faction'?'Faction selection grants only the reviewed policy’s listed powers through the permitted representative. It supplies no automatic national authority, appointments or resources.':'The selected person’s control follows the listed policy. Wealth, inventory quantities, capabilities, appointments and faction-level powers remain unknown unless the selected profile supplies them.'}</p><details><summary>Starting reference provenance</summary>${facts({source:startingOptions?.source||'Retained creation request',selection_digest:payload.selection_digest,snapshot_sha256:payload.snapshot_sha256||'Not a historical snapshot'})}</details>`;
}

function creationPayload(){
  if(wizardStep!==3||!reviewSelection)throw new Error('Review the campaign and character before starting.');
  if(!reviewSelection.recovery&&JSON.stringify(reviewedChoice())!==reviewSelection.signature)throw new Error('The starting choices changed. Review them again before starting.');
  if(!reviewSelection.recovery&&reviewSelection.readiness?.status==='declaration_only'&&!$('#confirm-declaration-start').checked)throw new Error('Choose declaration / reference use explicitly, or go Back to review a supported opening.');
  reviewSelection.requestId=reviewSelection.requestId||crypto.randomUUID();return {...reviewSelection.payload,...(reviewSelection.creator?{mode:'creator'}:{}),request_id:reviewSelection.requestId};
}
async function wizardNext(){
  if(busy)return;$('#create-error').textContent='';
  try{
    if(wizardStep===0){if(!$('#campaign-name').value.trim())throw new Error('Enter a campaign name.');wizardStep=1;invalidateReview();if($('#create-profile').value==='__hyw')await showHistoricalSetup();else{$('#profile-opening').innerHTML='<h3>A new, sourced campaign</h3><p>No historical date is inferred for this generic profile. Create a character next; actual possessions and capabilities remain to be established.</p>';}}
    else if(wizardStep===1){wizardBase();wizardStep=2;await loadStartingOptions();}
    else if(wizardStep===2){
      const payload=reviewedChoice(),signature=JSON.stringify(payload),request=++startPreviewRequest,dialog=createDialogRequest,creator=workspaceMode==='creator';
      const {character,...base}=payload;delete base.name;
      const choice={character_kind:character.kind,...(character.kind==='new'?{species:character.species,...(character.opening_id?{opening_id:character.opening_id}:{})}:{actor_id:character.actor_id,...(character.opening_id?{opening_id:character.opening_id}:{}),...(character.entity_id?{entity_id:character.entity_id}:{})})};
      startCheckLoading=true;syncCreateControls();let readiness;
      try{readiness=await api('starting-preview?'+new URLSearchParams({...base,...choice}),undefined,{creator});}
      catch(error){if(request!==startPreviewRequest||dialog!==createDialogRequest||!$('#create-dialog').open)return;throw error;}
      if(request!==startPreviewRequest||dialog!==createDialogRequest||!$('#create-dialog').open||wizardStep!==2||creator!==(workspaceMode==='creator')||signature!==JSON.stringify(reviewedChoice()))return;
      startCheckLoading=false;
      if(!readiness||readiness.engine_start_context_contract!=='irgs-start-readiness-1'||readiness.engine_review?.schema_version!=='irgs-start-readiness-1'||readiness.schema_version!==1||!['supported_slice','declaration_only'].includes(readiness.status)||!Number.isSafeInteger(readiness.action_count)||!Number.isSafeInteger(readiness.process_start_count)||readiness.action_count<0||readiness.process_start_count<0||(readiness.status==='supported_slice')!==(readiness.action_count+readiness.process_start_count>0))throw new Error('The host could not verify this start’s current capabilities. No campaign was created. Retry review when its source is available.');
      reviewSelection={payload,signature,readiness,requestId:null,creator};$('#confirm-declaration-start').checked=false;wizardStep=3;renderReview(payload);
    }
    syncCreateControls();$('#create-title').focus?.();
  }catch(error){startCheckLoading=false;$('#create-error').textContent=error.message;syncCreateControls();}
}
async function openCreateDialog(selection=null){
  if(busy||!token)return;const request=++createDialogRequest,mode=workspaceMode;const pending=readLocal('irgs-create-pending'),selected=selection?.id?approvedEntries.get(selection.id):null;
  if(workspaceMode==='player'&&pending?.mode==='creator'){notice('An unconfirmed Creator initialization is retained. Open Creator workspace to check that exact request.',true);changeView('content-library');return;}
  if(workspaceMode==='player'&&!pending&&(!selected||selected.snapshot_sha256!==selection.snapshot_sha256)){changeView('content-library');return;}
  $('#create-error').textContent='';try{
    if(mode==='creator')await ensureCatalog();if(request!==createDialogRequest||mode!==workspaceMode)return;loadProfiles();setupEntryContext=selected?{campaign_id:selected.campaign_id,entry_id:selected.id,snapshot_sha256:selected.snapshot_sha256}:null;
    if(pending){wizardStep=3;reviewSelection={payload:pending,requestId:pending.request_id,recovery:true,creator:pending.mode==='creator'};renderReview(pending,true);}
    else{wizardStep=0;reviewSelection=null;startingOptions=null;$('#campaign-name').value='';$('#new-character-name').value='';$('#new-character-species').value='human';$('#new-character-background').value='';ensureOpeningPicker();$('#character-opening').value='';$('#existing-character-opening').value='';openingSelectionKey=null;for(const id of BACKGROUND_FIELDS)$('#'+id).value=id==='character-arrangement'?'independent':id==='character-relationship-stage'?'undecided':'';if(selected){$('#create-profile').value='__hyw';$('#profile-description').textContent='Selected opening: '+selected.year+' · '+selected.title+'. The exact verified reference will be rechecked before character review.';}}
    $('#create-dialog').showModal();syncCreateControls();
  }catch(error){notice(error.message,true);}
}
function loadProfiles(){
  const profiles=workspaceMode==='creator'?rows(library.campaign_profiles).filter(profile=>!['ast','hundred-years-war','hyw'].includes(profile.id)&&profile.scenario_id!=='hundred-years-war'&&!String(profile.status||'').toLowerCase().includes('archived')):[];
  $('#create-profile').innerHTML=profiles.map(profile=>`<option value="${esc(profile.id)}">${esc(profile.name||profile.id)} · Creator authoring</option>`).join('')+'<option value="__hyw">Century of Conflict · historical campaign</option>';$('#create-profile').value=profiles[0]?.id||'__hyw';
  const describe=()=>{startingRequest+=1;startingOptions=null;reviewSelection=null;setupEntryContext=null;wizardStep=0;resetHistoricalSetup();$('#profile-opening').innerHTML='';const profile=profiles.find(item=>item.id===$('#create-profile').value);$('#profile-description').textContent=$('#create-profile').value==='__hyw'?'Choose a verified dated opening, then a Solo character. Proposed scenario references remain unavailable for launch.':profile?.description||profile?.source_status||'Creator initialization. This technical profile is not a published campaign listing.';syncCreateControls();};
  $('#create-profile').onchange=describe;describe();
}

document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>changeView(button.dataset.view));
document.querySelectorAll('[role=tab]').forEach(button=>button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=[...document.querySelectorAll('[role=tab]')],index=tabs.indexOf(button),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;changeView(tabs[next].dataset.view);tabs[next].focus();});
bindInspectors();bindSoloControls();bindIntentControls();bindPreviewControls();$('#inspect-dialog').addEventListener('close',()=>{++inspectorRequest;});$('#close-inspector').onclick=()=>$('#inspect-dialog').close();
$('#toggle-nav').onclick=()=>togglePreviewDrawer('navigation');
$('#toggle-context').onclick=()=>togglePreviewDrawer('character');
$('#close-context').onclick=()=>{document.body.classList.remove('context-open');$('#toggle-context').setAttribute('aria-expanded','false');$('#toggle-context').focus();};
document.addEventListener('keydown',event=>{if(event.key!=='Escape'||document.querySelector('dialog[open]'))return;if(document.body.classList.contains('tools-open')){$('#close-tools').click();event.preventDefault();}else if(document.body.classList.contains('context-open')){$('#close-context').click();event.preventDefault();}else if(document.body.classList.contains('nav-open')){document.body.classList.remove('nav-open');$('#toggle-nav').setAttribute('aria-expanded','false');$('#toggle-nav').focus();event.preventDefault();}});
$('#settings').onclick=openSettings;$('#close-settings').onclick=()=>$('#preferences-dialog').close();$('#preferences-form').onsubmit=event=>event.preventDefault();
$('#preferences-form').oninput=event=>{const control=event.target;if(control.name){preferences[control.name]=control.type==='range'?Number(control.value):control.value;applyPreferences();document.querySelectorAll('.mechanical-detail').forEach(detail=>detail.open=preferences.mechanics==='expanded');}};
$('#declaration').oninput=()=>{invalidateSoloProposal();stashDraft();syncComposer();};$('#declaration').onkeydown=event=>{const submit=event.key==='Enter'&&(preferences.submitKey==='enter'?!event.shiftKey:(event.ctrlKey||event.metaKey));if(submit){event.preventDefault();if(!$('#send-declaration').disabled)$('#composer-form').requestSubmit();}};
$('#composer-form').onsubmit=event=>{event.preventDefault();return submitDeclaration();};$('#retry-action').onclick=()=>{if(transportPending)deliverAction(transportPending,true);};$('#withdraw-action').onclick=withdrawDeclaration;
$('#campaign').onchange=()=>{if(busy){$('#campaign').value=current?.id||'';return;}openCampaign($('#campaign').value).catch(error=>notice(error.message,true));};
$('#player-character').onchange=()=>{if(busy){$('#player-character').value=current?.actor_id||'';return;}if(current)openCampaign(current.id,{actorId:$('#player-character').value}).catch(error=>notice(error.message,true));};
$('#workspace-mode').onclick=async()=>{
  if(busy)return;invalidateActionReview();stashDraft();rememberScroll();const id=current?.id,actor=current?.actor_id;
  campaignRequest+=1;createDialogRequest+=1;featuresRequest+=1;features=[];drawFeatureNav();workspaceMode=workspaceMode==='creator'?'player':'creator';view=workspaceMode==='creator'?'creator':'story';current=null;currentBinding=null;transportPending=null;
  if($('#inspect-dialog').open)$('#inspect-dialog').close();$('#inspect-content').innerHTML='';render();
  const mode=workspaceMode,request=campaignRequest;
  try{await Promise.all([loadFeatureNav({applyRoute:false}),...(mode==='creator'?[ensureCatalog()]:[])]);if(request!==campaignRequest||workspaceMode!==mode||$('#campaign').value!==(id||''))return;updateViewRoute(view);if(id)await openCampaign(id,{actorId:actor});}catch(error){if(request===campaignRequest)notice(error.message,true);}
};
$('#new-campaign').onclick=openCreateDialog;$('#cancel-create').onclick=()=>{if(!busy)$('#create-dialog').close();};
$('#create-dialog').addEventListener('close',()=>{startPreviewRequest+=1;startCheckLoading=false;createDialogRequest+=1;resetHistoricalSetup();startingRequest+=1;startingOptions=null;reviewSelection=null;});$('#create-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});
$('#confirm-declaration-start').onchange=syncCreateControls;
$('#setup-next').onclick=wizardNext;$('#setup-back').onclick=()=>{if(busy||wizardStep===0)return;if(readLocal('irgs-create-pending')){$('#create-error').textContent='Check the retained Start request before changing its choices.';return;}wizardStep-=1;invalidateReview();$('#create-error').textContent='';syncCreateControls();};
$('#character-kind').onchange=updateCharacterFields;$('#starting-character').onchange=updateCharacterFields;$('#starting-scenario').onchange=()=>loadStartingOptions($('#starting-scenario').value);$('#starting-faction').onchange=updateFactionFields;$('#faction-representative').onchange=invalidateReview;
for(const id of ['new-character-name','new-character-species','new-character-background','campaign-name',...BACKGROUND_FIELDS]){$('#'+id).oninput=invalidateReview;$('#'+id).onchange=invalidateReview;}
$('#create-form').onsubmit=async event=>{
  event.preventDefault();if(busy||wizardStep!==3)return;let payload;
  try{payload=creationPayload();}catch(error){$('#create-error').textContent=error.message;return;}
  writeLocal('irgs-create-pending',payload);setBusy(true);$('#create-error').textContent='';
  try{const record=await api('create',payload,{creator:false});
    if(record.status==='trashed'){writeLocal('irgs-create-pending',null);$('#create-dialog').close();view='trash';render();notice('This Start request already created a campaign that is now in Trash. Restore it there.');return;}
    await refreshList(record.id);workspaceMode='player';featuresRequest+=1;features=[];drawFeatureNav();view='story';await loadFeatureNav({applyRoute:false});await openCampaign(record.id);updateViewRoute('story');writeLocal('irgs-create-pending',null);$('#create-dialog').close();notice(routineText('campaign.created'));
  }catch(error){notice(error.message,true);$('#create-error').textContent=error.message;
    if(error.status===400){writeLocal('irgs-create-pending',null);reviewSelection=null;wizardStep=2;$('#create-error').textContent=error.message+' Check your character details and review again. Your entries have been kept; use Back if you need to change the starting point.';}
    else if(reviewSelection){reviewSelection.recovery=true;renderReview(payload,true);}
  }finally{setBusy(false);}
};
$('#fork').onclick=async()=>{if(workspaceMode!=='creator'||!current||busy||loadingCampaign)return;const id=current.id;setBusy(true);try{const branch=await api('fork',{id});await refreshList(branch.id);await openCampaign(branch.id);notice(routineText('campaign.branched'));}catch(error){notice(error.message,true);}finally{setBusy(false);}};
$('#delete-campaign').onclick=()=>{if(!current||busy||loadingCampaign||$('#campaign').value!==current.id)return;deleteTarget={id:current.id,revision:current.revision,name:current.name,origin:current.state?.fork_origin?.save_id,request:campaignRequest};$('#delete-name').textContent=current.name;$('#delete-error').textContent='';$('#delete-dialog').showModal();};
$('#cancel-delete').onclick=()=>{if(!busy)$('#delete-dialog').close();};$('#delete-dialog').addEventListener('close',()=>{deleteTarget=null;});$('#delete-dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});
$('#delete-form').onsubmit=async event=>{event.preventDefault();if(!deleteTarget||busy)return;const target=deleteTarget;if(loadingCampaign||current?.id!==target.id||$('#campaign').value!==target.id||campaignRequest!==target.request){$('#delete-dialog').close();notice(routineText('campaign.changed'),true);return;}setBusy(true);try{await api('delete',{id:target.id,revision:target.revision});$('#delete-dialog').close();await openCampaign('');const campaigns=await refreshList(),next=campaigns.find(campaign=>campaign.id===target.origin)||campaigns[0];await openCampaign(next?.id||'');notice(routineText('campaign.trashed'));}catch(error){$('#delete-error').textContent=error.message;}finally{setBusy(false);}};
$('#export').onclick=()=>{if(!current||busy||loadingCampaign)return;const full=workspaceMode==='creator'&&current.mode==='creator'&&current.state,data=full||current,blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`IRGS-${full?'full-save':'known-view'}-${current.id}-r${current.revision}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
if(typeof addEventListener==='function')addEventListener('hashchange',applyCurrentRoute);
applyPreferences();syncControls();
(async()=>{try{const campaigns=await refreshList();await loadFeatureNav({applyRoute:false});const previous=localStorage.getItem('irgs-active'),id=campaigns.find(campaign=>campaign.id===previous)?.id||campaigns[0]?.id;if(id)await openCampaign(id);else{view='home';render();}applyCurrentRoute();}catch(error){notice('Cannot connect to the IRGS host: '+error.message,true);$('#content').innerHTML='<div class="empty">Start the local server and reload this page.</div>';}})();
