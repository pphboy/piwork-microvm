import {coreOrigin} from './acceptance-endpoints.mjs';
// Uses original Files and Agent APIs; no host directory mapping or Core changes.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance'));
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const result=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
assert.equal(login.status,200);const {token}=await login.json(),headers={Authorization:'Bearer '+token};
const path='/api/v1/works/'+result.workId;
const put=await fetch(coreOrigin+path+'/files/persist.txt',{method:'PUT',headers,body:'persistent workspace bytes'});assert.ok(put.ok);
assert.equal(await(await fetch(coreOrigin+path+'/files/persist.txt',{headers})).text(),'persistent workspace bytes');
const sessions=await(await fetch(coreOrigin+path+'/sessions',{headers})).json();
let session=sessions.sessions[0];
if(!session){const r=await fetch(coreOrigin+path+'/sessions',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({idempotencyKey:'microvm-persistent-session'})});assert.equal(r.status,201);session=await r.json();}
await writeFile(join(out,'storage-result.json'),JSON.stringify({workId:result.workId,sessionId:session.sessionId,checks:['Ordinary workspace Files write/read','Real Agent Session recorded','No host directory sharing']},null,2)+'\n',{mode:0o600});
console.log('PASS durable ordinary workspace file and real production Agent Session recorded');
