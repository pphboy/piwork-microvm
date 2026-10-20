import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance'));
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const credentials=JSON.parse(await readFile(join(out,'credentials.json'))),state=JSON.parse(await readFile(join(out,'browser-result.json')));
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
try{
 const page=await browser.newPage();page.setDefaultTimeout(120000);
 await page.goto(origin+'/login');await page.getByLabel('Account',{exact:true}).fill(credentials.account);await page.getByLabel('Password',{exact:true}).fill(credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(url=>url.pathname==='/');
 await page.goto(origin+'/#/work/'+state.workId);await page.getByRole('button',{name:'Services',exact:true}).click();
 await page.locator('button[data-action="service-picker"]').click();await page.locator('button[data-action="select-service"][data-id="'+state.serviceId+'"]').click();
 const locator=page.frameLocator('iframe[title="microvm-service application"]');await locator.getByRole('heading',{name:'Piwork MicroVM Service',exact:true}).waitFor();
 const frame=await(await page.locator('iframe[title="microvm-service application"]').elementHandle()).contentFrame();
 const counter=await frame.evaluate(()=>fetch('counter').then(r=>r.json()));assert.equal(counter.value,state.counterAfter.value);
 assert.equal(await frame.evaluate(()=>fetch('integrity').then(r=>r.text())),'ok');
 const websocket=await frame.evaluate(()=>new Promise((resolve,reject)=>{const u=new URL('socket',location.href);u.protocol='ws:';const w=new WebSocket(u);const timer=setTimeout(()=>reject(new Error('timeout')),10000);w.onopen=()=>w.send('restart');w.onmessage=e=>{clearTimeout(timer);w.close();resolve(e.data)};w.onerror=()=>reject(new Error('websocket'));}));assert.equal(websocket,'echo:restart');
 await page.screenshot({path:join(out,'service-recovered.png'),fullPage:true});
 await writeFile(join(out,'recovery-browser-result.json'),JSON.stringify({origin,counter,integrity:'ok',websocket},null,2)+'\n',{mode:0o600});
 console.log('PASS real browser login, original Service SQLite counter/integrity and WebSocket after VM restart');
}finally{await browser.close();}
