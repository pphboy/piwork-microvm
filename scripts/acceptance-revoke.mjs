import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance')),origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const credentials=JSON.parse(await readFile(join(out,'credentials.json'))),state=JSON.parse(await readFile(join(out,'browser-result.json'))),grants=JSON.parse(await readFile(join(out,'grant-services.json')));
const {token}=await(await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)})).json();
async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const value=await r.json();assert.ok(r.ok,path+' '+r.status);return value;}
const service=grants.checks.find(c=>c.mode==='none');assert.ok(service);
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
try{
 const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(90000);
 await page.goto(origin+'/login');await page.getByLabel('Account',{exact:true}).fill(credentials.account);await page.getByLabel('Password',{exact:true}).fill(credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>u.pathname==='/');
 await page.goto(origin+'/#/work/'+state.workId);await page.getByRole('button',{name:'Services',exact:true}).click();await page.locator('button[data-action="service-picker"]').click();await page.locator('button[data-action="select-service"][data-id="'+service.serviceId+'"]').click();
 const frameElement=page.locator('iframe[title="probe-none application"]');await frameElement.waitFor();const frame=await(await frameElement.elementHandle()).contentFrame();
 let url;for(const until=Date.now()+60000;Date.now()<until;){try{url=await frame.evaluate(()=>location.href);if(url.startsWith(origin+'/services/'))break;}catch{}await new Promise(r=>setTimeout(r,200));}
 const accessible=await context.request.get(url);assert.equal(accessible.status(),200);
 const operation=await api('/api/v1/works/'+state.workId+'/services/'+service.serviceId+'/stop','POST',{idempotencyKey:'acceptance-revoke-'+Date.now()});
 for(const until=Date.now()+120000;Date.now()<until;){const op=await api('/api/v1/operations/'+operation.operationId);if(op.state==='succeeded')break;assert.notEqual(op.state,'failed');await new Promise(r=>setTimeout(r,300));}
 const revoked=await context.request.get(url);assert.ok([401,403,404,409,410,503].includes(revoked.status()),'cached Service authorization must stop granting access');
 await writeFile(join(out,'revocation-result.json'),JSON.stringify({before:accessible.status(),after:revoked.status(),previousAuthorizationDenied:true},null,2)+'\n',{mode:0o600});console.log('PASS a previously authorized browser Service entry was denied after the original stop/disable operation');
}finally{await browser.close();}
