// The spoken menu under the orb: three lines for the task on screen, all at
// once, and while a read-back waits, the three answers with what each does.
// The five-second rotation this check used to guard is gone on purpose: a
// line that rotates asks the worker to wait for the one they wanted.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync('web/index.html','utf8');
const source = html.slice(html.indexOf('const TASK_SUGGESTIONS ='), html.indexOf('// Every task in this area'));
const element = (tag) => ({tag,children:[],textContent:'',append(...nodes){this.children.push(...nodes)},replaceChildren(){this.children=[]}});
const box = element('div'); let key='receive'; let entries=[];
const text = n => n.textContent + n.children.map(text).join('');
const context = {document:{getElementById:()=>box,querySelector:()=>({dataset:{scenario:key}}),createElement:element},activeScenario:null,clearInterval(){},setInterval(){throw new Error('no rotation any more')}};
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
console.log('Suggestions: three lines per task, the three answers with their effect while a draft waits, no rotation passed.');
