// Real-provider calls through the original Core/production Agent. Test-only.
// Modes: first (write/read tool), restart (verify + continue), check (read only).
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {coreOrigin} from './acceptance-endpoints.mjs';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT);
const mode=process.argv[2]||'check';
assert.ok(['first','restart','check'].includes(mode));
const label=process.env.PIWORK_ACCEPTANCE_PHASE||mode;
assert.match(label,/^[a-z0-9-]+$/);
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
assert.equal(login.status,200,'test installation login');
const identity=await login.json(),headers={Authorization:'Bearer '+identity.token};
async function api(path,method='GET',body){
 const r=await fetch(coreOrigin+path,{method,headers:{...headers,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const v=await r.json();
 if(!r.ok)throw new Error(method+' '+path+' HTTP '+r.status+' code '+(v.code||'unknown'));
 return v;
}
const browser=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
const storage=JSON.parse(await readFile(join(out,'storage-result.json'),'utf8'));
const path='/api/v1/works/'+browser.workId;
async function waitFor(fn,label,ms=300000){
 const deadline=Date.now()+ms;
 while(Date.now()<deadline){const value=await fn();if(value)return value;await new Promise(r=>setTimeout(r,1000));}
 throw new Error('Timeout: '+label);
}
const initialWork=await api(path);
if(initialWork.observedState!=='ready')await api(path+'/start','POST',{idempotencyKey:'real-model-recovery-'+label});
await waitFor(async()=>(await api(path)).observedState==='ready','Work runtime');
await waitFor(async()=>{try{return (await api(path+'/sessions')).sessions.some(s=>s.sessionId===storage.sessionId);}catch{return false;}},'Agent history');
const stateFile=join(out,'real-model-state.json');
let saved;
try{saved=JSON.parse(await readFile(stateFile,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
const models=(await api('/api/v1/admin/models')).models;
if(!saved){
 assert.equal(mode,'first');
 const input=JSON.parse(await readFile(process.env.PIWORK_REAL_MODEL_FILE,'utf8'));
 const model=models.find(m=>m.model===input.model);
 assert.ok(model,'real model configured by original QuickStart');
 saved={workId:browser.workId,sessionId:storage.sessionId,model:{id:model.id,modelRef:model.modelRef,model:input.model,api:input.api},marker:'PIWORK_REAL_MODEL_'+randomUUID(),file:'acceptance-real-model.txt',runs:{}};
 await writeFile(stateFile,JSON.stringify(saved,null,2)+'\n',{mode:0o600});
 await api(path+'/sessions/'+saved.sessionId+'/chat-options','PATCH',{modelRef:model.modelRef,thinkingLevel:'off'});
}
assert.equal(saved.workId,browser.workId);
assert.ok(models.some(m=>m.id===saved.model.id&&m.modelRef===saved.model.modelRef),'original model identity');
async function history(){
 const v=await api(path+'/sessions/'+saved.sessionId);
 const ids=[];let calls=0,results=0;
 function visit(x){if(!x||typeof x!=='object')return;if(x.type==='tool-call')calls++;if(x.type==='tool-result')results++;if(typeof x.toolCallId==='string')ids.push(x.toolCallId);for(const value of Object.values(x))visit(value);}
 visit(v);
 return {value:v,summary:{http:200,messages:v.messages.length,toolCalls:calls,toolResults:results,idsWithPipe:ids.filter(id=>id.includes('|')).length},ids};
}
async function checkFile(){
 const r=await fetch(coreOrigin+path+'/files/'+saved.file,{headers});assert.equal(r.status,200,'model-created file exists');
 const b=Buffer.from(await r.arrayBuffer());assert.equal(b.toString().trim(),saved.marker,'actual tool file content');
 return createHash('sha256').update(b).digest('hex');
}
let before;
if(mode!=='first'){
 before=await history();assert.ok(before.summary.toolCalls>0&&before.summary.toolResults>0);
 assert.equal(await checkFile(),saved.fileSHA256,'file survives original-disk restart');
 for(const id of saved.toolCallIds)assert.ok(before.ids.includes(id),'original tool history survives');
 for(const runId of Object.values(saved.runs))assert.equal((await api(path+'/runs/'+runId)).state,4,'previous real Run succeeded');
}
if(mode!=='check'){
 let runId=saved.runs[mode];
 if(!runId){
  const prompt=mode==='first'
   ? `This is a real Piwork MicroVM persistence acceptance test. Use the available file or command tools to write /var/data/workspace/${saved.file} with exactly the following single line, then use a tool to read it back: ${saved.marker}. The period after the marker is sentence punctuation, not file content. Do not change other files or install anything. After tool verification, reply with ACCEPTANCE_WRITTEN and the marker.`
   : `The same MicroVM has been shut down and restarted. Use a tool to read /var/data/workspace/${saved.file}. Do not modify it. Reply with ACCEPTANCE_RECOVERED followed by the exact marker you read.`;
  const accepted=await api(path+'/runs','POST',{sessionId:saved.sessionId,submissionKey:'microvm-real-'+mode+'-'+saved.marker,prompt});
  runId=accepted.run.runId;saved.runs[mode]=runId;
  await writeFile(stateFile,JSON.stringify(saved,null,2)+'\n',{mode:0o600});
 }
 const run=await waitFor(async()=>{const r=await api(path+'/runs/'+runId);return [4,5,6,7].includes(r.state)?r:null;},'real model Run',420000);
 assert.equal(run.state,4,'real model Run state');
 assert.ok(run.finalText.includes(saved.marker),'model read-back confirmation');
 assert.ok(run.finalText.includes(mode==='first'?'ACCEPTANCE_WRITTEN':'ACCEPTANCE_RECOVERED'),'model completion confirmation');
}
const after=await history();assert.ok(after.summary.toolCalls>0&&after.summary.toolResults>0,'real tool calls and results');
const hash=await checkFile();
if(mode==='first'){saved.fileSHA256=hash;saved.toolCallIds=[...new Set(after.ids)];await writeFile(stateFile,JSON.stringify(saved,null,2)+'\n',{mode:0o600});}
if(mode==='restart')assert.ok(after.summary.toolCalls>before.summary.toolCalls,'continued real tool call after reboot');
const record={checkedAt:new Date().toISOString(),realProvider:true,mode,label,workId:saved.workId,sessionId:saved.sessionId,model:saved.model,runs:saved.runs,history:after.summary,file:saved.file,fileSHA256:hash,originalToolHistoryPresent:true,...(mode==='restart'?{continuedAfterRestart:true}:{})};
await writeFile(join(out,'real-model-'+label+'.json'),JSON.stringify(record,null,2)+'\n',{mode:0o600});
// Existing baseline helpers can check the real Run and its successful history.
if(mode==='first'){
 const run=await api(path+'/runs/'+saved.runs.first);
 await writeFile(join(out,'memory-result.json'),JSON.stringify({realProvider:true,workId:saved.workId,sessionId:saved.sessionId,runId:saved.runs.first,state:run.state,finalText:run.finalText,toolSessionHistoryHTTP:200,historySessionId:saved.sessionId,historyRunId:saved.runs.first,historyFinalText:run.finalText},null,2)+'\n',{mode:0o600});
}
console.log('PASS real provider '+mode+': '+saved.model.model+' / '+saved.model.api+', history HTTP 200, '+after.summary.toolCalls+' tool calls, file verified');
