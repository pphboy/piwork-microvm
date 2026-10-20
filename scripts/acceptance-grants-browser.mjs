// Real browser access to Services with original workspace grants and revocation.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance'));
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const credentials=JSON.parse(await readFile(join(out,'credentials.json'))),state=JSON.parse(await readFile(join(out,'browser-result.json'))),grants=JSON.parse(await readFile(join(out,'grant-services.json')));
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
const checks=[];
try{
 const context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(45000);
 await page.goto(origin+'/login');await page.getByLabel('Account',{exact:true}).fill(credentials.account);await page.getByLabel('Password',{exact:true}).fill(credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>url.pathname==='/');
 await page.goto(origin+'/#/work/'+state.workId);await page.getByRole('button',{name:'Services',exact:true}).click();
 for(const entry of grants.checks){
  await page.locator('button[data-action="service-picker"]').click();await page.locator('button[data-action="select-service"][data-id="'+entry.serviceId+'"]').click();
  const selector='iframe[title="probe-'+entry.mode+' application"]';await page.locator(selector).waitFor();
  let value;for(const until=Date.now()+60000;Date.now()<until;){try{const f=await page.locator(selector).elementHandle();const frame=await f.contentFrame();value=await frame.evaluate(()=>fetch('./').then(r=>r.json()));break;}catch{}await new Promise(r=>setTimeout(r,400));}
  assert.ok(value);if(entry.mode==='readonly'){assert.equal(value.read,'persistent workspace bytes');assert.equal(value.workspace,'EROFS');}else{assert.equal(value.workspace,false);assert.equal(value.private,false);}
  checks.push(value);
 }
 await writeFile(join(out,'grants-result.json'),JSON.stringify(checks,null,2)+'\n',{mode:0o600});
 console.log('PASS native browser reached authorized read-only and no-grant Services; workspace writes denied and private volume absent');
}finally{await browser.close();}
