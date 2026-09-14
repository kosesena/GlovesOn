// Execute the real session functions with fake transports; no mic/network/ERP.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = readFileSync('web/index.html', 'utf8');
const source = html.slice(html.indexOf('async function start() {'), html.indexOf('const scenarios = {'));
const timers = new Map(); let timerId = 0; const sockets = [];
const transcript = {open:false,value:'laptop',prepend(){},before(){}}; let status = ''; const messages = [];
class Socket {
  static OPEN = 1;
  constructor() {this.readyState = 1; this.sent=[]; sockets.push(this);}
  send(message) {this.sent.push(JSON.parse(message));} close() {this.readyState = 3;}
}
class Events {
  constructor() {queueMicrotask(() => this.onopen?.());}
  close() {this.closed = true;}
}
const context = vm.createContext({
  GlovesOnVoice:require('../web/voice-policy.js'), voiceNotes:{events:[]}, voiceSessionId:null,voiceBinding:null,
  recoveryTimer:null,recoveryDeadline:0,recoveryGeneration:0,noteVoice(){},
  WebSocket: Socket, EventSource: Events, WS_URL: 'wss://test',
  ws:null, sse:null, activeScopeToken:null, sessionSetupTimer:null, live:false,
  activeScenario:{title:'Test', action:'stock'}, scenarioSession:null,
  talkBtn:{disabled:false, textContent:'', classList:{replace(){}}},
  stampEl:{classList:{contains(){return false;}}},
  pendingTool:null, playCtx:null, playSources:[],
  document:{getElementById(){return transcript;},createElement(){return {append(){},remove(){}};}},
  setStatus(value){status=value;}, ensurePlayback:async()=>{}, prepareMicrophone:async()=>{}, append(...args){messages.push(args);}, receiveScopedEvent(){},
  finishUserTurn(){}, updateUserTranscript(){}, showToolCard(){}, pendingFactCards:[], clearPending(){}, clearDoc(){}, stopMic(){}, stopPlayback(){}, startMic:async()=>{},
  setTimeout(fn) {const id=++timerId; timers.set(id,fn); return id;},
  clearTimeout(id) {timers.delete(id);},
  fetch:async()=>({ok:true,json:async()=>({token:'test',agent_id:'temp',scope_token:'scope'})})
});
vm.runInContext(source, context);
(async()=>{
  await context.start();
  const oldSocket=sockets[0];
  await oldSocket.onmessage({data:JSON.stringify({type:'session.ready',config:{system_prompt:'base'}})});
  assert.equal(timers.size,1,'scenario acknowledgement timeout pending');
  const lateMessage=oldSocket.onmessage;
  context.end();
  assert.equal(timers.size,0,'teardown clears scenario timeout');
  await context.start();
  const current=context.ws;
  await lateMessage({data:JSON.stringify({type:'session.ended'})});
  assert.equal(context.ws,current,'old session cannot close new session');
  await current.onmessage({data:JSON.stringify({type:'session.ended'})});
  assert.equal(context.ws,null,'provider end tears down transports');
  assert.equal(context.activeScopeToken,null,'provider end releases private agent');
  await context.start();
  await context.ws.onmessage({data:JSON.stringify({type:'session.error',code:'agent_not_found',message:'Agent not found'})});
  assert.equal(context.ws,null,'provider error tears down transports before readiness');
  assert.equal(context.activeScopeToken,null,'provider error releases private agent');
  assert.equal(transcript.open,true,'failure is visible outside a collapsed transcript');
  assert.equal(status,'Connection error','failure does not masquerade as ready');
  assert.match(messages.at(-1)[2],/could not find/);
  transcript.open=false;
  context.ensurePlayback=async()=>{throw new Error('unsupported audio');};
  await context.start();
  assert.equal(context.talkBtn.disabled,false,'audio setup failure permits retry');
  assert.equal(transcript.open,true,'audio failure is visible');
  assert.equal(status,'Connection error');
  context.ensurePlayback=async()=>{};
  context.activeScenario=null;
  context.TOOL_LABEL={}; context.endToolPhase=()=>{};
  let completeTool;
  context.fetch=async(path)=>path.startsWith('/api/voice-tools/')
    ? new Promise(resolve=>{completeTool=()=>resolve({ok:true,json:async()=>({found:true,total:240})});})
    : {ok:true,json:async()=>({token:'test',session_config:{system_prompt:'base',tools:[]},scope_token:'scope',tool_capability:'ephemeral'})};
  await context.start();
  const inline=context.ws;
  inline.onopen();
  assert.equal(inline.sent[0].session.system_prompt,'base');
  assert.equal(inline.sent[0].session.agent_id,undefined,'inline connection never resolves a stored agent');
  await inline.onmessage({data:JSON.stringify({type:'tool.call',call_id:'one',name:'get_stock',arguments:{material:'4711'}})});
  completeTool(); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(inline.sent.filter(x=>x.type==='tool.result').length,0,'result waits for reply boundary');
  await inline.onmessage({data:JSON.stringify({type:'reply.done',status:'completed'})});
  assert.equal(inline.sent.filter(x=>x.type==='tool.result').length,1);
  assert.equal(JSON.parse(inline.sent.filter(x=>x.type==='tool.result').at(-1).result).total,240);
  assert.equal(context.requestWorkspaceAction('unknown'),false);
  assert.equal(context.requestWorkspaceAction('draft_email'),true);
  const selected=inline.sent.find(x=>x.type==='conversation.message');
  assert.equal(selected.role,'user');
  assert.match(selected.content,/Draft an email/);
  assert.match(inline.sent.at(-1).instructions,/never a confirmation/);
  assert.equal(context.requestWorkspaceAction('save_note'),false,'a reply in progress cannot be replaced by another selection');

  await inline.onmessage({data:JSON.stringify({type:'tool.call',call_id:'two',name:'get_stock',arguments:{material:'4711'}})});
  await inline.onmessage({data:JSON.stringify({type:'reply.done',status:'interrupted'})});
  completeTool(); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(inline.sent.filter(x=>x.type==='tool.result').length,1,'interruption discards late results');
  let played;
  context.base64ToFloat32=value=>value;
  context.playChunk=value=>{played=value;};
  await inline.onmessage({data:JSON.stringify({type:'reply.audio',data:'PCM16-test-chunk'})});
  assert.equal(played,'PCM16-test-chunk','provider data field reaches audio playback');
  context.end();
  let toolRequests=0, settleWrite;
  const template=JSON.parse(readFileSync('agent/agent.json','utf8'));
  const catalog=template.tools.map(t=>({...t,type:'function'}));
  context.fetch=async(path,opts)=>{
    if(path==='/api/voice-session/bind') return {ok:true};
    if(path==='/api/voice-session/resume-token') return {ok:true,json:async()=>({token:'fresh',session_id:'sess_resume'})};
    if(path.startsWith('/api/voice-tools/')) {
      toolRequests++;
      if(path.endsWith('prepare_goods_receipt')) return {ok:true,json:async()=>({prepared:true,draft_token:'draft'})};
      return new Promise(resolve=>{settleWrite=()=>resolve({ok:true,json:async()=>({posted:true,document:'4900000001'})});});
    }
    return {ok:true,json:async()=>({token:'first',session_config:template,tool_catalog:catalog,scope_token:'scope',tool_capability:'cap'})};
  };
  await context.start(); let dropped=context.ws; dropped.onopen();
  await dropped.onmessage({data:JSON.stringify({type:'session.ready',session_id:'sess_resume'})});
  await dropped.onmessage({data:JSON.stringify({type:'tool.call',call_id:'prep',name:'prepare_goods_receipt',arguments:{material:'4711',quantity:20}})});
  await new Promise(resolve=>setImmediate(resolve));
  await dropped.onmessage({data:JSON.stringify({type:'reply.done',status:'completed'})});
  context.showDraftRow=()=>{};context.showPending=()=>{};
  await dropped.onmessage({data:JSON.stringify({type:'tool.call',call_id:'write-once',name:'post_goods_receipt',arguments:{material:'4711',quantity:20}})});
  await dropped.onmessage({data:JSON.stringify({type:'reply.done',status:'completed'})});
  assert.equal(context.requestWorkspaceAction('save_note'),false,'a pending write cannot be displaced by a suggestion');
  dropped.close(); dropped.onclose(); await new Promise(resolve=>setImmediate(resolve));
  const resumed=context.ws; assert.notEqual(resumed,dropped); resumed.onopen();
  assert.deepEqual(JSON.parse(JSON.stringify(resumed.sent[0])),{type:'session.resume',session_id:'sess_resume'});
  settleWrite(); await new Promise(resolve=>setImmediate(resolve));
  await resumed.onmessage({data:JSON.stringify({type:'session.ready',session_id:'sess_resume'})});
  await resumed.onmessage({data:JSON.stringify({type:'tool.call',call_id:'write-once',name:'post_goods_receipt',arguments:{material:'4711',quantity:20}})});
  assert.equal(toolRequests,2,'resumed duplicate call ID reuses the outcome, never executes another write');
  assert.equal(context.activeScopeToken,'scope','transient drop keeps the same capability scope');
  context.end();
  assert.equal(context.activeScopeToken,null,'intentional end revokes the scope');
  context.activeScenario=null;
  let callWrites=0;
  context.fetch=async(path)=>({ok:true,json:async()=>path==='/api/voice-session/alex-token' ? {token:'alex-token',voice:'james'} : path.startsWith('/api/voice-tools/')
    ? (path.endsWith('/prepare_call') ? {prepared:true,draft_token:'draft'} : (++callWrites,{completed:true,simulated:true,record:{id:'CALL-TEST',status:'simulated_call_logged',details:{recipient:{id:'alex'},purpose:'Damaged delivery'}}}))
    : {token:'test',session_config:{system_prompt:'base',tools:[]},scope_token:'scope',tool_capability:'ephemeral'}});
  await context.start(); const callSocket=context.ws;
  for(const [name,id] of [['prepare_call','p'],['place_call','c']]) {
    await callSocket.onmessage({data:JSON.stringify({type:'tool.call',name,call_id:id,arguments:{}})});
    await new Promise(resolve=>setImmediate(resolve));
    await callSocket.onmessage({data:JSON.stringify({type:'reply.done',status:'completed'})});
  }
  assert.equal(callSocket.sent.some(x=>x.session?.system_prompt?.includes('ACTIVE FICTIONAL CALL')),false,'pending call must receive its result before its tool is removed');
  await callSocket.onmessage({data:JSON.stringify({type:'reply.done',status:'completed'})});
  await new Promise(resolve=>setImmediate(resolve));
  const alex=sockets.at(-1);
  assert.notEqual(alex,callSocket,'Alex gets a separate voice session');
  alex.onopen();
  assert.equal(alex.sent[0].session.tools.length,0);
  assert.equal(alex.sent[0].session.output.voice,'james');
  assert.equal(context.ws,null,'microphone waits for Alex readiness');
  assert(!alex.sent[0].session.system_prompt.includes('base'));
  await alex.onmessage({data:JSON.stringify({type:'session.ready'})});
  await alex.onmessage({data:JSON.stringify({type:'tool.call',name:'search_material',call_id:'stale'})});
  assert.equal(callWrites,1,'Alex cannot call the gateway');
  await alex.onmessage({data:JSON.stringify({type:'transcript.user',text:'Thanks, Alex. End call.'})});
  assert.equal(context.ws,callSocket,'ending Alex restores the original GlovesOn conversation');
  assert.equal(alex.readyState,3);
  context.end();
  console.log('Voice lifecycle: setup, teardown, interruption, result ordering and in-flight write recovery passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
