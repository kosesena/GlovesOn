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
    begin(name,id) {
      if (this.entries.some(e=>e.id===id)) return;
      // A new preparation replaces the only pending draft, across every device.
      if (name.startsWith('prepare_') || writes.has(name)) for (const entry of this.entries) if(entry.state==='draft') entry.state=writes.has(name)?'submitted':'superseded';
      if (/^prepare_(email|call|note)$/.test(name)) this.suggestions=null;
      const entry={name,id,state:'pending',result:null};
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
  function mount(host,onChoice) {
    const state=new DesktopState();
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
      if(result.matches?.length===0) add(screen,notice('No colleague found. Try a name or role.'));
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
        add(screen,node('small','document-kicker','DRAFT · NOT POSTED'),node('h3','',entry.name==='prepare_reversal'?'Reverse a receipt':'Receive a delivery'),recordFields(result.details));
        if(entry.state==='draft')add(screen,notice('Check the details. Say “confirm” to record them.'));
      } else if(entry.state==='saved' && result.MBLNR) {
        add(screen,node('small','document-kicker','MATERIAL DOCUMENT'),node('h3','',result.reversed?'Reversal recorded':'Receipt recorded'),badge('SAVED IN MOCK ERP'),recordFields(result));
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
      add(host,add(node('div','desktop-heading'),add(node('div'),node('small','',"LENA’S WORKSPACE"),node('h2','','See it happen')),badge('Mock environment')));
      if(!state.current) {
        add(host,add(node('div','desktop-empty'),node('div','desktop-empty-symbol','↗'),node('h3','','Your words. Work in motion.'),node('p','','Ask Lena to receive a delivery, email a colleague or make a work call.'),node('div','desktop-device-list','ERP records  /  Work phone  /  Mail')));
      } else {
        const entry=state.current;
        add(host,add(node('div','desktop-status '+entry.state),node('span','',labels[entry.name]||'Workspace'),node('strong','',stateText[entry.state])));
        const device=node('div','desktop-device');
        add(device,category(entry.name)==='phone'?phone(entry):['email','note'].includes(category(entry.name))?laptop(entry):erp(entry));add(host,device);
        if(entry.state==='submitted')add(host,notice('This draft was already used. Check the result in session activity.'));
        if(entry.state==='uncertain')add(host,notice('The result could not be verified. Ask Lena to check records before trying again.','error'));
        if(['expired','superseded','stopped'].includes(entry.state))add(host,notice('This draft or request is no longer active. Ask Lena to prepare it again.'));
        if(['error','rejected'].includes(entry.state) && ['phone','email','note'].includes(category(entry.name)))add(host,notice(entry.result?.message||'The request could not be completed.','error'));
      }
      if(state.suggestions) {
        const box=node('section','desktop-suggestions');
        add(box,node('h3','','What would you like to do?'),node('p','',state.suggestions.reason));
        const options=node('div','follow-up-options');
        for(const [key,label] of [['call_supervisor','Call supervisor'],['draft_email','Draft email'],['save_note','Save a note']]) {
          const button=node('button','',label);button.type='button';button.onclick=()=>onChoice(key);add(options,button);
        }
        add(box,options,node('small','','Choose here or tell Lena. Nothing happens until you confirm.'));add(host,box);
      }
      if(state.entries.length) {
        const history=node('details','desktop-activity');add(history,node('summary','','Session activity · '+state.entries.length));
        const list=node('ol');
        for(const e of state.entries.slice().reverse()) {
          const button=node('button','',`${labels[e.name]||e.name} · ${stateText[e.state]}`);button.type='button';button.onclick=()=>{state.current=e;render();};add(list,add(node('li'),button));
        }add(history,list);add(host,history);
      }
      add(host,node('p','desktop-footnote','Live tool results · demo records only. No real SAP, email delivery or phone connection.'));
    }
    const interval=setInterval(()=>{const was=state.entries.map(e=>e.state).join();state.expire();if(was!==state.entries.map(e=>e.state).join())render();},1000);
    render();
    return {
      state,render,
      begin(name,id){state.begin(name,id);render();},
      finish(name,result,failed,id){state.finish(name,result,failed,id);render();},
      reset(){state.reset();render();},
      invalidateDraft(){state.invalidateDraft();render();},
      dismissSuggestions(){state.suggestions=null;render();},
      end(){state.end();render();},
      destroy(){clearInterval(interval);}
    };
  }
  root.GlovesOnDesktop={DesktopState,outcome,mount};
  if(typeof module!=='undefined')module.exports=root.GlovesOnDesktop;
})(globalThis);
