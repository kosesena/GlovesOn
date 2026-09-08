// Execute the real session functions with fake transports; no mic/network/ERP.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = readFileSync('web/index.html', 'utf8');
const source = html.slice(html.indexOf('async function start() {'), html.indexOf('const scenarios = {'));
const timers = new Map(); let timerId = 0; const sockets = [];
class Socket {
  static OPEN = 1;
  constructor() {this.readyState = 1; sockets.push(this);}
  send() {} close() {this.readyState = 3;}
}
class Events {
  constructor() {queueMicrotask(() => this.onopen?.());}
  close() {this.closed = true;}
}
const context = vm.createContext({
  WebSocket: Socket, EventSource: Events, WS_URL: 'wss://test',
  ws:null, sse:null, activeScopeToken:null, sessionSetupTimer:null, live:false,
  activeScenario:{title:'Test', action:'stock'}, scenarioSession:null,
  talkBtn:{disabled:false, textContent:'', classList:{replace(){}}},
  stampEl:{classList:{contains(){return false;}}},
  pendingTool:null, playCtx:null, playSources:[],
  setStatus(){}, ensurePlayback:async()=>{}, append(){}, receiveScopedEvent(){},
  clearPending(){}, clearDoc(){}, stopMic(){}, stopPlayback(){}, startMic:async()=>{},
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
  console.log('Voice lifecycle: 3 checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
