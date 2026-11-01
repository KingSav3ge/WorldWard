'use strict';
// Local authoring drafts are separate from Story and pending action/creation keys.
const creatorDraftKey='irgs-creator-preview-drafts-v1';
const creatorDraftSections=['workshop','campaign-builder','playtest-validation'];
let creatorRenderRequest=0,creatorPreviewRequest=0;
function creatorDraftActive(){
  return workspaceMode==='creator'&&creatorDraftSections.some(id=>view==='feature:'+id);
}
function creatorContextActive(context){
  return creatorDraftActive()&&context.render===creatorRenderRequest&&context.navigation===inspectorRequest&&context.section===view;
}
function creatorSavedDrafts(){
  const value=readLocal(creatorDraftKey,{});
  return value&&typeof value==='object'&&!Array.isArray(value)?value:{};
}
function clearCreatorPreview(context,message){
  if(!creatorContextActive(context))return;
  ++creatorPreviewRequest;
  $('#creator-preview-result').innerHTML='';
  $('#creator-preview-status').textContent=message;
  if($('#creator-preview-submit'))$('#creator-preview-submit').disabled=false;
}
function creatorProfileMarkup(profile){
  const source=profile.classification==='mixed'?'Mixed · historical setting with a fictional human and opening':'Fictional · authored demonstration, not historical calibration';
  return '<span class="badge">'+esc(source)+'</span><p>'+esc(profile.source_status)+'</p><p class="note">'+esc(profile.source_label||'Selected source unavailable')+'</p>'+(profile.classification==='mixed'?'<p class="note">The selected dated checkpoint does not establish a historical hour.</p>':'<p class="note">An offer is not consent or a transfer. Company and permission choices do not add supplies or expansion allowance.</p>');
}
function creatorFieldMarkup(field,retained){
  const id='creator-field-'+field.id;
  if(field.kind==='text')return '<label for="'+id+'">'+esc(field.label)+'<input id="'+id+'" data-creator-field="'+esc(field.id)+'" maxlength="'+field.max_length+'" required></label>';
  const known=(field.options||[]).some(item=>item.id===retained);
  return '<label for="'+id+'">'+esc(field.label)+'<select id="'+id+'" data-creator-field="'+esc(field.id)+'" '+(field.optional?'':'required')+'><option value="">'+(field.optional?'None selected':'Choose explicitly…')+'</option>'+(!known&&retained?'<option value="'+esc(retained)+'" disabled>Previous choice — currently unavailable</option>':'')+(field.options||[]).map(item=>'<option value="'+esc(item.id)+'">'+esc(item.label)+'</option>').join('')+'</select></label>';
}
function creatorFields(profile){
  return Object.fromEntries(profile.fields.map(field=>[field.id,$('#creator-field-'+field.id).value]));
}
function retainCreatorFields(profile){
  const saved=creatorSavedDrafts(),previous=saved[profile.id]||{};
  const draft={draft_id:previous.draft_id||'creator-'+crypto.randomUUID(),fields:creatorFields(profile)};
  writeLocal(creatorDraftKey,{...saved,selected_profile:profile.id,[profile.id]:draft});
  return draft;
}
function creatorDocument(profile,retained){
  const fields=retained.fields;
  for(const field of profile.fields){
    if(!field.optional&&!String(fields[field.id]||'').trim())throw Error('Choose '+field.label.toLowerCase()+'. Your draft is retained.');
    if(field.kind==='select'&&fields[field.id]&&!(field.options||[]).some(item=>item.id===fields[field.id]))throw Error('A retained choice is no longer available. Choose again; your words are retained.');
  }
  let choices;
  if(profile.id==='rise-r00'){
    choices={template_id:'R00',...fields};
    if(!choices.offer_profile)delete choices.offer_profile;
  }else{
    choices={snapshot_sha256:profile.snapshot_sha256,character:{kind:'new',name:fields.character_name,species:'human',opening_id:fields.opening_id}};
  }
  return {schema_version:'irgs-world-draft-1',draft_id:retained.draft_id,classification:profile.classification,profile_id:profile.id,choices};
}
function renderCreatorFields(context,options){
  if(!creatorContextActive(context))return;
  clearCreatorPreview(context,'Preview only — no campaign saved.');
  const id=$('#creator-profile').value,profile=options.profiles.find(item=>item.id===id&&item.available);
  if(!profile){$('#creator-fields').innerHTML='<p class="note">Choose a supported profile to begin a separate draft.</p>';return;}
  const saved=creatorSavedDrafts(),retained=saved[id]?.fields||{};
  writeLocal(creatorDraftKey,{...saved,selected_profile:id});
  $('#creator-fields').innerHTML=creatorProfileMarkup(profile)+'<form id="creator-preview-form"><div class="setup-fields">'+profile.fields.map(field=>creatorFieldMarkup(field,retained[field.id]||'')).join('')+'</div><p class="note">Draft text stays in this browser. Previewing does not save a campaign or change your current Story.</p><div class="buttons"><button id="creator-preview-submit" class="primary" type="submit">Review initial view</button><button id="creator-preview-cancel" class="quiet" type="button">Cancel preview</button></div></form>';
  for(const field of profile.fields){
    const element=$('#creator-field-'+field.id);element.value=retained[field.id]||'';
    const edit=()=>{if(!creatorContextActive(context))return;retainCreatorFields(profile);clearCreatorPreview(context,'Draft changed. Review again to preview these exact choices.');};
    element.oninput=edit;element.onchange=edit;
  }
  $('#creator-preview-cancel').onclick=()=>{if(!creatorContextActive(context))return;retainCreatorFields(profile);clearCreatorPreview(context,'Preview cancelled. Draft retained. No campaign saved.');};
  $('#creator-preview-form').onsubmit=event=>{event.preventDefault();return previewCreatorDraft(context,options,profile);};
}
async function renderCreatorDraftPreview(){
  if(!creatorDraftActive())return;
  const context={render:++creatorRenderRequest,navigation:inspectorRequest,section:view};
  ++creatorPreviewRequest;
  $('#content').innerHTML='<section class="panel"><span class="eyebrow">CREATOR · PREVIEW ONLY</span><h2>A world before its first chapter.</h2><p>Choose a supported starting profile and review what its character initially receives. No campaign is saved.</p><p id="creator-options-status" role="status">Loading selected profile sources…</p><div id="creator-editor"></div></section>';
  try{
    const options=await api('creator/drafts/options');
    if(!creatorContextActive(context))return;
    if(options.schema_version!=='irgs-creator-preview-options-1'||options.draft_schema!=='irgs-world-draft-1'||!Array.isArray(options.profiles)||!options.options_digest)throw Error('The host returned incompatible profile choices.');
    $('#creator-options-status').textContent='Only the selected Engine’s bounded profiles are available. Durable playtest creation remains unavailable.';
    $('#creator-editor').innerHTML='<label for="creator-profile">Starting profile<select id="creator-profile"><option value="">Choose a profile…</option>'+options.profiles.map(profile=>'<option value="'+esc(profile.id)+'" '+(profile.available?'':'disabled')+'>'+esc(profile.title)+(profile.available?'':' · source unavailable')+'</option>').join('')+'</select></label><div id="creator-fields"></div><p id="creator-preview-status" role="status" aria-live="polite"></p><div id="creator-preview-result"></div><button id="creator-refresh-options" class="quiet" type="button">Refresh profile sources</button>';
    const selected=creatorSavedDrafts().selected_profile;
    $('#creator-profile').value=options.profiles.some(p=>p.id===selected&&p.available)?selected:'';
    $('#creator-profile').onchange=()=>renderCreatorFields(context,options);
    $('#creator-refresh-options').onclick=()=>renderCreatorDraftPreview();
    renderCreatorFields(context,options);
  }catch(error){
    if(!creatorContextActive(context))return;
    $('#creator-options-status').textContent='Preview choices unavailable: '+error.message;
    $('#creator-editor').innerHTML='<button id="creator-options-retry" class="quiet" type="button">Retry profile sources</button>';
    $('#creator-options-retry').onclick=()=>renderCreatorDraftPreview();
  }
}
function creatorReceivedText(record){
  try{
    const value=JSON.parse(record.text);
    if(value&&typeof value==='object'){
      if(value.kind==='initial_civil_date')return 'Received initial civil day: '+value.date+' ('+value.calendar+', '+value.precision+' precision). '+(value.time==null?'The historical hour is not established.':'Recorded time: '+value.time+'.');
      return 'A structured received record is available in the advanced details.';
    }
  }catch{}
  return String(record.text??'');
}
function renderCreatorActorPreview(result,draft,profile){
  const actor=result.actor_view,received=actor.received?.records||[],capabilities=actor.capabilities||[];
  return '<section class="panel"><span class="eyebrow">DISPOSABLE INITIAL VIEW</span><h3>What this character initially knows</h3>'+creatorProfileMarkup(profile)+received.map(record=>'<article class="record-card"><span class="badge">'+esc(label(record.status))+'</span><p class="entry-text">'+esc(creatorReceivedText(record))+'</p><small>Received source: '+esc(record.source_ref||'Not established')+'</small></article>').join('')+(received.length?'':'<p class="note">No received records are established in this preview.</p>')+'<h3>Supported intentions</h3><p class="note">These are supported attempts, not guaranteed outcomes. Preview controls submit no gameplay.</p><ul>'+capabilities.map(cap=>'<li>'+esc(cap.title)+'</li>').join('')+'</ul><details id="creator-preview-advanced"><summary>Advanced: exact choices and received records</summary><p class="note">These are the reviewed authoring choices and received records, not a full save. Preview identities cannot authorize gameplay or creation.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify({draft,actor_id:actor.actor_id,received,review_digest:result.review_digest},null,2))+'</pre></details></section>';
}
async function previewCreatorDraft(context,options,profile){
  if(!creatorContextActive(context))return;
  clearCreatorPreview(context,'Reviewing the selected initial view…');
  const request=creatorPreviewRequest,retained=retainCreatorFields(profile);
  const active=()=>creatorContextActive(context)&&request===creatorPreviewRequest&&$('#creator-profile').value===profile.id&&JSON.stringify(creatorFields(profile))===JSON.stringify(retained.fields);
  $('#creator-preview-submit').disabled=true;
  try{
    const draft=creatorDocument(profile,retained);
    const result=await api('creator/drafts/preview',{draft,options_digest:options.options_digest});
    if(!active())return;
    if(result.schema_version!=='irgs-world-initialization-preview-1'||result.status!=='preview_only'||result.committed!==false||result.preview_identities_reusable!==false||result.requires_explicit_acceptance!==true||result.draft_id!==draft.draft_id||result.profile_id!==draft.profile_id||!result.actor_view?.actor_id||Object.prototype.hasOwnProperty.call(result,'state'))throw Error('The host returned an incompatible preview.');
    $('#creator-preview-result').innerHTML=renderCreatorActorPreview(result,draft,profile);
    $('#creator-preview-status').textContent='Preview only — no campaign saved. Editing or cancelling discards this view.';
  }catch(error){
    if(active())$('#creator-preview-status').textContent=error.message;
  }finally{
    if(active())$('#creator-preview-submit').disabled=false;
  }
}
