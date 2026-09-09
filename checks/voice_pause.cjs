// Reproduce transport audio arriving between fragments, using the real event cases.
const {readFileSync}=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=readFileSync('web/index.html','utf8');const nodes=[];
const c=vm.createContext({logEl:{},setStatus(){},endToolPhase(){},playChunk(){},base64ToFloat32:x=>x,
append(kind,who,text){const n={kind,isConnected:true,lastChild:{textContent:text},classList:{toggle(){},remove(){}}};nodes.push(n);return n;}});
vm.runInContext(html.slice(html.indexOf('let userTurnEl ='),html.indexOf('let pendingFactCards =')),c);
const user=html.slice(html.indexOf("      case 'transcript.user.delta':"),html.indexOf("      case 'tool.call':",html.indexOf("      case 'transcript.user.delta':")));
const agent=html.slice(html.indexOf("      case 'reply.audio':"),html.indexOf("      case 'reply.done':",html.indexOf("      case 'reply.audio':")));
vm.runInContext('function event(m){switch(m.type){'+user+agent+'}}',c);
c.event({type:'transcript.user',text:'Show me.'});
c.event({type:'reply.audio',data:'late audio'});
c.event({type:'transcript.user.delta',text:'Receipt.'});
c.event({type:'transcript.agent',text:'',interrupted:true});
c.event({type:'reply.audio',data:'late audio'});
c.event({type:'transcript.user.delta',text:'Receipt. Receive.'});
c.event({type:'transcript.user',text:'Receipt. Receive.'});
assert.equal(nodes.length,1,'audio and empty interrupted transcripts must not split the user message');
assert.equal(nodes[0].lastChild.textContent,'Show me. Receipt. Receive.','partial hypotheses are replaced, not repeated');
c.event({type:'transcript.agent',text:'What is the material number?'});
c.event({type:'transcript.user',text:'4711.'});
assert.deepEqual(nodes.map(x=>x.kind),['user','agent','user'],'a visible agent response creates a genuine new turn');
console.log('Voice pause regression: interleaved audio, empty interruption, partial revisions and real reply passed.');
