// Runs as a real Piwork Service in the production Agent image, UID 10001.
const http=require('node:http'),fs=require('node:fs'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const database='/var/data/workspace/data/microvm.sqlite';
fs.mkdirSync('/var/data/workspace/data',{recursive:true});
const sql=q=>execFileSync('sqlite3',[database,q],{encoding:'utf8'}).trim();
sql('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS counter(value INTEGER); INSERT INTO counter SELECT 0 WHERE NOT EXISTS(SELECT 1 FROM counter);');
const counter=()=>Number(sql('SELECT value FROM counter;'));
const server=http.createServer(async(req,res)=>{
 if(req.url==='/health'){res.end('ok');return;}
 if(req.url==='/counter'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({value:counter()}));return;}
 if(req.url==='/integrity'){res.end(sql('PRAGMA integrity_check;'));return;}
 if(req.url==='/increment'&&req.method==='POST'){
  sql('PRAGMA synchronous=FULL; BEGIN IMMEDIATE; UPDATE counter SET value=value+1; COMMIT;');
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify({value:counter()}));return;
 }
 if(req.url==='/events'){
  res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache'});
  res.write('data: microvm-first\n\n');setTimeout(()=>{res.end('data: microvm-second\n\n');},100);return;
 }
 if(req.url==='/note'){res.end(fs.readFileSync('/var/data/workspace/note.txt'));return;}
 if(req.url==='/cookie'){res.end(req.headers.cookie||'');return;}
 if(req.url==='/network'){
  try{
   await require('node:dns').promises.lookup('example.com');
   const r=await fetch('https://example.com',{signal:AbortSignal.timeout(15000)});
   const ai=await fetch('https://api.openai.com/v1/models',{signal:AbortSignal.timeout(15000)});
   res.setHeader('Content-Type','application/json');res.end(JSON.stringify({dns:true,https:r.status,aiApiReachable:true,aiHttpStatus:ai.status,modelCalled:false}));
  }catch{res.writeHead(503);res.end('network unavailable');}return;
 }
 res.setHeader('Content-Type','text/html');res.setHeader('Set-Cookie','demo=isolated; HttpOnly; Path=/; SameSite=Lax');
 res.end('<!doctype html><h1>Piwork MicroVM Service</h1><p>Real Work container, persistent SQLite, HTTP/WebSocket/SSE.</p>');
});
server.on('upgrade',(req,socket)=>{
 if(req.url!=='/socket'||!req.headers['sec-websocket-key']){socket.destroy();return;}
 const accept=crypto.createHash('sha1').update(req.headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
 socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n');
 let pending=Buffer.alloc(0);
 socket.on('data',chunk=>{
  pending=Buffer.concat([pending,chunk]);
  while(pending.length>=2){
   const opcode=pending[0]&15,masked=(pending[1]&128)!==0;let size=pending[1]&127,offset=2;
   if(size===126){if(pending.length<4)return;size=pending.readUInt16BE(2);offset=4;}
   if(size===127||size>4096){socket.destroy();return;}
   const end=offset+(masked?4:0)+size;if(pending.length<end)return;
   const mask=masked?pending.subarray(offset,offset+4):null;offset+=masked?4:0;
   const body=Buffer.from(pending.subarray(offset,end));if(mask)for(let i=0;i<body.length;i++)body[i]^=mask[i%4];
   pending=pending.subarray(end);
   if(opcode===8){socket.end(Buffer.from([0x88,0]));return;}
   if(opcode===1){const reply=Buffer.from('echo:'+body.toString());socket.write(Buffer.concat([Buffer.from([0x81,reply.length]),reply]));}
  }
 });socket.on('error',()=>{});
});
server.listen(8099,'0.0.0.0');
