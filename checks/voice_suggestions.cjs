const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync('web/index.html','utf8');
const source = html.slice(html.indexOf('const TASK_SUGGESTIONS ='), html.indexOf('// Every task in this area'));
const element = () => ({children:[],textContent:'',classList:{toggle(){}},setAttribute(){},append(...nodes){this.children.push(...nodes)},replaceChildren(){this.children=[]},animate(){}});
const box = element(); let tick; let ms; let key='receive';
const context = {document:{hidden:false,getElementById:()=>box,querySelector:()=>({dataset:{scenario:key}}),createElement:element},live:false,activeScenario:null,warehouseStage:'work',location:{hash:'#warehouse'},reducedMotion:{matches:true},clearInterval(){tick=null},setInterval(fn,delay){tick=fn;ms=delay;return 1}};
vm.createContext(context);vm.runInContext(source,context);context.renderVoiceSuggestions();
assert.equal(ms,5000);const first=box.children[1].textContent;tick();assert.notEqual(box.children[1].textContent,first);
const current=box.children[1].textContent;
for(const [target,field,value] of [[context,'live',true],[box,'hidden',true],[context.document,'hidden',true],[context,'warehouseStage','lobby']]){const old=target[field];target[field]=value;tick();assert.equal(box.children[1].textContent,current);target[field]=old;}
key='dropped';context.renderVoiceSuggestions();assert.match(box.children[1].textContent,/bearings/);
console.log('Suggestions: five-second rotation, speaking/hidden/navigation pause, task reset passed.');
