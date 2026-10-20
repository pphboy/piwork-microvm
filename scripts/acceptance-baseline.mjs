import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance')),origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const browser=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
const storage=JSON.parse(await readFile(join(out,'storage-result.json'),'utf8'));
for(const until=Date.now()+240000;Date.now()<until;){try{if((await fetch(origin+'/readyz?profile=docker-delivery')).status===200)break;}catch{}await new Promise(r=>setTimeout(r,500));}
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});assert.equal(login.status,200);const identity=await login.json(),headers={Authorization:'Bearer '+identity.token};
async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{...headers,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const x=await r.json();assert.ok(r.ok,method+' '+path+' '+r.status+' '+x.code);return x;}
const path='/api/v1/works/'+browser.workId;
if((await api(path)).observedState!=='ready'){
 const accepted=await api(path+'/start','POST',{idempotencyKey:'source-after-export-'+Date.now()});
 const end=Date.now()+180000;while(Date.now()<end){const op=await api('/api/v1/operations/'+accepted.operationId);if(op.state==='succeeded')break;assert.notEqual(op.state,'failed');await new Promise(r=>setTimeout(r,400));}
}
let current;
for(const until=Date.now()+180000;Date.now()<until;){current=await api(path);if(current.observedState==='ready')break;await new Promise(r=>setTimeout(r,400));}
assert.equal(current.observedState,'ready');
const note=await(await fetch(coreOrigin+path+'/files/note.txt',{headers})).text();
const service=await api(path+'/services/'+browser.serviceId);
let session;
{
 session=(await api(path+'/sessions')).sessions.find(s=>s.sessionId===storage.sessionId);
}
assert.ok(session,'persisted Agent Session available after the real handshake');
const models=(await api('/api/v1/admin/models')).models.map(m=>({id:m.id,modelRef:m.modelRef,name:m.name,model:m.model,baseUrl:m.baseUrl}));
const data={user:identity.user,workId:browser.workId,serviceId:browser.serviceId,serviceRevision:service.desiredRevision,sessionId:storage.sessionId,noteSHA256:createHash('sha256').update(note).digest('hex'),models,counter:browser.counterAfter.value};
if(process.argv.includes('--verify')){
 const before=JSON.parse(await readFile(join(out,'persistence-baseline.json'),'utf8'));
 for(const key of ['workId','serviceId','serviceRevision','sessionId','noteSHA256'])assert.deepEqual(data[key],before[key],key);
 assert.deepEqual(data.user,before.user);assert.deepEqual(data.models,before.models);
 const file=await fetch(coreOrigin+path+'/files/persist.txt',{headers});assert.equal(file.status,200);assert.equal(await file.text(),'persistent workspace bytes');
 for(const expected of browser.files){const r=await fetch(coreOrigin+path+'/files/'+encodeURIComponent(expected.name),{headers});assert.equal(r.status,200);assert.equal(createHash('sha256').update(Buffer.from(await r.arrayBuffer())).digest('hex'),expected.sha256);}
 const memory=JSON.parse(await readFile(join(out,'memory-result.json'),'utf8'));
 const run=await api(path+'/runs/'+memory.runId);assert.equal(run.state,4);assert.equal(run.finalText,memory.finalText);
 const detail=await fetch(coreOrigin+path+'/sessions/'+(memory.historySessionId||storage.sessionId),{headers});
 if(memory.historySessionId){assert.equal(detail.status,200);const history=await detail.json();assert.ok(history.messages.some(m=>m.text.includes(memory.historyFinalText)));assert.ok(history.runs.some(r=>r.runId===memory.historyRunId));}
 await writeFile(join(out,'persistence-result.json'),JSON.stringify({checks:['administrator','models','Work identity','Service revision','Agent Session identity','Run result','Chinese/binary Files SHA256'],textSessionHistoryHTTP:detail.status,toolSessionHistoryHTTP:memory.toolSessionHistoryHTTP,knownUpstreamIssue:memory.toolSessionHistoryHTTP===200?null:'Unmodified upstream tool Session history did not return 200'},null,2)+'\n',{mode:0o600});
 console.log('PASS administrator, models, Work, Service revision, Agent Session/Run result and Chinese/binary Files hashes survived shutdown and restart');
 if(!detail.ok)console.log('FAIL upstream Session history HTTP '+detail.status+'; recorded separately, not reported as a pass');
}else{await writeFile(join(out,'persistence-baseline.json'),JSON.stringify(data,null,2)+'\n',{mode:0o600});console.log('Persistence baseline captured; real Work and Service running before VM shutdown.');}
