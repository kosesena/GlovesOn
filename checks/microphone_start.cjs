// Exercise Safari-sensitive ordering without a real microphone or provider.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync('web/index.html','utf8');const events=[];let allow;
const c=vm.createContext({micCtx:null,micStream:null,micNode:null,micAnalyser:null,SAMPLE_RATE:24000,
 AudioContext:class{constructor(){events.push('context');this.state='suspended';}resume(){events.push('resume');this.state='running';return Promise.resolve();}close(){return Promise.resolve();}},
 navigator:{mediaDevices:{getUserMedia(){events.push('permission');return new Promise(r=>allow=r);}}}});
vm.runInContext(html.slice(html.indexOf('async function prepareMicrophone()'),html.indexOf('// --- the session')),c);
(async()=>{const pending=c.prepareMicrophone();assert.deepEqual(events,['context','resume','permission']);
 let stopped=false;allow({getTracks:()=>[{stop(){stopped=true;}}]});await pending;assert(c.micStream);c.stopMic();assert(stopped);
 const late=c.prepareMicrophone();c.stopMic();stopped=false;allow({getTracks:()=>[{stop(){stopped=true;}}]});await late;assert(stopped);assert.equal(c.micStream,null);
 console.log('Microphone: audio resumed before permission wait; cancelled permission releases tracks');
})().catch(e=>{console.error(e);process.exitCode=1});
