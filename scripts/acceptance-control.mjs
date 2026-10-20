import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
const out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||resolve(import.meta.dirname,'../dist/acceptance')),base=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin,credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});assert.equal(login.status,200);const {token}=await login.json();
const [work,action,key]=process.argv.slice(2),headers={Authorization:'Bearer '+token,'Content-Type':'application/json'};
const r=await fetch(coreOrigin+'/api/v1/works/'+work+'/'+action,{method:'POST',headers,body:JSON.stringify({idempotencyKey:key})});assert.equal(r.status,202);const accepted=await r.json();
for(const until=Date.now()+180000;Date.now()<until;){const op=await(await fetch(coreOrigin+'/api/v1/operations/'+accepted.operationId,{headers})).json();if(op.state==='succeeded'){console.log('PASS Work '+action);process.exit(0)};if(op.state==='failed')throw new Error('Work control failed: '+op.error?.code);await new Promise(r=>setTimeout(r,400));}
throw new Error('Work control timeout');
