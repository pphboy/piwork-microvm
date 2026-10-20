import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const project=resolve(import.meta.dirname,'..'),out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||join(project,'dist/acceptance'));
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const state=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
const image=JSON.parse(await readFile(join(project,'dist/piwork/images.json'),'utf8')).agent.reference;
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});assert.equal(login.status,200);const {token}=await login.json();const auth={Authorization:'Bearer '+token};
async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{...auth,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const x=await r.json();assert.ok(r.ok,method+' '+path+' '+r.status+' '+x.code+' '+(x.field||''));return x;}
async function wait(id){const until=Date.now()+300000;while(Date.now()<until){const op=await api('/api/v1/operations/'+id);if(op.state==='succeeded')return op;assert.ok(!['failed','superseded'].includes(op.state),'operation '+op.state+' '+(op.error?.code||''));await new Promise(r=>setTimeout(r,400));}throw new Error('operation timeout');}
const path='/api/v1/works/'+state.workId;
const suffix=process.env.PIWORK_ACCEPTANCE_TAG||'';
const key=x=>x+suffix;
if((await api(path)).observedState!=='ready'){const op=await api(path+'/start','POST',{idempotencyKey:key('snapshot-source-start')});await wait(op.operationId);}
for(const s of (await api(path+'/services')).services.filter(s=>s.name.startsWith('probe-'))){const op=await api(path+'/services/'+s.serviceId+'/remove','POST',{idempotencyKey:'remove-grant-'+s.serviceId});await wait(op.operationId);}
let service=await api(path+'/services/'+state.serviceId);
const fixture=await readFile(join(project,'fixtures/service.cjs'),'utf8');
if(service.definition.args[1]!==fixture){const updated=await api(path+'/services/'+state.serviceId,'PUT',{expectedRevision:service.desiredRevision,definition:{name:'microvm-service',image:{reference:service.definition.image.reference},command:'node',args:['-e',fixture],workingDirectory:'/var/data/workspace',mounts:[{source:'workspace',target:'/var/data/workspace',readOnly:false}],ports:[{name:'web',protocol:'tcp',containerPort:8099}],readiness:{kind:'http',portName:'web',path:'/health',deadlineMs:10000}},idempotencyKey:key('cookie-service-definition')});await wait(updated.operationId);service=await api(path+'/services/'+state.serviceId);}
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
try{
 const context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(30000);
 await page.goto(origin+'/login');await page.getByLabel('Account',{exact:true}).fill(credentials.account);await page.getByLabel('Password',{exact:true}).fill(credentials.password);
 const signed=page.waitForResponse(r=>new URL(r.url()).pathname==='/_web/api/login'&&r.request().method()==='POST');await page.getByRole('button',{name:'Sign in',exact:true}).click();assert.equal((await signed).status(),200);await page.waitForURL(u=>u.pathname==='/admin/setup'||u.pathname==='/');
 await page.goto(origin+'/#/work/'+state.workId);await page.getByRole('button',{name:'Services',exact:true}).click();await page.frameLocator('iframe').getByRole('heading',{name:'Piwork MicroVM Service',exact:true}).waitFor();
 const frame=page.frames().find(f=>{try{const u=new URL(f.url());return u.origin===origin&&u.pathname.startsWith('/services/')}catch{return false}});assert.ok(frame);
 const cookie=await frame.evaluate(()=>fetch('cookie').then(r=>r.text()));assert.ok(cookie.includes('demo=isolated')&&!cookie.includes('piwork'),'application Cookie round trip without platform credential');
 assert.equal(new URL(frame.url()).origin,origin,'Service uses the original ControlPlane origin');
 const wsEvent=page.waitForEvent('websocket');await frame.evaluate(()=>{window.keepalive=new WebSocket('ws://'+location.host+location.pathname+'socket')});const socket=await wsEvent;const closed=new Promise(resolve=>socket.on('close',resolve));
 const stopped=await api(path+'/stop','POST',{idempotencyKey:key('microvm-export-stop')});await wait(stopped.operationId);await Promise.race([closed,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Service socket did not close')),15000))]);
 const denied=await context.request.get(new URL('counter',frame.url()).href,{maxRedirects:0});assert.ok([401,403,409,503].includes(denied.status()),'stopped Work cannot use old Service route');
 console.log('PASS Service application Cookie, same UI origin, socket closure and denied old route after real Work stop');
}finally{await browser.close();}
const exported=await api(path+'/exports','POST',{idempotencyKey:key('microvm-cold-export')});await wait(exported.operationId);
const content=await fetch(coreOrigin+'/api/v1/work-snapshots/'+exported.snapshotId+'/content',{headers:auth});assert.equal(content.status,200);const bytes=Buffer.from(await content.arrayBuffer());const digest=createHash('sha256').update(bytes).digest('hex');
await writeFile(join(out,'microvm-cold.work'),bytes,{mode:0o600});
const upload=await fetch(coreOrigin+'/api/v1/work-packages',{method:'POST',headers:{...auth,'Content-Type':'application/vnd.piwork.work-package','X-Piwork-SHA256':digest},body:bytes});assert.equal(upload.status,201);const pack=await upload.json();
const imported=await api('/api/v1/work-imports','POST',{packageId:pack.packageId,name:'Imported MicroVM Work'+suffix,idempotencyKey:key('microvm-cold-import')});await wait(imported.operationId);const work=await api('/api/v1/works/'+imported.workId);assert.equal(work.desiredState,'stopped');
await writeFile(join(out,'snapshot-result.json'),JSON.stringify({sourceWork:state.workId,importedWork:imported.workId,snapshotId:exported.snapshotId,packageId:pack.packageId,digest,bytes:bytes.length,serviceId:state.serviceId,serviceRevision:service.desiredRevision},null,2)+'\n',{mode:0o600});
console.log('PASS Real cold snapshot exported, uploaded and imported stopped; independent persistent volumes remain inside the Guest disk.');
