// Focused official-input acceptance. Run only against a dedicated test installation.
// Private credentials and downloaded ZIPs stay outside the repository evidence.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT);
const origin=process.env.PIWORK_UI_ORIGIN||'http://127.0.0.1:17891';
const core=process.env.PIWORK_CORE_ORIGIN||'http://127.0.0.1:17871';
const verify=process.argv.includes('--verify');
const credentials=JSON.parse(await readFile(process.env.PIWORK_LOG_CREDENTIALS||join(out,'credentials.json')));
const previous=verify?JSON.parse(await readFile(join(out,'session-baseline.json'))):null;
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const hash=b=>createHash('sha256').update(b).digest('hex');
const wait=async(fn,label,ms=180000)=>{for(const end=Date.now()+ms;Date.now()<end;){if(await fn())return;await new Promise(r=>setTimeout(r,500));}throw Error('timeout '+label)};
const browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--no-proxy-server']});
try{
 console.log('Stage: wait for Guest readiness');
 await wait(async()=>{try{return (await fetch(origin+'/readyz?profile=docker-delivery')).ok}catch{return false}},'Guest ready',600000);
 console.log('Stage: API login');
 const login=await fetch(core+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
 assert.equal(login.status,200);const identity=await login.json();const headers={Authorization:'Bearer '+identity.token};
 const api=async(path,method='GET',body)=>{const r=await fetch(core+'/api/v1/'+path,{method,headers:{...headers,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const v=await r.json();assert.ok(r.ok,`${method} ${path}: ${r.status} ${v.code}`);return v;};
 const works=(await api('works')).works;
 const work=works.find(w=>w.id===(previous?.workId||process.env.PIWORK_ACCEPTANCE_WORK_ID))||works.find(w=>w.name==='MicroVM Acceptance Work');assert.ok(work,'existing test Work');
 const base='works/'+work.id;
 if((await api(base)).observedState!=='ready')await api(base+'/start','POST',{idempotencyKey:'official-reopen-'+Date.now()});
 await wait(async()=>['ready','degraded'].includes((await api(base)).observedState),'production Work ready');
 let service;await wait(async()=>{service=(await api(base+'/services')).services.find(s=>s.serviceId===(previous?.serviceId||process.env.PIWORK_ACCEPTANCE_SERVICE_ID))|| (await api(base+'/services')).services.find(s=>s.name==='microvm-service');return service&&service.observedState==='ready';},'persisted Service ready');
 console.log('Stage: Files identity');
 const record={platform:process.env.PIWORK_ACCEPTANCE_PLATFORM,realModelCall:false,userId:identity.user.id,workId:work.id,serviceId:service.serviceId,serviceRevision:service.desiredRevision,files:[]};
 for(const name of (previous?.files.map(f=>f.name)||['note.txt','中文资料.txt','二进制.bin'])){
  let bytes;await wait(async()=>{try{const r=await fetch(core+'/api/v1/'+base+'/files/'+encodeURIComponent(name),{headers});if(!r.ok)return false;bytes=Buffer.from(await r.arrayBuffer());return true;}catch(error){if(error instanceof TypeError)return false;throw error;}},'File helper '+name);
  record.files.push({name,sha256:hash(bytes)});
 }
 console.log('Stage: browser login');
 const context=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:1000}});const page=await context.newPage();page.setDefaultTimeout(120000);
 await page.goto(origin+'/login');await page.getByLabel('Account',{exact:true}).fill(credentials.account);await page.getByLabel('Password',{exact:true}).fill(credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.locator('.works-page').waitFor();
 console.log('Stage: browser Files and Service');
 await page.goto(origin+'/#/work/'+work.id);await page.getByRole('button',{name:'Files',exact:true}).click();
 await page.locator('button[data-action="open-file"][data-path="/note.txt"]').click();await page.getByLabel('Edit note.txt').waitFor();
 await page.getByRole('button',{name:'Services',exact:true}).click();
 await page.locator('button[data-action="service-picker"]').click();await page.locator('button[data-action="select-service"][data-id="'+service.serviceId+'"]').click();
 const locator=page.locator('iframe[title="microvm-service application"]');await page.frameLocator('iframe[title="microvm-service application"]').getByRole('heading',{name:'Piwork MicroVM Service',exact:true}).waitFor();
 const frame=await(await locator.elementHandle()).contentFrame();
 record.counter=await frame.evaluate(()=>fetch('counter').then(r=>r.json()));assert.equal(await frame.evaluate(()=>fetch('integrity').then(r=>r.text())),'ok');
 await page.screenshot({path:join(out,verify?'session-reopened.png':'session-baseline.png'),fullPage:true});
 if(process.env.PIWORK_EXPECTED_OLD_DATA){
  const old=JSON.parse(await readFile(process.env.PIWORK_EXPECTED_OLD_DATA));
  assert.equal(record.workId,old.workId);assert.equal(record.serviceId,old.serviceId);assert.deepEqual(record.counter,old.counterAfter);
  for(const file of old.files)assert.equal(record.files.find(f=>f.name===file.name)?.sha256,file.sha256,'original File '+file.name);
  record.originalDataMatched=true;
 }
 if(verify){for(const field of ['userId','workId','serviceId','serviceRevision','files','counter'])assert.deepEqual(record[field],previous[field],field+' retained');}
 if(!verify||process.env.PIWORK_EXPORT_ON_REOPEN==='1'){
  console.log('Stage: administrator ZIP');
  await page.goto(origin+'/');await page.locator('.works-page').waitFor();
  await page.locator('[data-action=account]').click();const menu=page.getByRole('menuitem',{name:'Export logs',exact:true});const downloading=page.waitForEvent('download');await menu.click();const download=await downloading;
  const dir=resolve(out,'../downloads');await mkdir(dir,{recursive:true});const target=join(dir,download.suggestedFilename());await download.saveAs(target);const bytes=await readFile(target);
  // Python zipfile works on both native Windows and Linux; no Guest boot is used to read it.
  const python=process.env.PIWORK_PYTHON||'python3';const script="import json,zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; m=json.loads(z.read('manifest.json')); assert m['core']['files']; print(json.dumps({'coreFiles':len(m['core']['files']),'complete':m['complete'],'sources':len(m['sources'])}))";
  record.export={filename:download.suggestedFilename(),size:bytes.length,sha256:hash(bytes),...JSON.parse(execFileSync(python,['-c',script,target],{encoding:'utf8'}))};
 }
 await writeFile(join(out,verify?'session-reopened.json':'session-baseline.json'),JSON.stringify(record,null,2)+'\n',{mode:0o600});console.log('PASS existing account, Work, Files, production Service, SQLite'+(verify?' retained after reopening':' and downloaded administrator ZIP'));
}finally{await browser.close();}
