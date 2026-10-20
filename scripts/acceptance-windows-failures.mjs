// Run with native Windows Node against the stopped final PE test installation.
import assert from 'node:assert/strict';
import {readFile,writeFile,rename,unlink,mkdir,access} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import net from 'node:net';
const base=resolve(process.env.PIWORK_WINDOWS_ACCEPTANCE_ROOT),installation=join(base,'安装 数据'),binary=join(base,'piwork-microvm.exe'),out=join(base,'evidence');
assert.equal(process.platform,'win32');assert.equal(await access(join(installation,'runtime.json')).then(()=>true,()=>false),false,'stop owned VM first');
const checks=[];
const corePort=Number(process.env.PIWORK_ACCEPTANCE_CORE_PORT||17871);
function run(name,args,expected,ok=false){const r=spawnSync(binary,['--core-port',String(corePort),...args],{encoding:'utf8',timeout:120000,windowsHide:true});assert.ifError(r.error);assert.equal(r.status===0,ok,name);const text=r.stdout+r.stderr;if(expected)assert.ok(text.includes(expected),name+': '+text);checks.push({case:name,exit:r.status,diagnostic:text.trim()});}
const unused=join(base,'help-must-not-create');
run('help',['--data-dir',unused,'--help'],'Usage',true);assert.equal(await access(unused).then(()=>true,()=>false),false);
for(const flag of ['--port','--core-port'])for(const value of ['0','-1','abc','65536'])run('invalid-'+flag+'-'+value,['--data-dir',unused,flag,value],'port');
run('same-host-ports',['--data-dir',unused,'--port','8080','--core-port','8080'],'different host ports');
assert.equal(await access(unused).then(()=>true,()=>false),false);
async function fileHash(path){const hash=createHash('sha256');for await(const chunk of createReadStream(path))hash.update(chunk);return hash.digest('hex');}
const disk=join(installation,'disks/state.qcow2'),saved=disk+'.acceptance-saved',before=await fileHash(disk);
await rename(disk,saved);
try{
 run('missing-existing-disk',['--data-dir',installation,'--port','8080','--no-open'],'existing persistent disk is missing');
 await writeFile(disk,'invalid existing disk; never overwrite');
 run('corrupt-existing-disk',['--data-dir',installation,'--port','8080','--no-open'],'persistent qcow2 header/size is invalid');
 assert.equal(await readFile(disk,'utf8'),'invalid existing disk; never overwrite');
}finally{await unlink(disk).catch(()=>{});await rename(saved,disk);}
assert.equal(await fileHash(disk),before);
const unknown=join(base,'unknown-installation');await mkdir(unknown,{recursive:true});await writeFile(join(unknown,'sentinel.txt'),'preserve unknown bytes');
run('unknown-data',['--data-dir',unknown,'--port','8080','--no-open'],'contains unknown data');assert.equal(await readFile(join(unknown,'sentinel.txt'),'utf8'),'preserve unknown bytes');
for(const port of [8080,corePort]){
 const server=net.createServer();await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve)});
 try{run('occupied-'+port,['--data-dir',installation,'--port','8080','--no-open'],'127.0.0.1:'+port+' is occupied');}finally{await new Promise(resolve=>server.close(resolve));}
}
await writeFile(join(out,'native-failures.json'),JSON.stringify({originalDiskSHA256:before,originalDiskBytesPreserved:true,checks},null,2)+'\n');
console.log('PASS native final PE help/invalid flags, UI/Core conflicts, unknown root and missing/corrupt disk; exact original disk retained');
