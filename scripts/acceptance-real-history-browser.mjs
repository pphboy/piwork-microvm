// Read the actual real-provider tool history through the unmodified UI.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT),label=process.env.PIWORK_ACCEPTANCE_PHASE||'restart';
assert.match(label,/^[a-z0-9-]+$/);
const origin='http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT);
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const saved=JSON.parse(await readFile(join(out,'real-model-state.json'),'utf8'));
const {chromium}=await import(pathToFileURL(process.env.PIWORK_PLAYWRIGHT_MODULE||'/home/p/Projects/piwork/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({headless:true,...(process.env.PIWORK_BROWSER_PATH?{executablePath:process.env.PIWORK_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-proxy-server']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(60000);
 await page.goto(origin+'/login');
 await page.getByLabel('Account',{exact:true}).fill(credentials.account);
 await page.getByLabel('Password',{exact:true}).fill(credentials.password);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(u=>u.pathname==='/');
 await page.goto(origin+'/#/work/'+saved.workId);
 await page.locator('button[data-action="sessions"]').first().click();
 const pending=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname.endsWith('/sessions/'+saved.sessionId));
 await page.locator('button[data-action="select-session"][data-id="'+saved.sessionId+'"]').click();
 const response=await pending;assert.equal(response.status(),200);
 await page.waitForFunction(marker=>document.body.innerText.includes(marker),saved.marker);
 assert.equal(await page.locator('.read-failure').first().isVisible(),false);
 await page.screenshot({path:join(out,'real-history-'+label+'.png'),fullPage:true});
 await writeFile(join(out,'real-history-browser-'+label+'.json'),JSON.stringify({origin,sessionId:saved.sessionId,status:200,markerVisible:true,readFailureVisible:false},null,2)+'\n',{mode:0o600});
 console.log('PASS original browser UI loaded real tool history: HTTP 200, expected model result visible');
}finally{await browser.close();}
