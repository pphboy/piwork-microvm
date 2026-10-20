// Synthetic protocol fixture, NOT a model/provider. Uses the production SDK.
import http from 'node:http';
let sequence=0;
const textOf=x=>typeof x==='string'?x:JSON.stringify(x);
function value(raw){
 try{const v=JSON.parse(raw);if(v.adoptedExperienceVersion!==undefined||v.evidenceIds||v.memoryCommit)return v;if(v.details)return v.details;if(v.content)return value(v.content.map(x=>x.text||'').join(''));return v;}catch{return {};}
}
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/responses'){res.writeHead(404);res.end();return;}
 let raw='';for await(const part of req){raw+=part;if(raw.length>2e6){res.writeHead(413);res.end();return;}}
 let body;try{body=JSON.parse(raw);}catch{res.writeHead(400);res.end();return;}
 const input=Array.isArray(body.input)?body.input:[];
 let start=-1;for(let i=0;i<input.length;i++)if(input[i].role==='user')start=i;
 const output=input.slice(start+1).filter(x=>x.type==='function_call_output').map(x=>value(textOf(x.output)));
 let args;
 if(output.length===0)args={operation:'status'};
 if(output.length===1)args={operation:'stage',expectedVersion:output[0].adoptedExperienceVersion??0,userPreference:true,entry:{entryId:'microvm-preference',scope:'work',rule:'MicroVM acceptance preserves ordinary files and preferences',evidenceIds:[]}};
 if(output.length===2)args={operation:'commit',evidenceIds:output[1].evidenceIds||[]};
 const textHistory=JSON.stringify(input.slice(start)).includes('synthetic-text-only-history');
 if(textHistory)args=undefined;
 const finalText=textHistory?'SYNTHETIC_FIXTURE_TEXT_HISTORY':'SYNTHETIC_FIXTURE_MEMORY_COMMITTED';
 const id='fixture-response-'+(++sequence),usage={input_tokens:1,output_tokens:1,total_tokens:2,input_tokens_details:{cached_tokens:0},output_tokens_details:{reasoning_tokens:0}};
 let item;
 if(args){
  if(!(body.tools||[]).some(t=>t.name==='brain_experience')){res.writeHead(422);res.end('required package tool unavailable');return;}
  item={type:'function_call',id:'fc-'+sequence,call_id:'call-'+sequence,name:'brain_experience',arguments:JSON.stringify(args),status:'completed'};
 }else item={type:'message',id:'msg-'+sequence,role:'assistant',status:'completed',content:[{type:'output_text',text:finalText,annotations:[]}]};
 res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache'});
 const emit=(type,data)=>res.write('event: '+type+'\ndata: '+JSON.stringify({type,...data})+'\n\n');
 emit('response.created',{response:{id,status:'in_progress',model:body.model,output:[]}});
 emit('response.output_item.added',{output_index:0,item:{...item,status:'in_progress',...(args?{arguments:''}:{content:[]})}});
 if(args){emit('response.function_call_arguments.delta',{output_index:0,item_id:item.id,delta:item.arguments});emit('response.function_call_arguments.done',{output_index:0,item_id:item.id,arguments:item.arguments});}
 else{emit('response.content_part.added',{output_index:0,content_index:0,part:{type:'output_text',text:'',annotations:[]}});emit('response.output_text.delta',{output_index:0,content_index:0,delta:item.content[0].text});}
 emit('response.output_item.done',{output_index:0,item});emit('response.completed',{response:{id,status:'completed',model:body.model,output:[item],usage}});res.end();
 // Only protocol phase and public receipt structure are logged; no headers/body.
 console.log('fixture response '+sequence+' phase '+(args?.operation||'complete')+' result keys '+output.map(o=>Object.keys(o).join(',')).join(';'));
}).listen(18555,'127.0.0.1',()=>console.log('Synthetic Responses fixture ready on loopback 18555; no real model.'));
