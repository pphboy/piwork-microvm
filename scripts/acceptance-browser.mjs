import {coreOrigin} from './acceptance-endpoints.mjs';
// Real browser against the running Guest. Never starts a host Core or mock UI.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const project=resolve(import.meta.dirname,'..');
const playwright=process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs';
const {chromium}=await import(pathToFileURL(playwright));
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||join(project,'dist/acceptance'));await mkdir(out,{recursive:true,mode:0o700});
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const credentialsPath=join(out,'credentials.json');
let credentials;
try{credentials=JSON.parse(await readFile(credentialsPath,'utf8'));}
catch{credentials={account:'microvm-admin',password:randomBytes(24).toString('hex')};await writeFile(credentialsPath,JSON.stringify(credentials),{mode:0o600});}
const syntheticKey='microvm-acceptance-synthetic-not-a-real-key';
// Optional private input for real-provider acceptance; never put its content in logs.
const realModel=process.env.PIWORK_REAL_MODEL_FILE?JSON.parse(await readFile(process.env.PIWORK_REAL_MODEL_FILE,'utf8')):null;
let stage='browser launch',browser,activePage;
const results={environment:process.env.PIWORK_ACCEPTANCE_PLATFORM||'real Linux KVM Guest',origin,realModelCall:realModel?'pending separate real-model acceptance':'not verified: no provider credential supplied',checks:[]};
function check(name){results.checks.push(name);console.log('PASS '+name);}
async function waitFor(fn,label,timeout=180000){const until=Date.now()+timeout;while(Date.now()<until){if(await fn())return;await new Promise(r=>setTimeout(r,500));}throw new Error('Timed out: '+label);}
try{
 browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const page=await context.newPage();activePage=page;page.setDefaultTimeout(30000);
 await waitFor(async()=>{try{return (await fetch(origin+'/healthz')).ok;}catch{return false;}},'Guest WebUI health',180000);
 stage='original first-time setup';
 const initial=await(await fetch(origin+'/_web/api/state')).json();
 if(!initial.administratorInitialized){
  await page.goto(origin);await page.getByRole('heading',{name:'Create your administrator'}).waitFor();
  await page.getByLabel('Account',{exact:true}).fill(credentials.account);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByLabel('Confirm password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Create administrator',exact:true}).click();
  await page.getByRole('heading',{name:'Sign in to Piwork'}).waitFor();
  check('First administrator created through unmodified upstream 0.0.9 UI');
 }else await page.goto(origin+'/login');
 stage='sign in';console.log('Stage: '+stage);
 await page.getByLabel('Account',{exact:true}).fill(credentials.account);
 await page.getByLabel('Password',{exact:true}).fill(credentials.password);
 const signedIn=page.waitForResponse(r=>new URL(r.url()).pathname==='/_web/api/login'&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 assert.equal((await signedIn).status(),200);
 await page.waitForURL(url=>url.pathname==='/admin/setup'||url.pathname==='/');
 stage='Quick setup';console.log('Stage: '+stage);
 await page.goto(origin+'/admin/setup');
 await page.locator('#model-form, #choose-form, #workbench-exit').first().waitFor();
 console.log('Quick setup form is available');
 if(await page.getByLabel('Model ID',{exact:true}).count()){
  await page.getByLabel('Model ID',{exact:true}).fill(realModel?.model||'gpt-4.1-mini');
  await page.getByLabel('API type',{exact:true}).selectOption(realModel?.api||'openai-responses');
  await page.getByLabel('Base URL',{exact:true}).fill(realModel?.baseUrl||'https://api.openai.com/v1');
  await page.getByLabel('API Key',{exact:true}).fill(realModel?.credential||syntheticKey);
  let tests=0;page.on('request',r=>{if(r.url().includes('/model-tests'))tests++;});
  await page.getByRole('button',{name:'Save and continue',exact:true}).click();
  await page.getByText('Your Runtime configuration is saved on this server.',{exact:true}).waitFor();
  console.log('Model and Runtime saved; waiting for real preparation');
  assert.equal(tests,0,'Saving must not implicitly call a model');
 }
 await waitFor(async()=>{const r=await fetch(origin+'/readyz?profile=docker-delivery');return r.status===200;},'actual runtime readiness',300000);
 check('Existing QuickStart saved configuration and all production runtime dependencies became Ready');
 await page.screenshot({path:join(out,'quickstart-ready.png'),fullPage:true});
 await page.goto(origin+'/');await page.getByRole('heading',{name:'Works',exact:true}).waitFor();
 const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
 assert.equal(login.status,200);const {token}=await login.json();
 async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const value=await r.json();assert.ok(r.ok,method+' '+path+' failed: '+r.status+' '+value.code);return value;}
 stage='create Work';
 const workName='MicroVM Acceptance Work';
 let work=(await api('/api/v1/works')).works.find(w=>w.name===workName);
 if(!work){
  await page.getByRole('button',{name:'New Work',exact:true}).first().click();await page.locator('#create-name').fill(workName);await page.getByRole('button',{name:'Create Work',exact:true}).click();
  await waitFor(async()=>{work=(await api('/api/v1/works')).works.find(w=>w.name===workName);return !!work;},'persisted Work');
 }
 results.workId=work.id;
 await waitFor(async()=>{work=await api('/api/v1/works/'+work.id);return work.observedState==='ready';},'real Agent ready',240000);
 check('Real production Agent Work created and ready');
 await page.goto(origin+'/');
 await page.getByRole('link',{name:/^MicroVM Acceptance Work/}).first().click();
 await page.screenshot({path:join(out,'work-ready.png'),fullPage:true});
 stage='Files';console.log('Stage: '+stage);
 const fileURL=coreOrigin+'/api/v1/works/'+work.id+'/files/note.txt';
 let old=await fetch(fileURL,{headers:{Authorization:'Bearer '+token}});
 if(old.status===404){const r=await fetch(fileURL,{method:'PUT',headers:{Authorization:'Bearer '+token},body:'microvm-original'});assert.ok([201,204].includes(r.status));}
 else assert.equal(old.status,200);
 await page.getByRole('button',{name:'Files',exact:true}).click();
 await page.locator('button[data-action="open-file"][data-path="/note.txt"]').click();
 const note='saved by real browser Files '+randomBytes(4).toString('hex');
 await page.getByLabel('Edit note.txt').fill(note);
 await page.getByRole('button',{name:'Save file',exact:true}).click();
 await page.getByText('File saved.',{exact:true}).waitFor();
 assert.equal(await(await fetch(fileURL,{headers:{Authorization:'Bearer '+token}})).text(),note);
 check('Real browser Files edit persisted in the Work volume');
 await page.getByRole('button',{name:'Back to files',exact:true}).click();
 const uploads=[{name:'中文资料.txt',mimeType:'text/plain',buffer:Buffer.from('真实浏览器上传；持久化到 ext4。\n')},{name:'二进制.bin',mimeType:'application/octet-stream',buffer:randomBytes(65536)}];
 for(const upload of uploads)await fetch(coreOrigin+'/api/v1/works/'+work.id+'/files/'+encodeURIComponent(upload.name),{method:'DELETE',headers:{Authorization:'Bearer '+token}});
 await page.locator('button[data-action="refresh-files"]').click();
 page.on('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'More file actions',exact:true}).click();
 const choosing=page.waitForEvent('filechooser');await page.getByRole('menuitem',{name:'Upload files',exact:true}).click();
 await(await choosing).setFiles(uploads);await page.getByText('Upload complete.',{exact:true}).waitFor();
 results.files=[];
 for(const upload of uploads){
  stage='download '+upload.name;
  let download;
  for(let attempt=1;attempt<=3;attempt++){
   await page.getByRole('button',{name:'Actions for '+upload.name,exact:true}).click();
   const pending=page.waitForEvent('download').catch(error=>({error}));await page.locator('button[data-action="download-file"]').click();
   download=await pending;if(download.error)throw download.error;
   const failure=await download.failure();
   if(!failure)break;
   (results.downloadRetries??=[]).push({name:upload.name,attempt,failure});
   if(failure!=='canceled'||attempt===3)throw new Error('Browser download failed: '+failure);
  }
  const bytes=await readFile(await download.path());assert.deepEqual(bytes,upload.buffer);
  results.files.push({name:upload.name,suggestedFilename:download.suggestedFilename(),sha256:createHash('sha256').update(bytes).digest('hex')});
  if(download.suggestedFilename()!==upload.name)console.log('NOTE browser suggested filename differs; exact downloaded bytes verified and original Files name retained');
  if(await page.getByRole('button',{name:'Close dialog',exact:true}).count())await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 }
 await page.locator('button[data-action="open-file"][data-path="/中文资料.txt"]').click();
 const modified='通过原版 Files 修改中文文件。\n';await page.getByLabel('Edit 中文资料.txt',{exact:true}).fill(modified);
 await page.getByRole('button',{name:'Save file',exact:true}).click();await page.getByText('File saved.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Back to files',exact:true}).click();
 results.files[0].sha256=createHash('sha256').update(modified).digest('hex');
 const deleted=await fetch(coreOrigin+'/api/v1/works/'+work.id+'/files/delete-me.txt',{method:'PUT',headers:{Authorization:'Bearer '+token},body:'delete test'});assert.ok(deleted.ok);
 await page.locator('button[data-action="refresh-files"]').click();
 await page.getByRole('button',{name:'Actions for delete-me.txt',exact:true}).click();await page.locator('button[data-action="file-delete"]').click();
 await page.getByRole('button',{name:'Delete paths',exact:true}).click();
 await waitFor(async()=>(await fetch(coreOrigin+'/api/v1/works/'+work.id+'/files/delete-me.txt',{headers:{Authorization:'Bearer '+token}})).status===404,'Files deletion');
 if(await page.getByRole('button',{name:'Close dialog',exact:true}).count())await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 assert.equal((await fetch(coreOrigin+'/api/v1/works/'+work.id+'/files/delete-me.txt',{headers:{Authorization:'Bearer '+token}})).status,404);
 check('Original Files UI uploaded/downloaded Chinese text and binary bytes, edited text and deleted a file');
 stage='deploy Service';console.log('Stage: '+stage);
 const image=JSON.parse(await readFile(join(project,'dist/piwork/images.json'),'utf8')).agent.reference;
 const script=await readFile(join(project,'fixtures/service.cjs'),'utf8');
 let service=(await api('/api/v1/works/'+work.id+'/services')).services.find(s=>s.name==='microvm-service');
 if(!service){
  const accepted=await api('/api/v1/works/'+work.id+'/services','POST',{definition:{name:'microvm-service',image:{reference:image},command:'node',args:['-e',script],workingDirectory:'/var/data/workspace',mounts:[{source:'workspace',target:'/var/data/workspace',readOnly:false}],ports:[{name:'web',protocol:'tcp',containerPort:8099}],readiness:{kind:'http',portName:'web',path:'/health',deadlineMs:10000}},idempotencyKey:'microvm-service-create'});
  await waitFor(async()=>{const op=await api('/api/v1/operations/'+accepted.operationId);if(op.state==='failed')throw new Error('Service operation failed');return op.state==='succeeded';},'Service deployment');
  service=(await api('/api/v1/works/'+work.id+'/services')).services.find(s=>s.name==='microvm-service');
 }
 results.serviceId=service.serviceId;
 await page.getByRole('button',{name:'Services',exact:true}).click();
 await page.frameLocator('iframe').getByRole('heading',{name:'Piwork MicroVM Service',exact:true}).waitFor({timeout:45000});
 const frame=page.frames().find(f=>{try{const u=new URL(f.url());return u.origin===origin&&u.pathname.startsWith('/services/');}catch{return false;}});
 assert.ok(frame);results.serviceOrigin=new URL(frame.url()).origin;results.serviceURL=frame.url();
 assert.equal(await frame.evaluate(()=>fetch('note').then(r=>r.text())),note);
 assert.equal(await frame.evaluate(()=>fetch('integrity').then(r=>r.text())),'ok');
 results.counterBefore=await frame.evaluate(()=>fetch('counter').then(r=>r.json()));
 try{
  const previous=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
  if(previous.serviceId===results.serviceId&&previous.counterAfter)assert.equal(results.counterBefore.value,previous.counterAfter.value,'Service counter survives the VM restart');
 }catch(error){if(error.code!=='ENOENT')throw error;}
 results.counterAfter=await frame.evaluate(()=>fetch('increment',{method:'POST'}).then(r=>r.json()));
 assert.equal(results.counterAfter.value,results.counterBefore.value+1);
 check('Host browser reached the authorized real Service; Files bytes and ext4 SQLite are shared and persistent');
 const anonymous=await fetch(new URL('counter',results.serviceURL));assert.ok([401,403].includes(anonymous.status));
 check('Anonymous Service access rejected');
 stage='Service WebSocket and SSE';
 const streaming=await frame.evaluate(async()=>{
  const websocket=await new Promise((resolve,reject)=>{const u=new URL('socket',location.href);u.protocol='ws:';const w=new WebSocket(u);const timer=setTimeout(()=>{w.close();reject(new Error('WebSocket timeout'));},10000);w.onopen=()=>w.send('microvm');w.onmessage=e=>{clearTimeout(timer);w.close();resolve(e.data)};w.onerror=()=>reject(new Error('WebSocket error'));});
  const events=await new Promise((resolve,reject)=>{const data=[],s=new EventSource('events');const timer=setTimeout(()=>{s.close();reject(new Error('SSE timeout'));},10000);s.onmessage=e=>{data.push(e.data);if(data.length===2){clearTimeout(timer);s.close();resolve(data)}};s.onerror=()=>{if(data.length<2){clearTimeout(timer);s.close();reject(new Error('SSE error'))}};});
  return {websocket,events};
 });
 assert.equal(streaming.websocket,'echo:microvm');assert.deepEqual(streaming.events,['microvm-first','microvm-second']);
 check('Real Service WebSocket round trip and SSE passed through QEMU forwarding');
 results.workNetwork=await frame.evaluate(()=>fetch('network').then(r=>r.json()));
 assert.equal(results.workNetwork.dns,true);assert.equal(results.workNetwork.https,200);assert.equal(results.workNetwork.aiApiReachable,true);
 check('Real Work network DNS/HTTPS and AI API reachability verified; no model invocation');
 await page.screenshot({path:join(out,'service-ready.png'),fullPage:true});
 await writeFile(join(out,'browser-result.json'),JSON.stringify(results,null,2)+'\n',{mode:0o600});
 console.log('Browser setup and Work acceptance completed.');
}catch(error){
 results.failedStage=stage;results.failure=String(error.message).replaceAll(credentials.password,'[redacted]').replaceAll(realModel?.credential||syntheticKey,'[redacted]').replaceAll(syntheticKey,'[redacted]').replace(/#setup=[\w-]+/g,'#setup=[redacted]');
 if(activePage){
  results.pagePath=new URL(activePage.url()).pathname;
  // Setup failures may leave a real credential in the DOM. Save only masked imagery.
  await activePage.locator('input').evaluateAll(inputs=>inputs.forEach(input=>{if(input.type==='password'||/key|credential|password/i.test(input.id+' '+input.name))input.value='';})).catch(()=>{});
  await activePage.screenshot({path:join(out,'failure.png'),fullPage:true}).catch(()=>{});
 }
 await writeFile(join(out,'browser-result.json'),JSON.stringify(results,null,2)+'\n',{mode:0o600});
 console.error('Browser acceptance failed at: '+stage);process.exitCode=1;
}finally{await browser?.close();}
