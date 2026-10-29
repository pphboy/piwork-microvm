// Focused regressions against the production script, with only its automatic
// boot replaced in this test copy. No product debug API or external DOM library.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html = fs.readFileSync(new URL('../cmd/piwork-launcher/frontend/index.html', import.meta.url), 'utf8');
const source = fs.readFileSync(new URL('../cmd/piwork-launcher/frontend/app.js', import.meta.url), 'utf8');
const catalogs = Object.fromEntries(['en','zh-CN'].map(language => [language, JSON.parse(fs.readFileSync(new URL(`../internal/desktop/locales/${language}.json`, import.meta.url), 'utf8'))]));
class Element {
  constructor(dataset={}) { this.dataset=dataset; this.attrs={};this.classes=new Set();this.textContent='';this.disabled=false;this.handlers={};this.scrollHeight=0;this.scrollTop=0;this.clientHeight=0;this.classList={toggle:(k,v)=>v?this.classes.add(k):this.classes.delete(k),add:k=>this.classes.add(k),remove:k=>this.classes.delete(k),contains:k=>this.classes.has(k)}; }
  setAttribute(k,v) {this.attrs[k]=v;}
  getAttribute(k) {return this.attrs[k];}
  querySelector() {return new Element();}
  addEventListener(name,fn) {this.handlers[name]=fn;}
  focus() {this.onFocus?.();}
}
function setup(app={}) {
  const ids=new Map();const id=name=>{if(!ids.has(name))ids.set(name,new Element());return ids.get(name);};
  const screens=['idle','starting','running','error','stopping'].map(screen=>new Element({screen}));
  const terms=[...html.matchAll(/data-i18n="([^"]+)"/g)].map(m=>new Element({i18n:m[1]}));
  const languages=['en','zh-CN'].map(language=>{const el=new Element({language});el.textContent=language==='en'?'English':'简体中文';return el;});
  const documentEvents={};
  const events={};const document={documentElement:{lang:'en'},getElementById:id,querySelectorAll:s=>({'.screen':screens,'[data-step]':[0,1,2].map(step=>new Element({step})), '[data-i18n]':terms,'[data-language]':languages}[s]||[]),addEventListener:(name,fn)=>documentEvents[name]=fn};
  id('languageMenu').hidden=true;
  languages.forEach(el=>el.onFocus=()=>document.activeElement=el);
  id('languageTrigger').onFocus=()=>document.activeElement=id('languageTrigger');
  const ctx={document,window:{go:{main:{App:app}},runtime:{EventsOn:(name,fn)=>events[name]=fn}},navigator:{language:'zh-CN',languages:['zh-CN']},setTimeout:()=>0,clearTimeout(){}};
  vm.createContext(ctx);
  vm.runInContext(source.replace('  boot();','  globalThis.testAPI = {ui, onStatus, onLog, refreshLogs, boot, applyStatus, causeText};'),ctx);
  return {...ctx.testAPI,id,screens,events,terms,languages,document,documentEvents};
}
const status=(revision,session,state='starting')=>({revision,session,state,installationRoot:'/owned/data',language:'en',phase:'guest',canStart:false,canRetry:false,canChooseDir:false});

test('late old events/snapshots cannot revive running or replace logs',async()=>{
 let resolve;const p=new Promise(r=>resolve=r);const x=setup({ReadLogs:()=>p});x.ui.catalogs=catalogs;
 x.onStatus(status(5,'old','running'));
 x.onStatus(status(10,'new'));
 x.onLog({session:'new',text:'new log'});
 x.onStatus({...status(9,'old','running'),webAvailable:true,webURL:'http://old'});
 x.onLog({session:'old',text:'old log'});
 resolve({text:'old response',currentAvailable:true});await new Promise(r=>setImmediate(r));
 assert.equal(x.ui.status.session,'new');assert.equal(x.ui.status.state,'starting');assert.equal(x.id('openButton').disabled,true);
 assert.deepEqual([...x.ui.logs],['new log']);
});

test('startup subscribes before snapshot; Chinese OS never changes English default',async()=>{
 const calls=[];const x=setup({GetCatalogs:async()=>catalogs,GetStatus:async()=>{calls.push(Object.keys(x.events).length);return status(1,'');},ReadLogs:async()=>({})});
 await x.boot();assert.deepEqual(calls,[2]);assert.equal(x.ui.language,'en');assert.equal(x.document.documentElement.lang,'en');
 assert.equal(x.id('footerStatus').textContent,'Local · Starting');
});

test('offline language switching preserves VM state, log and known error',()=>{
 const x=setup();x.ui.catalogs=catalogs;
 const running={...status(1,'same','running'),webAvailable:true,webURL:'http://127.0.0.1:17891',diskPath:'/same/disk'};
 x.onStatus(running);x.onLog({session:'same',text:'technical log'});x.onStatus({...running,revision:2,language:'zh-CN'});
 assert.equal(x.id('openButton').disabled,false);assert.equal(x.ui.status.session,'same');assert.equal(x.document.documentElement.lang,'zh-CN');assert.deepEqual([...x.ui.logs],['technical log']);
 x.onStatus({...status(3,'same','error'),language:'zh-CN',error:'required TCP port 127.0.0.1:17891 is occupied'});
 assert.match(x.id('errorMessage').textContent,/17891/);assert.match(x.id('errorMessage').textContent,/端口/);
});

test('language choices stay collapsed until opened; selecting saves once and closes both menus',async()=>{
 const saved=[];const running={...status(1,'same','running'),webAvailable:true,webURL:'http://127.0.0.1:17891'};
 const x=setup({GetCatalogs:async()=>catalogs,GetStatus:async()=>running,ReadLogs:async()=>({}),SetLanguage:async language=>{saved.push(language);return {...running,revision:2,language};}});
 await x.boot();
 x.id('moreTrigger').handlers.click({stopPropagation(){}});
 assert.equal(x.id('currentLanguage').textContent,'English');assert.equal(x.id('languageMenu').hidden,true);
 x.id('languageTrigger').handlers.click();
 assert.equal(x.id('languageTrigger').getAttribute('aria-expanded'),'true');assert.equal(x.document.activeElement,x.languages[0]);
 await x.languages[1].handlers.click();
 assert.deepEqual(saved,['zh-CN']);assert.equal(x.id('currentLanguage').textContent,'简体中文');
 assert.equal(x.id('languageMenu').hidden,true);assert.equal(x.id('moreMenu').classList.contains('open'),false);
 assert.equal(x.ui.status.session,'same');assert.equal(x.id('openButton').disabled,false);
 x.id('moreTrigger').handlers.click({stopPropagation(){}});
 assert.equal(x.id('languageMenu').hidden,true);assert.equal(x.languages[1].getAttribute('aria-checked'),'true');
});

test('language keyboard navigation and outside dismissal preserve the parent menu correctly',async()=>{
 const x=setup({GetCatalogs:async()=>catalogs,GetStatus:async()=>status(1,''),ReadLogs:async()=>({})});await x.boot();
 const key=key=>({key,preventDefault(){}});
 x.id('moreTrigger').handlers.click({stopPropagation(){}});
 x.id('languageTrigger').handlers.keydown(key('ArrowRight'));
 x.id('languageMenu').handlers.keydown(key('ArrowUp'));assert.equal(x.document.activeElement,x.languages[1]);
 x.id('languageMenu').handlers.keydown(key('ArrowDown'));assert.equal(x.document.activeElement,x.languages[0]);
 x.documentEvents.keydown(key('Escape'));
 assert.equal(x.id('languageMenu').hidden,true);assert.equal(x.id('moreMenu').classList.contains('open'),true);assert.equal(x.document.activeElement,x.id('languageTrigger'));
 x.id('languageTrigger').handlers.click();x.id('languageMenu').handlers.keydown(key('ArrowLeft'));
 assert.equal(x.id('languageMenu').hidden,true);assert.equal(x.document.activeElement,x.id('languageTrigger'));
 x.id('languageTrigger').handlers.click();x.documentEvents.click({target:{closest:()=>null}});
 assert.equal(x.id('languageMenu').hidden,true);assert.equal(x.id('moreMenu').classList.contains('open'),false);
});

test('static text and dynamic text keys have both built-in translations',()=>{
 assert.deepEqual(Object.keys(catalogs.en).sort(),Object.keys(catalogs['zh-CN']).sort());
 const keys=[...html.matchAll(/data-i18n(?:-title|-aria-label)?="([^"]+)"/g),...source.matchAll(/\bt\('([^']+)'\)/g)].map(m=>m[1]).filter(k=>!k.endsWith('.'));
 for(const key of keys) for(const language of ['en','zh-CN']) assert.ok(catalogs[language][key],`${language}: ${key}`);
 assert.equal(html.match(/<html lang="([^"]+)"/)[1],'en');
 assert.doesNotMatch(source,/[\u4e00-\u9fff]/,'application text belongs in catalogs');
 assert.ok(!html.includes('导出诊断'));
});
