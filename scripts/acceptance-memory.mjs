import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance'));
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const state=JSON.parse(await readFile(join(out,'storage-result.json'),'utf8'));
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});assert.equal(login.status,200);const {token}=await login.json();
async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const x=await r.json();assert.ok(r.ok,method+' '+path+' status '+r.status+' '+x.code);return x;}
let model=(await api('/api/v1/admin/models')).models.find(m=>m.name==='Synthetic MicroVM fixture');
if(!model)model=await api('/api/v1/admin/models','POST',{name:'Synthetic MicroVM fixture',model:'gpt-4.1-mini',api:'openai-responses',baseUrl:'http://127.0.0.1:18555/v1',credential:'synthetic-fixture-only-not-provider-key'});
const path='/api/v1/works/'+state.workId;
for(const until=Date.now()+180000;Date.now()<until;){const r=await fetch(coreOrigin+path+'/sessions',{headers:{Authorization:'Bearer '+token}});if(r.status===200)break;await new Promise(r=>setTimeout(r,500));}
await api(path+'/sessions/'+state.sessionId+'/chat-options','PATCH',{modelRef:model.modelRef,thinkingLevel:'off'});
const accepted=await api(path+'/runs','POST',{sessionId:state.sessionId,submissionKey:'synthetic-microvm-memory',prompt:'This is a synthetic integration test. Remember my preference that MicroVM preserves ordinary files and preferences.'});
const runId=accepted.run.runId,deadline=Date.now()+180000;
let run;
while(Date.now()<deadline){run=await api(path+'/runs/'+runId);if([4,5,6,7].includes(run.state))break;await new Promise(r=>setTimeout(r,500));}
assert.equal(run.state,4,'production SDK Run against synthetic Responses fixture');assert.match(run.finalText,/SYNTHETIC_FIXTURE_MEMORY_COMMITTED/);
await api(path+'/sessions/'+state.sessionId+'/chat-options','PATCH',{modelRef:null,thinkingLevel:'off'});
const toolHistory=await fetch(coreOrigin+path+'/sessions/'+state.sessionId,{headers:{Authorization:'Bearer '+token}});
const textSession=await api(path+'/sessions','POST',{idempotencyKey:'microvm-text-history'});
await api(path+'/sessions/'+textSession.sessionId+'/chat-options','PATCH',{modelRef:model.modelRef,thinkingLevel:'off'});
const textAccepted=await api(path+'/runs','POST',{sessionId:textSession.sessionId,submissionKey:'synthetic-text-history',prompt:'synthetic-text-only-history: return a deterministic synthetic test message.'});
let textRun;
for(const until=Date.now()+120000;Date.now()<until;){textRun=await api(path+'/runs/'+textAccepted.run.runId);if([4,5,6,7].includes(textRun.state))break;await new Promise(r=>setTimeout(r,300));}
assert.equal(textRun.state,4);assert.equal(textRun.finalText,'SYNTHETIC_FIXTURE_TEXT_HISTORY');
await api(path+'/sessions/'+textSession.sessionId+'/chat-options','PATCH',{modelRef:null,thinkingLevel:'off'});
const textHistory=await api(path+'/sessions/'+textSession.sessionId);assert.ok(textHistory.messages.some(m=>m.text.includes('SYNTHETIC_FIXTURE_TEXT_HISTORY')));
await writeFile(join(out,'memory-result.json'),JSON.stringify({realProvider:false,workId:state.workId,sessionId:state.sessionId,runId,state:run.state,finalText:run.finalText,toolSessionHistoryHTTP:toolHistory.status,historySessionId:textSession.sessionId,historyRunId:textRun.runId,historyFinalText:textRun.finalText},null,2)+'\n',{mode:0o600});
console.log('PASS Production Agent SDK Session/Run used a clearly synthetic Responses fixture and completed Memory tools. External provider remains unverified.');
console.log('PASS separate text Session history read through the original Core API; tool Session history HTTP '+toolHistory.status+' recorded accurately');
