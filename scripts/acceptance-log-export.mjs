// Focused acceptance against a GUI-started real Guest; no model calls or mock UI.
// CDP attaches only to the owned acceptance browser. Downloads stay on its Host.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const origin=process.env.PIWORK_UI_ORIGIN||'http://127.0.0.1:17891';
const core=process.env.PIWORK_CORE_ORIGIN||'http://127.0.0.1:17871';
const root=resolve(process.env.PIWORK_LOG_ACCEPT_ROOT||'/home/p/piwork-log-export-upgrade');
const label=process.env.PIWORK_LOG_PLATFORM||'linux';
const out=join(root,'evidence');await mkdir(out,{recursive:true});
const creds=JSON.parse(await readFile(process.env.PIWORK_LOG_CREDENTIALS||'/home/p/piwork-gui-complete/business/credentials.json'));
const old=JSON.parse(await readFile(join(out,label+'-old-data.json')));
const nativeDir=process.env.PIWORK_NATIVE_DOWNLOAD_DIR||join(root,'downloads');
const mappedDir=process.env.PIWORK_MAPPED_DOWNLOAD_DIR||nativeDir;
const browser=await chromium.connectOverCDP(process.env.PIWORK_BROWSER_CDP||'http://127.0.0.1:19222');
// A new tab makes a new export intent after restart; the original tab restores
// its previous export for Download again (upstream sessionStorage behavior).
const context=browser.contexts()[0], page=process.env.PIWORK_LOG_GAP_ONLY==='1'?await context.newPage():context.pages().find(p=>p.url().startsWith(origin))||await context.newPage();
const cdp=await browser.newBrowserCDPSession();await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:nativeDir,eventsEnabled:true});
page.setDefaultTimeout(30000);
const wait=async(fn,label,ms=180000)=>{const end=Date.now()+ms;while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,250));}throw Error('timeout '+label)};
const sha=b=>createHash('sha256').update(b).digest('hex');
const result={platform:label,origin,core,realModelCall:'not attempted; controlled Service only',workId:old.workId,files:[],exports:[],desktopRequests:[]};
page.on('response',r=>{const u=new URL(r.url());if(u.origin===origin&&u.pathname.startsWith('/_desktop/api/'))result.desktopRequests.push({path:u.pathname,status:r.status()});});
try{
 await page.goto(origin+'/login');
 await Promise.race([page.getByLabel('Account',{exact:true}).waitFor(),page.getByRole('heading',{name:'Works',exact:true}).waitFor()]);
 if(await page.getByLabel('Account',{exact:true}).isVisible()){await page.getByLabel('Account',{exact:true}).fill(creds.account);await page.getByLabel('Password',{exact:true}).fill(creds.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();}
 await page.getByRole('heading',{name:'Works',exact:true}).waitFor();assert.equal(await page.evaluate(()=>location.origin),origin);
 const login=await fetch(core+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(creds)});assert.equal(login.status,200);const {token}=await login.json();
 async function api(path,method='GET',body){const r=await fetch(core+'/api/v1/'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const value=await r.json();assert.ok(r.ok,method+' '+path+' '+r.status+' '+value.code);return value;}
 const work=await api('works/'+old.workId);assert.equal(work.id,old.workId);
 if(process.env.PIWORK_LOG_GAP_ONLY!=='1'&&process.env.PIWORK_LOG_ENDPOINT_ONLY!=='1'){
 if(!['ready','degraded'].includes(work.observedState)){await api('works/'+old.workId+'/start','POST',{idempotencyKey:'log-upgrade-start-'+label+'-'+randomUUID()});await wait(async()=> ['ready','degraded'].includes((await api('works/'+old.workId)).observedState),'old Work runtime');}
 result.observedState=(await api('works/'+old.workId)).observedState;
 if(result.observedState==='degraded'){const prior=JSON.parse(await readFile(join(out,label+'-result.json')));const controlled=await api('works/'+old.workId+'/services/'+prior.serviceId);assert.equal(controlled.observedState,'failed');result.expectedFailedService=prior.serviceId;}
 for(const file of old.files){const r=await fetch(core+'/api/v1/works/'+old.workId+'/files/'+encodeURIComponent(file.name),{headers:{Authorization:'Bearer '+token}});assert.equal(r.status,200);const bytes=Buffer.from(await r.arrayBuffer());assert.equal(sha(bytes),file.sha256);result.files.push({name:file.name,sha256:sha(bytes)});}
 console.log('PASS original login, Work and file hashes');
 }
 if(process.env.PIWORK_LOG_RECOVERY==='1'||process.env.PIWORK_LOG_ENDPOINT_ONLY==='1'){
  await page.getByText(old.workId,{exact:true}).waitFor();
  await page.screenshot({path:join(out,label+'-recovered-desktop.png')});
  await writeFile(join(out,label+'-recovery.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});
 } else {
  const meta=JSON.parse(await readFile(resolve('dist/piwork/metadata.json')));
  const script="for(let i=0;i<250;i++)console.log('UPGRADE-FAULT-'+String(i).padStart(3,'0'));console.error('CONTROLLED_UPGRADE_FAILURE');console.log('API_KEY=synthetic-upgrade-secret');process.exit(17)";
  const definition={name:'upgrade-log-failure',image:{reference:meta.images.agent},command:'node',args:['-e',script],workingDirectory:'/',environment:{API_KEY:'synthetic-upgrade-secret'},ports:[{name:'web',protocol:'tcp',containerPort:8099}],readiness:{kind:'http',portName:'web',path:'/',deadlineMs:5000}};
  let failed;
  if(process.env.PIWORK_LOG_GAP_ONLY==='1'){failed={serviceId:JSON.parse(await readFile(join(out,label+'-result.json'))).serviceId};}
  else {
  failed=await api('works/'+old.workId+'/services','POST',{definition,idempotencyKey:'upgrade-fault-'+label});
  await wait(async()=> (await api('operations/'+failed.operationId)).state==='failed','controlled Service failure');
  const restarted=await api('works/'+old.workId+'/services/'+failed.serviceId+'/restart','POST',{idempotencyKey:'upgrade-fault-restart-'+label});
  await wait(async()=> (await api('operations/'+restarted.operationId)).state==='failed','archive original failed instance');
  }
  result.serviceId=failed.serviceId;
  async function exportZIP(tag){
   await page.locator('[data-action=account]').click();const menu=page.getByRole('menuitem',{name:'Export logs',exact:true});assert.equal(await menu.count(),1);
   const downloading=page.waitForEvent('download',{timeout:120000});await menu.click();const download=await downloading;
   const target=join(mappedDir,download.suggestedFilename());await wait(async()=>{try{const st=await stat(target);return st.size>0}catch{return false}},'native saved ZIP');
   await wait(async()=>{try{execFileSync('unzip',['-t',target],{stdio:'ignore'});return true}catch{return false}},'complete ZIP');
   const manifest=JSON.parse(execFileSync('unzip',['-p',target,'manifest.json'],{encoding:'utf8'}));
   assert.ok(manifest.core.files.length,'Core logs missing');
   assert.doesNotMatch(execFileSync('unzip',['-p',target],{encoding:'utf8'}),/synthetic-upgrade-secret/);
   if(tag==='gap')await page.getByText(/gap\(s\) recorded/).waitFor();
   const sources=manifest.sources.filter(s=>s.serviceId===failed.serviceId);assert.ok(sources.length,'fault Service source missing');
   let stdout='',stderr='';for(const source of sources)for(const entry of source.entries||[]){const value=execFileSync('unzip',['-p',target,entry],{encoding:'utf8'});if(entry.endsWith('/stdout.log'))stdout+=value;if(entry.endsWith('/stderr.log'))stderr+=value;}
   assert.match(stdout,/UPGRADE-FAULT-000/);assert.match(stdout,/UPGRADE-FAULT-249/);assert.match(stderr,/CONTROLLED_UPGRADE_FAILURE/);assert.doesNotMatch(stdout,/synthetic-upgrade-secret/);
   const record={tag,filename:download.suggestedFilename(),bytes:(await stat(target)).size,sha256:sha(await readFile(target)),exportId:manifest.exportId,complete:manifest.complete,sources:sources.map(s=>({sourceId:s.sourceId,state:s.state,reason:s.reason})),coreFiles:manifest.core.files.length};
   result.exports.push(record);await page.screenshot({path:join(out,label+'-'+tag+'-export.png')});await writeFile(join(out,label+'-'+tag+'-manifest.json'),JSON.stringify(manifest,null,2)+'\n',{mode:0o600});
   console.log('PASS real browser ZIP',JSON.stringify(record));await page.getByRole('button',{name:'Close',exact:true}).click();return manifest;
  }
  if(process.env.PIWORK_LOG_GAP_ONLY==='1'){
   const partial=await exportZIP('gap');assert.equal(partial.complete,false);assert.ok(partial.sources.some(s=>s.serviceId===failed.serviceId&&['partial','unavailable'].includes(s.state)));
  } else {
   const full=await exportZIP('fault');
   await writeFile(join(out,label+'-gap-request.json'),JSON.stringify({workId:old.workId,serviceId:failed.serviceId,sources:full.sources.filter(s=>s.serviceId===failed.serviceId).map(s=>s.sourceId)}),{mode:0o600});
   if(process.env.PIWORK_LOG_DEFER_GAP!=='1'){
    await wait(async()=>{try{return(await stat(join(out,label+'-gap-ready'))).isFile()}catch{return false}},'owned source gap preparation');
    const partial=await exportZIP('gap');assert.equal(partial.complete,false);assert.ok(partial.sources.some(s=>s.serviceId===failed.serviceId&&['partial','unavailable'].includes(s.state)));
   }
  }
  await writeFile(join(out,label+(process.env.PIWORK_LOG_GAP_ONLY==='1'?'-gap-result.json':'-result.json')),JSON.stringify(result,null,2)+'\n',{mode:0o600});
 }
} finally {await browser.close();}
