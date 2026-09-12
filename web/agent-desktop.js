/* A view of actual tool requests/results, never a scripted success animation. */
(function(root) {
  'use strict';
  const writes = new Set(['post_goods_receipt','reverse_goods_receipt','send_email','place_call','save_note']);
  const labels = {
    get_stock:'Checking stock', search_material:'Finding a material', get_purchase_order:'Opening purchase order',
    get_recent_documents:'Opening recent receipts', prepare_goods_receipt:'Preparing receipt',
    prepare_reversal:'Preparing reversal', post_goods_receipt:'Recording receipt', reverse_goods_receipt:'Recording reversal',
    find_colleague:'Finding a colleague', prepare_email:'Drafting email', send_email:'Saving to demo outbox',
    prepare_call:'Preparing call', place_call:'Logging demo call', prepare_note:'Preparing note', save_note:'Saving note',
    get_communication_history:'Opening activity', suggest_follow_up:'Suggesting next steps', search_mm_knowledge:'Checking MM reference'
  };
  function category(name) {
    if (/email/.test(name)) return 'email';
    if (/call|colleague/.test(name)) return 'phone';
    if (/note/.test(name)) return 'note';
    if (name === 'get_communication_history') return 'history';
    return 'erp';
  }
  function outcome(name, result, failed) {
    if (failed || result?.error) return writes.has(name) ? 'uncertain' : 'error';
    if (result?.prepared === true && result.draft_token) return 'draft';
    if (name === 'post_goods_receipt') return result?.posted === true && result.MBLNR ? 'saved' : 'rejected';
    if (name === 'reverse_goods_receipt') return result?.reversed === true && result.MBLNR ? 'saved' : 'rejected';
    if (writes.has(name)) return result?.completed === true && result.simulated === true && result.record?.id ? 'saved' : 'rejected';
    if (result?.prepared === false || result?.found === false) return 'rejected';
    return 'read';
  }
  class DesktopState {
    constructor() { this.reset(); }
    reset() { this.entries=[]; this.current=null; this.suggestions=null; }
    begin(name,id,args) {
      if (this.entries.some(e=>e.id===id)) return;
      // The arguments carry the sentence the agent reports as confirmed; the
      // saved card shows it as the reason the document exists. Reported, not
      // proven — the judge guide says so — but it is what the audit row holds.
      let parsed=args;
      if(typeof args==='string'){try{parsed=JSON.parse(args);}catch{parsed=null;}}
      if(!parsed||typeof parsed!=='object') parsed=null;
      // A new preparation replaces the only pending draft, across every device.
      if (name.startsWith('prepare_') || writes.has(name)) for (const entry of this.entries) if(entry.state==='draft') entry.state=writes.has(name)?'submitted':'superseded';
      if (/^prepare_(email|call|note)$/.test(name)) this.suggestions=null;
      const entry={name,id,state:'pending',result:null,args:parsed};
      this.entries.push(entry); this.entries=this.entries.slice(-20); this.current=entry;
    }
    finish(name,result,failed,id) {
      const entry=this.entries.find(e=>e.id===id);
      if(!entry) return; // Ignore old-session results after a reset.
      entry.result=result || {}; entry.state=outcome(name,result,failed);
      if(entry.state==='draft') entry.expires=Date.now()+Math.min(120,Number(result.expires_in)||120)*1000;
      if(name==='suggest_follow_up' && result?.suggested && !failed) this.suggestions=result;
    }
    invalidateDraft() {
      for(const e of this.entries) if(e.state==='draft') e.state='superseded';
    }
    expire() { for(const e of this.entries) if(e.state==='draft' && e.expires<=Date.now()) e.state='expired'; }
    end() {
      for(const e of this.entries) {
        if(e.state==='pending') e.state=writes.has(e.name)?'uncertain':'stopped';
        if(e.state==='draft') e.state='expired';
      }
    }
  }
  function mount(host,onChoice,options) {
    const state=new DesktopState();
    // The rail above the workspace: what the worker said, what was read back,
    // what was recorded. Optional, so the module still mounts without it.
    const rail=options?.rail||null;
    const provenance=typeof options?.provenance==='function'?options.provenance:null;
    let said=null, recent=[];
    // Who exists, for the empty screen. Fetched by the page, never invented here.
    let directory=[];
    const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
    const add=(parent,...children)=>{parent.append(...children.filter(Boolean));return parent;};
    const words=value=>value === undefined || value === null || value === '' ? '—' : String(value);
    const fields=(items)=>{const list=node('dl','desktop-fields');for(const [key,value] of items) {if(value===undefined)continue;add(list,add(node('div'),node('dt','',key),node('dd','',words(value))));}return list;};
    const notice=(text,kind='')=>node('p','desktop-notice '+kind,text);
    const badge=(text)=>node('span','desktop-badge',text);
    function recordFields(d) {
      return fields([['Document',d.MBLNR],['Material',d.MATNR],['Description',d.MAKTX],['Quantity',d.MENGE===undefined?undefined:`${d.MENGE} ${d.MEINS||''}`],['Plant / Location',d.WERKS?`${d.WERKS} / ${d.LGORT||'—'}`:undefined],['Storage bin',d.LGPLA],['Reverses',d.reverses||d.document],['Stock after posting',d.new_stock_level===undefined?undefined:`${d.new_stock_level} ${d.MEINS||''}`]]);
    }
    function phone(entry) {
      const shell=node('div','work-phone'), screen=node('div','phone-screen');
      add(shell,node('div','phone-island'),screen);
      add(screen,node('small','phone-owner',"Lena’s work phone"),node('h3','',entry.name==='find_colleague'?'Work contacts':'Work call'));
      const result=entry.result||{}, data=result.record?.details||result.details;
      if(data?.recipient) {
        const p=data.recipient;
        add(screen,node('div','contact-avatar',p.name.split(' ').map(w=>w[0]).join('')),node('h4','',p.name),node('p','contact-role',p.role),node('p','contact-extension','Extension '+p.extension));
        if(data.purpose) add(screen,node('p','call-purpose',data.purpose));
        add(screen,node('div','phone-call-symbol','☎'));
        if(entry.state==='saved') add(screen,notice('Demo call logged','success'),node('small','',result.record.id));
        else if(entry.state==='draft') add(screen,notice('Say “confirm” to simulate this call.'));
      } else if(entry.state==='pending') add(screen,notice('Looking up your colleague…'));
      else for(const p of result.matches||[]) add(screen,add(node('article','contact-row'),node('span','contact-initial',p.name[0]),add(node('div'),node('strong','',p.name),node('small','',p.role+' · Ext. '+p.extension))));
      if(result.matches?.length===0) {
        add(screen,notice('No colleague matched. The whole demo directory:'));
        for(const person of result.directory||[]) add(screen,add(node('article','contact-row'),node('span','contact-initial',person.name[0]),add(node('div'),node('strong','',person.name),node('small','',person.role+' · Ext. '+person.extension))));
      }
      add(screen,node('p','device-disclaimer','Demo phone · no real call is placed.'));
      return shell;
    }
    function laptop(entry) {
      const note=category(entry.name)==='note', result=entry.result||{}, data=result.record?.details||result.details;
      const laptop=node('div','work-laptop'), screen=node('div','laptop-screen');
      add(laptop,screen,node('div','laptop-base'));
      add(screen,add(node('div','laptop-toolbar'),node('span','window-controls','● ● ●'),node('span','',note?'Lena’s notes':'Lena’s mail'),badge('DEMO')));
      add(screen,node('p','mail-folder',note?'WORK NOTES':entry.state==='saved'?'DEMO OUTBOX':'NEW MESSAGE'));
      if(data) {
        if(note) add(screen,node('h3','note-title',data.title));
        else add(screen,fields([['To',data.recipient.name],['Email',data.recipient.email],['Subject',data.subject]]));
        add(screen,node('p','mail-body',data.body));
      } else add(screen,notice(note?'Preparing your note…':'Preparing your message…'));
      if(entry.state==='draft') add(screen,notice(note?'Read back · say “confirm” to save this note.':'Read back · say “confirm” to save to the demo outbox.'));
      if(entry.state==='saved') add(screen,notice(note?'Saved to demo notes':'Saved to demo outbox','success'),node('small','record-reference',result.record.id));
      add(screen,node('p','device-disclaimer',note?'Demo notes · saved for this voice session.':'Demo mail · no email is delivered to a real person.'));
      return laptop;
    }
    function erp(entry) {
      const result=entry.result||{}, screen=node('div','erp-screen');
      add(screen,add(node('div','erp-toolbar'),node('strong','','GlovesOn ERP'),badge('MOCK')));
      if(entry.state==='pending') {add(screen,node('h3','',labels[entry.name]||'Working'),notice('Waiting for the system result…'));return screen;}
      if(entry.name==='get_stock' && result.found) {
        add(screen,node('small','document-kicker','MATERIAL STOCK'),node('h3','',result.MAKTX||result.MATNR),fields([['Material',result.MATNR],['Unrestricted stock',`${result.total_unrestricted} ${result.MEINS||''}`],['Plant',result.WERKS]]));
        for(const loc of result.locations||[]) add(screen,fields([['Bin',loc.LGPLA],['Storage location',loc.LGORT],['On hand',`${loc.LABST} ${loc.MEINS||result.MEINS||''}`]]));
        add(screen,notice('Stock checked. Nothing written.'));
      } else if(entry.name==='get_recent_documents') {
        add(screen,node('h3','','Recent material documents'));
        for(const d of result.documents||[]) add(screen,add(node('article','desktop-record'),recordFields(d)));
        if(!result.documents?.length)add(screen,notice('No matching documents.'));
      } else if(entry.name==='get_purchase_order' && result.found) {
        add(screen,node('h3','','Purchase order'),fields([['Order',result.EBELN],['Material',result.MATNR],['Quantity',result.MENGE],['Status',result.status],['Supplier',result.LIFNR]]));
      } else if(entry.name==='search_material') {
        add(screen,node('h3','','Material search'));
        for(const d of result.matches||[]) add(screen,fields([['Material',d.MATNR],['Description',d.MAKTX]]));
        if(!result.matches?.length)add(screen,notice('No matching materials.'));
      } else if(entry.name==='get_communication_history') {
        add(screen,node('h3','','This session’s activity'));
        for(const record of result.records||[]) add(screen,add(node('article','desktop-record'),node('strong','',record.id),node('p','',record.kind==='call'?'Demo call · '+record.details.recipient.name:record.details.subject||record.details.title),node('small','',record.status.replaceAll('_',' '))));
        if(!result.records?.length)add(screen,notice('No saved communications in this session.'));
      } else if(result.details && /prepare/.test(entry.name)) {
        const d=result.details;
        screen.classList.add('receipt-draft');
        const kicker=add(node('div','receipt-kicker'),node('small','document-kicker',entry.name==='prepare_reversal'?'REVERSAL DRAFT':'GOODS RECEIPT'),badge(stateText[entry.state]||'Not posted'));
        add(screen,kicker);
        const hero=add(node('div','receipt-material'),add(node('div'),node('h3','',d.MAKTX||'Material details'),node('p','','Material '+words(d.MATNR))));
        if(/hex bolts/i.test(d.MAKTX||'')) {
          const illustration=node('img','material-illustration');illustration.src='/assets/hex-bolts-studio.png';illustration.alt='';add(hero,illustration);
        }
        add(screen,hero,fields([['Quantity',d.MENGE===undefined?undefined:`${d.MENGE} ${d.MEINS||''}`],['Destination bin',d.LGPLA],['Plant',d.WERKS]]));
        if(d.LGORT || d.document || d.reverses)add(screen,node('p','receipt-context', [d.LGORT?'Storage location '+d.LGORT:'',d.document||d.reverses?'Original document '+(d.document||d.reverses):''].filter(Boolean).join(' · ')));
        if(entry.state==='draft')add(screen,notice('Review the details. Say “confirm” to '+(entry.name==='prepare_reversal'?'reverse.':'post.')));
        const steps=node('div','desktop-steps receipt-steps');
        for(const [i,label] of ['Speak','Review','Confirm'].entries()) {
          const step=add(node('div',i===1 && entry.state==='draft'?'active':''),node('span','',String(i+1)),node('small','',label));
          add(steps,step);
        }
        add(screen,steps);
      } else if(entry.state==='saved' && result.MBLNR) {
        add(screen,node('small','document-kicker','MATERIAL DOCUMENT'),node('h3','',result.reversed?'Reversal recorded':'Receipt recorded'),badge('SAVED IN MOCK ERP'),recordFields(result));
        // Before is derived from after and the quantity: a receipt adds, a
        // reversal takes back out. Both numbers come from the same tool result.
        if(result.new_stock_level!==undefined && result.MENGE!==undefined) {
          const after=Number(result.new_stock_level), qty=Number(result.MENGE);
          const before=result.reversed?after+qty:after-qty;
          add(screen,node('p','record-stock',`Stock ${before} → ${after} ${result.MEINS||''}`));
        }
        const why=entry.args?.confirmed_utterance;
        if(why) add(screen,add(node('div','record-why'),node('small','','WHY THIS DOCUMENT EXISTS'),node('p','','“'+String(why)+'”')));
      } else if(entry.name==='suggest_follow_up') {
        add(screen,node('h3','','A next step for this delivery'),notice('Choose how you would like to follow up. No action has been taken.'));
      } else if(entry.name==='search_mm_knowledge') {
        add(screen,node('h3','','MM reference'));
        for(const r of result.references||[])add(screen,node('p','',r.title));
      }
      if(['rejected','error'].includes(entry.state))add(screen,notice(typeof result.message==='string'?result.message:'The request could not be completed. Ask your guide to check.','error'));
      return screen;
    }
    const stateText={pending:'Working…',draft:'Your confirmation needed',saved:'Saved',read:'Checked',rejected:'Needs attention',error:'Could not finish',uncertain:'Result uncertain',expired:'Draft expired',superseded:'Draft replaced',submitted:'Draft used',stopped:'Stopped'};
    function render() {
      state.expire(); host.replaceChildren();
      // A kicker, not a title: the card below is the thing, this only names the surface.
      add(host,add(node('div','desktop-heading'),node('small','',"LENA’S WORKSPACE"),badge('Mock S/4HANA')));
      // No device tabs: the worker never chooses a device, the tool does. The
      // card shows whatever the current action is, and earlier ones are reached
      // through the session activity list below.
      if(!state.current) {
        const empty=add(node('div','desktop-empty'),node('small','document-kicker','MATERIAL DOCUMENT · NONE YET'),node('h3','','No document yet'),node('p','','What you confirm becomes the record here.'));
        add(host,empty);
        // Evidence that the system has done things, even on a quiet day: the
        // last documents in the mock ERP, each with the sentence behind it one
        // click away. This is the receipts idea, on the screen itself.
        if(recent.length) {
          const list=add(node('section','desktop-recent'),node('small','','RECENT DOCUMENTS · WHY EACH ONE EXISTS'));
          for(const d of recent.slice(0,4)) {
            const row=node('div','recent-row');
            // The movement type in words as well as the code: 501 means nothing to
            // a reader who has not lived in MM, and "receipt" is what it means.
            const kind={'101':'receipt','501':'receipt','102':'reversal','502':'reversal'}[String(d.BWART)]||'movement';
            add(row,node('span','recent-number',d.MBLNR),node('span','recent-type',`${d.BWART} · ${kind}`),node('span','recent-what',`${words(d.MENGE)} ${d.MEINS||''} · material ${d.MATNR}${d.LGPLA?' · bin '+d.LGPLA:''}`));
            if(provenance) {
              const why=node('button','recent-why','why ↗');why.type='button';
              why.onclick=async()=>{why.disabled=true;let row_=null;try{row_=await provenance(d.MBLNR);}catch{row_=null;}
                const said=row_?.voice?.utterance;const line=add(node('p','recent-reason'),node('span','recent-reason-label','Confirmed with'),node('span','',said?('“'+said+'”'):'No provenance row for this document.'));
                row.after(line);why.remove();};
              add(row,why);
            }
            add(list,row);
          }
          add(host,list);
        }
      } else {
        const entry=state.current;
        add(host,add(node('div','desktop-status '+entry.state),node('span','',labels[entry.name]||'Workspace'),node('strong','',stateText[entry.state])));
        const device=node('div','desktop-device');
        add(device,category(entry.name)==='phone'?phone(entry):['email','note'].includes(category(entry.name))?laptop(entry):erp(entry));add(host,device);
        if(entry.state==='submitted')add(host,notice('This draft was already used. Check the result in session activity.'));
        if(entry.state==='uncertain')add(host,notice('The result could not be verified. Ask GlovesOn to check records before trying again.','error'));
        if(['expired','superseded','stopped'].includes(entry.state))add(host,notice('This draft or request is no longer active. Ask GlovesOn to prepare it again.'));
        if(['error','rejected'].includes(entry.state) && ['phone','email','note'].includes(category(entry.name)))add(host,notice(entry.result?.message||'The request could not be completed.','error'));
      }
      if(state.suggestions) {
        const box=node('section','desktop-suggestions');
        add(box,node('h3','','What would you like to do?'),node('p','',state.suggestions.reason));
        // The gateway decides who this belongs to; the buttons say the name so
        // the worker can disagree with it before anything is drafted.
        const to=state.suggestions.recipient;
        if(to) add(box,node('p','follow-up-recipient',to.name+' · '+to.role+' — '+state.suggestions.because));
        const options=node('div','follow-up-options');
        const labels=[['call_colleague',to?'Call '+to.name:'Call a colleague'],['draft_email',to?'Email '+to.name:'Draft email'],['save_note','Save a note']];
        for(const [key,label] of labels) {
          const button=node('button','',label);button.type='button';button.onclick=()=>onChoice(key);add(options,button);
        }
        add(box,options,node('small','','Choose here or tell GlovesOn. Nothing happens until you confirm.'));add(host,box);
      }
      if(state.entries.length) {
        const history=node('details','desktop-activity');add(history,node('summary','','Session activity · '+state.entries.length));
        const list=node('ol');
        for(const e of state.entries.slice().reverse()) {
          const button=node('button','',`${labels[e.name]||e.name} · ${stateText[e.state]}`);button.type='button';button.onclick=()=>{state.current=e;render();};add(list,add(node('li'),button));
        }add(history,list);add(host,history);
      }
      // Who can be reached, in one line, instead of a drawer to open.
      if(directory.length) add(host,node('p','desktop-reach','REACH · '+directory.map(person=>person.name+' ('+person.role.toLowerCase()+')').join(' · ')));
      add(host,node('p','desktop-footnote','Live tool results · demo records only. No real SAP, email delivery or phone connection.'));
      renderRail();
    }
    // --- The rail --------------------------------------------------------
    // Three cells, always present, so the discipline is visible before anyone
    // speaks. The read-back cell draws from the tool's returned details, which
    // are the facts the agent is required to read aloud; the exact spoken
    // sentence stays in the transcript. Nothing here is invented from the
    // model's reply.
    function cell(key){return rail?rail.querySelector('[data-cell="'+key+'"]'):null;}
    function setCell(key,cls,text,meta,chips) {
      const el=cell(key); if(!el) return;
      el.className='rail-cell'+(cls?' '+cls:'');
      el.querySelector('.rail-text').textContent=text;
      const m=el.querySelector('.rail-meta'); if(m) m.textContent=meta||'';
      const c=el.querySelector('.rail-chips'); if(c){c.replaceChildren();for(const chip of chips||[]) if(chip) add(c,node('span','',chip));}
    }
    function readback(entry) {
      const d=entry.result?.details||{}, who=d.recipient?.name;
      if(entry.name==='prepare_reversal') return {text:`Reverse document ${d.document||d.reverses||'—'}: ${words(d.MENGE)} ${d.MEINS||''} of ${d.MAKTX||'—'} back out of bin ${d.LGPLA||'—'}. Confirm?`,chips:[d.MENGE!==undefined?`${d.MENGE} ${d.MEINS||''}`:'',d.MAKTX,d.LGPLA?'Bin '+d.LGPLA:'']};
      if(entry.name==='prepare_goods_receipt') return {text:`${words(d.MENGE)} ${d.MEINS||''} of ${d.MAKTX||'—'} into bin ${d.LGPLA||'—'}. Confirm?`,chips:[d.MENGE!==undefined?`${d.MENGE} ${d.MEINS||''}`:'',d.MAKTX,d.LGPLA?'Bin '+d.LGPLA:'']};
      if(entry.name==='prepare_email') return {text:`Email ${who||'—'}: “${d.subject||''}”. Confirm?`,chips:[who?'To '+who:'',d.subject]};
      if(entry.name==='prepare_call') return {text:`Call ${who||'—'}${d.purpose?' about '+d.purpose:''}. Confirm?`,chips:[who?'Call '+who:'',d.purpose]};
      if(entry.name==='prepare_note') return {text:`Save the note “${d.title||''}”. Confirm?`,chips:[d.title]};
      return {text:'Read back before anything is written.',chips:[]};
    }
    function countdown(at){const s=Math.max(0,Math.round((at-Date.now())/1000));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}
    function renderRail() {
      if(!rail) return;
      const latest=state.entries.slice().reverse();
      const draft=latest.find(e=>e.state==='draft');
      const used=latest.find(e=>e.state==='submitted');
      const write=latest.find(e=>writes.has(e.name)&&['saved','rejected','uncertain','pending'].includes(e.state));
      if(said) setCell('said','is-live','“'+said+'”',''); else setCell('said','','Your words, as heard.','');
      const source=draft||used;
      if(source){const r=readback(source);setCell('readback',draft?'is-waiting':'is-live',r.text,'',r.chips);}
      else setCell('readback','','Every write is read back: quantity, unit, description, bin.','',[]);
      if(write&&write.state==='saved') {
        const r=write.result||{};
        const what=r.MBLNR?('Material document '+r.MBLNR+(r.reverses?' reverses '+r.reverses:'')):('Saved · '+(r.record?.id||''));
        setCell('recorded','is-saved',what,r.new_stock_level!==undefined?`Stock now ${r.new_stock_level} ${r.MEINS||''}`:'');
      } else if(write&&write.state==='rejected') {
        const r=write.result||{};
        setCell('recorded','is-refused','Refused. '+(r.duplicate?`This exact posting already went through as ${r.MBLNR}. Nothing was posted twice.`:(r.message||'Nothing was recorded.')),'');
      } else if(write&&write.state==='uncertain') setCell('recorded','is-refused','Result uncertain. Records are checked before anything is tried again.','');
      else if(write&&write.state==='pending') setCell('recorded','is-waiting','Posting…','');
      else if(draft) setCell('recorded','','Nothing yet. Say yes to post it. Anything else posts nothing.',draft.expires?'Draft expires in '+countdown(draft.expires):'');
      else setCell('recorded','','Nothing yet. Only a spoken yes posts the document.','');
    }
    const interval=setInterval(()=>{const was=state.entries.map(e=>e.state).join();state.expire();if(was!==state.entries.map(e=>e.state).join())render();else if(state.entries.some(e=>e.state==='draft'))renderRail();},1000);
    render();
    return {
      state,render,
      begin(name,id,args){state.begin(name,id,args);render();},
      finish(name,result,failed,id){state.finish(name,result,failed,id);render();},
      reset(){state.reset();said=null;render();},
      said(text){said=typeof text==='string'&&text.trim()?text.trim():null;renderRail();},
      invalidateDraft(){state.invalidateDraft();render();},
      dismissSuggestions(){state.suggestions=null;render();},
      setDirectory(list){directory=Array.isArray(list)?list:[];render();},
      setRecent(list){recent=Array.isArray(list)?list:[];render();},
      end(){state.end();render();},
      destroy(){clearInterval(interval);}
    };
  }
  root.GlovesOnDesktop={DesktopState,outcome,mount};
  if(typeof module!=='undefined')module.exports=root.GlovesOnDesktop;
})(globalThis);
