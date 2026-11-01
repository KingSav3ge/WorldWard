'use strict';
// Real ordinary Rise creation/actions against a fresh synthetic local store.
// No Creator edits, remote source, user saves, live AI or gameplay-rule changes.
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict');
const {spawn,execFileSync}=require('child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const baselineCommit=process.argv[3]==='--baseline'?'7327290fbb057ad320cfeb3a009e4138944b078c':null;
const baselineScript=baselineCommit?execFileSync('git',['show',baselineCommit+':IRGS_Web/static/app.js'],{cwd:root}):null;
const reportPath=process.argv[2]?path.resolve(process.argv[2]):null;
if(reportPath&&reportPath.startsWith(root+path.sep))throw Error('Keep qualification evidence outside source');
if(reportPath)fs.mkdirSync(path.dirname(reportPath),{recursive:true});
const folder=fs.mkdtempSync(path.join(reportPath?path.dirname(reportPath):os.tmpdir(),'saves-journey-'));
const metadata=path.join(folder,'host.json');
const hostCode=[
'import json,sys','from pathlib import Path',
"sys.path.insert(0,str(Path(sys.argv[1])/'IRGS_Web'))",
'from server import make_server',
"folder=Path(sys.argv[2]);server=make_server(0,folder/'saves')",
"(folder/'host.json').write_text(json.dumps({'port':server.server_port}))",
'try: server.serve_forever()','except KeyboardInterrupt: pass','finally: server.server_close()'
].join('\n');
(async()=>{
 const child=spawn('python3',['-B','-c',hostCode,root,folder],{stdio:['ignore','ignore','pipe']});
 let stderr='',browser,page,report={status:'running',baseline_app_asset_commit:baselineCommit,fixture_directory:folder,live_provider_calls:0,browser_errors:[],checks:[]};
 child.stderr.on('data',data=>stderr+=data);
 try{
  const deadline=Date.now()+20000;
  while(!fs.existsSync(metadata)){
   if(child.exitCode!==null||Date.now()>deadline)throw Error('Synthetic host did not start: '+stderr);
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  const origin='http://127.0.0.1:'+JSON.parse(fs.readFileSync(metadata)).port;
  browser=await chromium.launch({executablePath:process.env.IRGS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  page=await browser.newPage({viewport:{width:1360,height:1000}});const posts=[],external=[];
  page.on('pageerror',error=>report.browser_errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST')posts.push(request.url());});
  await page.route('**/*',route=>{
   const url=route.request().url();
   if(!url.startsWith(origin+'/')){external.push(url);return route.abort();}
   if(baselineScript&&url===origin+'/app.js')return route.fulfill({status:200,contentType:'application/javascript',body:baselineScript});
   if(/\/api\/ai\//.test(url)){report.live_provider_calls++;return route.abort();}
   return route.continue();
  });
  report.phase='boot';await page.goto(origin);await page.waitForFunction(()=>token&&features.length);
  await page.locator('[data-view="content-library"]').first().click();await page.waitForSelector('.catalogue-card');
  await page.locator('#catalogue-current-starts > summary').click();await page.locator('[data-rise-setup]').click();
  await page.locator('#rise-form').waitFor();
  for(const [key,value]of Object.entries({name:'Saves summary regression',founder_name:'Avery',household_name:'Avery household',settlement_name:'Test clearing'})){
   await page.locator('#rise-form [name="'+key+'"]').fill(value);
  }
  await page.locator('#rise-form [name="permission"]').selectOption('held');
  await page.locator('#rise-form button[type="submit"]').click();await page.locator('#rise-confirm').check();
  report.phase='create';await page.locator('#rise-create').click();
  await page.waitForFunction(()=>current?.name==='Saves summary regression'&&!busy&&!loadingCampaign);
  report.phase='actions';const id=await page.evaluate(()=>current.id);
  const recordPath=path.join(folder,'saves',id+'.json');
  const saved=()=>fs.readFileSync(recordPath,'utf8');
  const revision=()=>JSON.parse(saved()).revision;
  await page.locator('#declaration').fill('Keep this independent draft');
  for(let index=0;index<2;index++){
   const before=await page.evaluate(()=>current.revision);
   await page.locator('[data-rise-action="inspect"]').click();
   await page.locator('#action-review-dialog[open]').waitFor();
   await page.locator('#confirm-reviewed-action').click();
   await page.waitForFunction(value=>current?.revision>value&&!busy&&!loadingCampaign,before);
  }
  report.authoritative_revision=revision();
  assert(report.authoritative_revision>0);
  const beforeNavigation=saved(),postCount=posts.length;
  await page.locator('[data-view="saves"]').first().click();
  const card=page.locator('.journey-card').filter({has:page.locator('[data-resume-campaign="'+id+'"]')});
  report.saved_card_text=await card.innerText();
  if(reportPath)await page.screenshot({path:reportPath.replace(/\.json$/,'.png')});
  assert(report.saved_card_text.includes('revision '+report.authoritative_revision),'Saves card must show the current durable revision without reloading');
  assert.equal(saved(),beforeNavigation);assert.equal(posts.length,postCount);
  report.checks.push('Two normal committed actions update the Saves card without reload or extra writes');
  await card.locator('[data-resume-campaign]').click();
  await page.waitForFunction(id=>current?.id===id&&view==='story'&&!loadingCampaign,id);
  assert.equal(await page.locator('#declaration').inputValue(),'Keep this independent draft');
  await page.locator('[data-view="saves"]').first().click();
  assert((await page.locator('.journey-card').innerText()).includes('revision '+revision()));
  assert.equal(saved(),beforeNavigation);assert.equal(posts.length,postCount);
  report.checks.push('Repeated Saves/Continue navigation preserves the draft and exact saved bytes');
  await page.reload();await page.waitForFunction(id=>current?.id===id&&!loadingCampaign,id);
  await page.locator('[data-view="saves"]').first().click();
  assert((await page.locator('.journey-card').innerText()).includes('revision '+revision()));
  assert.equal(saved(),beforeNavigation);assert.equal(posts.length,postCount);
  report.checks.push('Reload retains the same current card revision without changing the saved world');
  assert.deepEqual(external,[]);assert.deepEqual(report.browser_errors,[]);assert.equal(report.live_provider_calls,0);
  report.status='passed';
 }catch(error){
  report.status='failed';report.error=String(error);if(page)report.ui_state=await page.evaluate(()=>({current:typeof current==='undefined'?null:current&&{id:current.id,name:current.name,revision:current.revision},busy,loadingCampaign,view,notice:document.querySelector('#notice')?.textContent})).catch(()=>null);process.exitCode=1;
 }finally{
  if(browser)await browser.close();
  if(child.exitCode===null){child.kill('SIGINT');await new Promise(resolve=>child.once('exit',resolve));}
  fs.writeFileSync(path.join(folder,'host.log'),stderr);
  if(reportPath)fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
