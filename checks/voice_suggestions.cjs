// The spoken menu under the orb: three lines for the task on screen, all at
// once, and while a read-back waits, the three answers with what each does.
// The five-second rotation this check used to guard is gone on purpose: a
// line that rotates asks the worker to wait for the one they wanted.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync('web/index.html','utf8');
const source = html.slice(html.indexOf('const TASK_SUGGESTIONS ='), html.indexOf('// Every task in this area'));
const element = (tag) => ({tag,children:[],textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v},append(...nodes){this.children.push(...nodes)},replaceChildren(){this.children=[]}});
const box = element('div'); let key='receive'; let entries=[];
const text = n => n.textContent + n.children.map(text).join('');
const context = {document:{getElementById:()=>box,querySelector:()=>({dataset:{scenario:key}}),createElement:element},activeScenario:null,live:false,talkBtn:{disabled:false,clicks:0,click(){this.clicks++}},clearInterval(){},setInterval(){throw new Error('no rotation any more')}};
context.globalThis = context; context.agentDesktop = {state:{get entries(){return entries;}}};
vm.createContext(context); vm.runInContext(source,context);
context.renderVoiceSuggestions();
assert.equal(box.children[0].textContent,'Try saying');
assert.equal(box.children.filter(n=>n.tag==='q').length,3);
assert.match(text(box.children[1]),/Twenty pieces of 4711 arrived/);
key='dropped'; context.renderVoiceSuggestions();
assert.match(text(box.children[1]),/bearings/);
entries=[{name:'prepare_goods_receipt',state:'draft',result:{details:{MENGE:20,MEINS:'EA'}}}];
context.renderVoiceSuggestions();
assert.equal(box.children[0].textContent,'You can say');
const lines = box.children.filter(n=>n.tag==='q').map(text);
assert.deepEqual(lines,['“Yes, confirm”→ posts 20 EA','“Make that twelve”→ new read-back','“Cancel that”→ nothing is recorded']);
entries=[{name:'prepare_email',state:'draft',result:{details:{}}}];
context.renderVoiceSuggestions();
assert.match(text(box.children[2]),/Change it/);
assert.match(text(box.children[3]),/nothing is saved/);
// Choosing a line makes it the green one; the choice survives a re-render and
// yields to the first line again once the worker has spoken.
entries=[]; key='receive'; context.renderVoiceSuggestions();
const chips=()=>box.children.filter(n=>n.tag==='q');
assert.deepEqual(chips().map(q=>q.attrs['aria-pressed']),['true','false','false']);
chips()[1].onclick();
assert.equal(context.talkBtn.clicks,1,'choosing a line opens the microphone when it is closed');
context.live=true; chips()[2].onclick(); assert.equal(context.talkBtn.clicks,1,'and leaves it alone when it is open'); context.live=false; chips()[1].onclick();
assert.deepEqual(chips().map(q=>q.attrs['aria-pressed']),['false','true','false']);
context.renderVoiceSuggestions();
assert.deepEqual(chips().map(q=>q.attrs['aria-pressed']),['false','true','false']);
context.forgetSuggestionChoice(); context.renderVoiceSuggestions();
assert.deepEqual(chips().map(q=>q.attrs['aria-pressed']),['true','false','false']);
console.log('Suggestions: three lines per task, the three answers with their effect while a draft waits, no rotation, a chosen line stays chosen passed.');
