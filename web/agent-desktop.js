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
      const entry={name,id,state:'pending',result:null,args:parsed,at:Date.now(),doneAt:null};
      this.entries.push(entry); this.entries=this.entries.slice(-20); this.current=entry;
    }
    finish(name,result,failed,id) {
      const entry=this.entries.find(e=>e.id===id);
      if(!entry) return; // Ignore old-session results after a reset.
      entry.result=result || {}; entry.state=outcome(name,result,failed); entry.doneAt=Date.now();
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
    const stream=options?.stream||null;
    const provenance=typeof options?.provenance==='function'?options.provenance:null;
    let saidLog=[], recent=[];
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
    const clock=ms=>{const d=new Date(ms);return [d.getHours(),d.getMinutes(),d.getSeconds()].map(n=>String(n).padStart(2,'0')).join(':');};
    const countdown=at=>{const s=Math.max(0,Math.round((at-Date.now())/1000));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;};
    const isWrite=e=>writes.has(e.name), isPrepare=e=>/^prepare_/.test(e.name);
    const stockBefore=r=>{if(r.new_stock_level===undefined||r.MENGE===undefined)return null;const after=Number(r.new_stock_level),qty=Number(r.MENGE);return {before:r.reversed?after+qty:after-qty,after};};
    // What the agent is required to read aloud, from the tool's own details.
    function readback(entry) {
      const d=entry.result?.details||{}, who=d.recipient?.name;
      if(entry.name==='prepare_reversal') return {big:`Reverse ${d.document||d.reverses||'—'}: ${words(d.MENGE)} ${d.MEINS||''} of ${d.MAKTX||'—'} out of bin ${d.LGPLA||'—'}.`,chips:[d.MENGE!==undefined?`${d.MENGE} ${d.MEINS||''}`:'',d.MAKTX,d.LGPLA?'Bin '+d.LGPLA:'']};
      if(entry.name==='prepare_goods_receipt') return {big:`${words(d.MENGE)} ${d.MEINS||''} of ${d.MAKTX||'—'} into bin ${d.LGPLA||'—'}.`,chips:[d.MENGE!==undefined?`${d.MENGE} ${d.MEINS||''}`:'',d.MAKTX,d.LGPLA?'Bin '+d.LGPLA:'']};
      if(entry.name==='prepare_email') return {big:`Email ${who||'—'}: “${d.subject||''}”`,chips:[who?'To '+who:'',d.subject]};
      if(entry.name==='prepare_call') return {big:`Call ${who||'—'}${d.purpose?' about '+d.purpose:''}.`,chips:[who?'Call '+who:'',d.purpose]};
      if(entry.name==='prepare_note') return {big:`Save the note “${d.title||''}”.`,chips:[d.title]};
      return {big:'Read back before anything is written.',chips:[]};
    }
    const kickers={erp:'GOODS RECEIPT · MATERIAL DOCUMENT · MOCK S/4HANA',reversal:'REVERSAL · MATERIAL DOCUMENT · MOCK S/4HANA',email:'DEMO MAIL · LENA’S WORK LAPTOP · NO REAL DELIVERY',phone:'DEMO CALL · LENA’S WORK PHONE · NO REAL CALL',note:'DEMO NOTE · LENA’S WORK LAPTOP',history:'THIS SESSION · DEMO COMMUNICATIONS'};
    function stampFor(entry) {
      if(!entry) return null;
      const c=category(entry.name), st=entry.state;
      const draftWords={erp:'NOT YET POSTED',email:'NOT YET SENT',phone:'NOT YET PLACED',note:'NOT YET SAVED'};
      const savedWords={email:'SAVED TO OUTBOX',phone:'CALL LOGGED',note:'NOTE SAVED'};
      if(st==='draft'||st==='pending'&&isWrite(entry)) return {text:draftWords[c]||'NOT YET POSTED',tone:'wait'};
      if(st==='saved') return {text:c==='erp'?`POSTED · ${entry.result?.BWART||''}`.trim():savedWords[c],tone:'saved'};
      if(st==='rejected'||st==='uncertain'||st==='error'&&isWrite(entry)) return {text:c==='erp'?'NOT POSTED':'NOT SAVED',tone:'refused'};
      return null;
    }
    // --- The sheet: the record, whatever state it is in --------------------
    function render() {
      state.expire(); host.replaceChildren();
      const entry=state.current, c=entry?category(entry.name):'erp';
      const sheet=node('div','desk-sheet');
      const stamp=stampFor(entry);
      if(stamp) add(sheet,node('div','desk-stamp is-'+stamp.tone,stamp.text));
      const kicker=entry?(entry.name==='prepare_reversal'||entry.result?.reversed?kickers.reversal:kickers[c]||kickers.erp):'MATERIAL DOCUMENT · MOCK S/4HANA';
      add(sheet,node('small','desk-kicker',kicker));
      // The number line: dashes until the system assigns one.
      if(!entry||c==='erp'&&!/^(get_|search_)/.test(entry.name)) {
        const r=entry?.result||{};
        const line=node('div','desk-number');
        if(entry?.state==='saved'&&r.MBLNR) add(line,node('span','desk-number-label','Document'),node('span','desk-number-value',r.MBLNR),node('span','desk-number-note','✓ assigned '+clock(entry.doneAt||Date.now())));
        else add(line,node('span','desk-number-label','Document'),node('span','desk-number-blank','— — — — — — — — — —'),node('span','desk-number-note','assigned when you say yes'));
        add(sheet,line);
      } else if(entry.state==='saved'&&entry.result?.record?.id) {
        add(sheet,add(node('div','desk-number'),node('span','desk-number-label','Record'),node('span','desk-number-value',entry.result.record.id),node('span','desk-number-note','✓ saved '+clock(entry.doneAt||Date.now()))));
      }
      // The band: the moment the sheet is in.
      if(entry&&entry.state==='draft') {
        const rb=readback(entry);
        const band=add(node('div','desk-band is-wait'),add(node('div','desk-band-head'),add(node('span','desk-band-eyebrow'),node('i','desk-dot is-pulse'),node('span','','READ BACK · WAITING FOR YOUR YES')),node('span','desk-band-time',clock(entry.doneAt||entry.at)+(entry.expires?' · expires in '+countdown(entry.expires):''))));
        add(band,add(node('p','desk-band-big'),node('span','',rb.big+' '),node('span','desk-band-ask','Confirm?')),node('span','desk-band-hint',c==='erp'?'Say yes to post. Say a number to change it. Anything else posts nothing.':'Say yes to save it. Say a change and it is drafted again. Nothing reaches a real person.'));
        add(sheet,band);
      } else if(entry&&entry.state==='pending'&&isWrite(entry)) {
        add(sheet,add(node('div','desk-band is-wait'),add(node('div','desk-band-head'),add(node('span','desk-band-eyebrow'),node('i','desk-dot is-pulse'),node('span','',c==='erp'?'POSTING':'SAVING')),node('span','desk-band-time',clock(entry.at))),node('p','desk-band-big','Waiting for the system to answer.')));
      } else if(entry&&entry.state==='saved'&&isWrite(entry)) {
        const r=entry.result||{}, sb=stockBefore(r);
        const band=add(node('div','desk-band is-saved'),add(node('div','desk-band-head'),add(node('span','desk-band-eyebrow'),node('i','desk-dot is-done'),node('span','','RECORDED · '+clock(entry.doneAt||Date.now()))),node('span','desk-band-time',sb?`stock ${sb.before} → ${sb.after} ${r.MEINS||''}`:'')));
        add(band,node('p','desk-band-big',c==='erp'?(r.reversed?`${words(r.MENGE)} ${r.MEINS||''} of ${r.MAKTX||''} are back out of bin ${r.LGPLA||''}.`:`${words(r.MENGE)} ${r.MEINS||''} of ${r.MAKTX||''} are in bin ${r.LGPLA||''}.`):(c==='email'?'Saved to the demo outbox. No email was delivered to a real person.':c==='phone'?'Demo call logged. No phone rang anywhere.':'Note saved for this session.')));
        add(band,node('span','desk-band-hint',c==='erp'?(r.reversed?'Both documents stay in the record.':'Wrong? Say “reverse it”. A reversal takes them back out and both documents stay.'):'Check it under session activity any time.'));
        add(sheet,band);
      } else if(entry&&['rejected','uncertain','error'].includes(entry.state)&&isWrite(entry)) {
        const r=entry.result||{};
        const text=entry.state==='uncertain'?'The result could not be verified. Records are checked before anything is tried again.':(r.duplicate?`This exact posting already went through as ${r.MBLNR}. Nothing was posted twice.`:(typeof r.message==='string'?r.message:'Nothing was recorded.'));
        add(sheet,add(node('div','desk-band is-refused'),add(node('div','desk-band-head'),add(node('span','desk-band-eyebrow'),node('i','desk-dot is-refused'),node('span','',entry.state==='uncertain'?'RESULT UNCERTAIN':'REFUSED · '+clock(entry.doneAt||Date.now())))),node('p','desk-band-big',text),node('span','desk-band-hint','Nothing is recorded. A new read-back starts from what you say next.')));
      } else if(!entry) {
        add(sheet,add(node('div','desk-band is-idle'),add(node('div','desk-band-head'),add(node('span','desk-band-eyebrow'),node('i','desk-dot'),node('span','','NOTHING ON THE TABLE'))),node('p','desk-band-big','Say what arrived.'),node('span','desk-band-hint','Lena looks the material up, reads the receipt back, and writes nothing until you say yes.')));
      }
      // The body: the document's fields, or the device the action lives on.
      if(entry&&c==='erp'&&(entry.state==='draft'&&isPrepare(entry)||entry.state==='saved'&&isWrite(entry)||['rejected','uncertain'].includes(entry.state)&&isWrite(entry))) {
        const d=entry.state==='draft'?(entry.result?.details||{}):(entry.result||{});
        const grid=node('div','desk-fields');
        const cell=(label,value,hint,cls)=>add(grid,add(node('div','desk-field'+(cls?' '+cls:'')),add(node('span','desk-field-label'),node('span','',label),hint?node('span','desk-field-hint',hint):null),node('span','desk-field-value',words(value))));
        cell('Material',d.MATNR,entry.state==='saved'?'✓':'✓ looked up');
        cell('Description',d.MAKTX,'✓ material master','is-wide');
        cell('Quantity',d.MENGE!==undefined?`${d.MENGE} ${d.MEINS||''}`:undefined,entry.state==='draft'?'being confirmed':(entry.state==='saved'?'✓ confirmed':'not posted'),entry.state==='draft'?'is-confirming':'');
        cell('Storage bin',d.LGPLA,'✓ the material’s own');
        cell('Plant / location',d.WERKS?`${d.WERKS} / ${d.LGORT||'—'}`:undefined,'✓ default');
        if(d.document||d.reverses) cell('Reverses',d.document||d.reverses,'✓ the original stays');
        if(entry.state==='saved'){const sb=stockBefore(entry.result||{});if(sb)cell('Stock',`${sb.before} → ${sb.after} ${d.MEINS||''}`,'✓ from the same result');}
        add(sheet,grid);
        const why=entry.args?.confirmed_utterance;
        if(entry.state==='saved'&&why) add(sheet,add(node('div','desk-why'),node('small','','WHY THIS DOCUMENT EXISTS'),node('p','','“'+String(why)+'” — as the agent reported it, '+clock(entry.doneAt||Date.now())+'.')));
      } else if(entry&&entry.state==='pending'&&!isWrite(entry)) {
        add(sheet,node('p','desk-quiet',(labels[entry.name]||'Working')+'…'));
      } else if(entry&&c==='phone') add(sheet,add(node('div','desktop-device'),phone(entry)));
      else if(entry&&['email','note'].includes(c)) add(sheet,add(node('div','desktop-device'),laptop(entry)));
      else if(entry&&entry.state!=='draft') add(sheet,add(node('div','desktop-device'),erp(entry)));
      if(state.suggestions) {
        const box=node('section','desktop-suggestions');
        add(box,node('h3','','What would you like to do?'),node('p','',state.suggestions.reason));
        const to=state.suggestions.recipient;
        if(to) add(box,node('p','follow-up-recipient',to.name+' · '+to.role+' — '+state.suggestions.because));
        const options=node('div','follow-up-options');
        for(const [key,label] of [['call_colleague',to?'Call '+to.name:'Call a colleague'],['draft_email',to?'Email '+to.name:'Draft email'],['save_note','Save a note']]) {
          const button=node('button','',label);button.type='button';button.onclick=()=>onChoice(key);add(options,button);
        }
        add(box,options,node('small','','Choose here or tell Lena. Nothing happens until you confirm.'));add(sheet,box);
      }
      // The ledger: what the mock ERP holds today, each with its sentence a click away.
      const ledger=add(node('div','desk-ledger'),add(node('div','desk-ledger-head'),node('small','','TODAY IN THE LEDGER'),node('span','desk-ledger-note','why each one exists ↗')));
      if(recent.length) {
        const kinds={'101':'receipt','501':'receipt','102':'reversal','502':'reversal'};
        for(const d of recent.slice(0,4)) {
          const stub=add(node('div','desk-stub'),node('span','desk-stub-number',d.MBLNR),node('span','desk-stub-what',`${d.BWART} · ${kinds[String(d.BWART)]||'movement'} · ${words(d.MENGE)} ${d.MEINS||''} ${d.MATNR}`));
          if(provenance) {
            const why=node('button','desk-stub-why','why');why.type='button';
            why.onclick=async()=>{why.disabled=true;let row=null;try{row=await provenance(d.MBLNR);}catch{row=null;}
              const said=row?.voice?.utterance;add(stub,add(node('p','desk-stub-reason'),node('span','desk-stub-reason-label','Confirmed with'),node('span','',said?('“'+said+'”'):'No provenance row for this document.')));why.remove();};
            add(stub,why);
          }
          add(ledger,stub);
        }
      } else add(ledger,node('p','desk-quiet','No documents in the ledger yet.'));
      add(sheet,ledger);
      if(directory.length) add(sheet,node('p','desktop-reach','REACH · '+directory.map(person=>person.name+' ('+person.role.toLowerCase()+')').join(' · ')));
      add(sheet,node('p','desktop-footnote','Live tool results · demo records only. No real SAP, email delivery or phone connection.'));
      add(host,sheet);
      renderStream();
      host.dispatchEvent(new CustomEvent('gloveson:desktop'));
    }
    // --- The stream: everything this action did, in order, with the time ---
    function streamItems() {
      const items=[];
      for(const s of saidLog) items.push({at:s.at,title:'You said',text:'“'+s.text+'”',tone:'done'});
      for(const e of state.entries) {
        const r=e.result||{}, c=category(e.name), d=r.details||{};
        if(e.state==='pending') { items.push({at:e.at,title:labels[e.name]||e.name,text:'Waiting for the system…',tone:'wait',entry:e}); continue; }
        if(isPrepare(e)) {
          const waiting=e.state==='draft';
          const after={superseded:'Draft replaced by a new read-back.',expired:'Draft expired. Nothing was recorded.',submitted:'Confirmed.'}[e.state];
          items.push({at:e.doneAt||e.at,title:'Read back',text:waiting?(c==='erp'?'Four facts, aloud. Waiting for your yes.':c==='email'?'Recipient, subject and body, aloud. Waiting for your yes.':c==='phone'?'Who and why, aloud. Waiting for your yes.':'Title and text, aloud. Waiting for your yes.'):(after||readback(e).big),tone:waiting?'wait':(e.state==='rejected'?'refused':'done'),entry:e});
          continue;
        }
        if(isWrite(e)) {
          if(e.state==='saved') { const sb=stockBefore(r); items.push({at:e.doneAt||e.at,title:c==='erp'?(r.reversed?'Reversed':'Posted'):c==='email'?'Saved to outbox':c==='phone'?'Call logged':'Note saved',text:c==='erp'?`Material document ${r.MBLNR}${sb?` · stock ${sb.before} → ${sb.after} ${r.MEINS||''}`:''}`:(r.record?.id||''),tone:'done',entry:e}); }
          else items.push({at:e.doneAt||e.at,title:e.state==='uncertain'?'Result uncertain':'Refused',text:r.duplicate?`Already posted as ${r.MBLNR}. Nothing posted twice.`:(typeof r.message==='string'?r.message:'Nothing was recorded.'),tone:'refused',entry:e});
          continue;
        }
        if(e.name==='get_stock') items.push({at:e.doneAt||e.at,title:r.found?'Looked up '+(r.MATNR||''):'Not found',text:r.found?`${r.MAKTX||''} · bin ${r.locations?.[0]?.LGPLA||'—'} · ${words(r.total_unrestricted)} ${r.MEINS||''} on hand`:(r.message||''),tone:r.found?'done':'refused',entry:e});
        else if(e.name==='suggest_follow_up') items.push({at:e.doneAt||e.at,title:'Follow-up',text:r.recipient?`${r.because} → ${r.recipient.name}`:'Options offered.',tone:'done',entry:e});
        else if(e.name==='find_colleague') items.push({at:e.doneAt||e.at,title:'Looked up a colleague',text:(r.matches||[]).map(m=>m.name).join(', ')||'No match; the whole directory offered.',tone:'done',entry:e});
        else items.push({at:e.doneAt||e.at,title:labels[e.name]||e.name,text:stateText[e.state]||'',tone:e.state==='error'||e.state==='rejected'?'refused':'done',entry:e});
      }
      items.sort((a,b)=>a.at-b.at);
      return items.slice(-7);
    }
    function renderStream() {
      if(!stream) return;
      stream.replaceChildren();
      const items=streamItems();
      const draft=state.entries.slice().reverse().find(e=>e.state==='draft');
      const busy=state.entries.some(e=>e.state==='pending');
      const last=state.entries[state.entries.length-1];
      const status=draft||busy?'LIVE':(last&&last.state==='saved'?'DONE':'READY');
      add(stream,add(node('div','stream-head'),node('small','','THIS ACTION'),add(node('span','stream-live is-'+status.toLowerCase()),node('i','desk-dot '+(status==='LIVE'?'is-pulse':'is-done')),node('span','',status+' · '+clock(Date.now()).slice(0,5)))));
      const list=node('div','stream-list');
      if(!items.length) add(list,add(node('div','stream-item is-next'),node('span','stream-time','now'),node('i','stream-dot'),node('div','stream-title','You said'),node('div','stream-text','Say what arrived; it appears here with the time.')));
      for(const it of items) {
        const row=add(node('div','stream-item is-'+it.tone),node('span','stream-time',clock(it.at)),node('i','stream-dot'),node('div','stream-title',it.title),node('div','stream-text',it.text));
        if(it.entry){row.classList.add('is-link');row.onclick=()=>{state.current=it.entry;render();};}
        add(list,row);
      }
      // The ghost: what the next line will be, and what it takes.
      let next=null;
      if(draft) next=['Posted',category(draft.name)==='erp'?'A document number, the moment you say yes. Anything else, and this line never exists.':'A record id, the moment you say yes. Nothing reaches a real person.'];
      else if(last&&last.state==='saved'&&category(last.name)==='erp'&&!last.result?.reversed) next=['Reversal','Only if you ask. A reversal against this document; both stay.'];
      else if(items.length) next=['Next','Say what arrived, or ask for stock.'];
      if(next) add(list,add(node('div','stream-item is-next'),node('span','stream-time','next'),node('i','stream-dot'),node('div','stream-title',next[0]),node('div','stream-text',next[1])));
      add(stream,list);
      // Newest at the bottom, and the bottom in view.
      stream.scrollTop=stream.scrollHeight;
    }
    const interval=setInterval(()=>{const was=state.entries.map(e=>e.state).join();state.expire();if(was!==state.entries.map(e=>e.state).join())render();else if(state.entries.some(e=>e.state==='draft'))render();},1000);
    render();
    return {
      state,render,
      begin(name,id,args){state.begin(name,id,args);render();},
      finish(name,result,failed,id){state.finish(name,result,failed,id);render();},
      reset(){state.reset();saidLog=[];render();},
      said(text){if(typeof text==='string'&&text.trim()){saidLog.push({text:text.trim(),at:Date.now()});saidLog=saidLog.slice(-8);}renderStream();},
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
