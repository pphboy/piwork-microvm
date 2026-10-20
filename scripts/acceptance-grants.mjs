import {coreOrigin} from './acceptance-endpoints.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
const project=resolve(import.meta.dirname,'..'),out=resolve(process.env.PIWORK_ACCEPTANCE_OUT||join(project,'dist/acceptance'));
const credentials=JSON.parse(await readFile(join(out,'credentials.json'),'utf8'));
const state=JSON.parse(await readFile(join(out,'browser-result.json'),'utf8'));
const image=JSON.parse(await readFile(join(project,'dist/piwork/images.json'),'utf8')).agent.reference;
const origin=new URL('http://127.0.0.1:'+Number(process.env.PIWORK_ACCEPTANCE_PORT||17891)).origin;
const login=await fetch(coreOrigin+'/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});assert.equal(login.status,200);const {token}=await login.json();
async function api(path,method='GET',body){const r=await fetch(coreOrigin+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const x=await r.json();assert.ok(r.ok,method+' '+path+' '+r.status+' '+x.code);return x;}
async function wait(id){const until=Date.now()+180000;while(Date.now()<until){const op=await api('/api/v1/operations/'+id);if(op.state==='succeeded')return;assert.ok(!['failed','superseded'].includes(op.state),'grant operation '+op.state);await new Promise(r=>setTimeout(r,300));}throw new Error('grant operation timeout');}
const path='/api/v1/works/'+state.workId;
const checks=[];
for(const mode of ['readonly','none']){
 const program=`const fs=require('fs'),http=require('http');const mode=${JSON.stringify(mode)};let result={mode};if(mode==='readonly'){result.read=fs.readFileSync('/var/data/workspace/persist.txt','utf8');try{fs.writeFileSync('/var/data/workspace/no-write','bad');result.workspace='WRITABLE'}catch(e){result.workspace=e.code}}else{result.workspace=fs.existsSync('/var/data/workspace/persist.txt');result.private=fs.existsSync('/var/data/work.sqlite')}http.createServer((q,r)=>{r.setHeader('Content-Type','application/json');r.end(JSON.stringify(result))}).listen(8099,'0.0.0.0');`;
 let service=(await api(path+'/services')).services.find(s=>s.name==='probe-'+mode);
 if(!service){const accepted=await api(path+'/services','POST',{definition:{name:'probe-'+mode,image:{reference:image},command:'node',args:['-e',program],workingDirectory:mode==='readonly'?'/var/data/workspace':'/',mounts:mode==='readonly'?[{source:'workspace',target:'/var/data/workspace',readOnly:true}]:[],ports:[{name:'web',protocol:'tcp',containerPort:8099}],readiness:{kind:'http',portName:'web',path:'/',deadlineMs:10000},cpuMillis:100,memoryBytes:134217728},idempotencyKey:'grant-probe-'+mode});await wait(accepted.operationId);service=(await api(path+'/services')).services.find(s=>s.name==='probe-'+mode);}
 checks.push({mode,serviceId:service.serviceId});
}
await writeFile(join(out,'grant-services.json'),JSON.stringify({workId:state.workId,checks},null,2)+'\n',{mode:0o600});
console.log('Real read-only and no-grant Services deployed; inspect their actual container results next.');
