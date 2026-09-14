/* Conversation policy is separate from rendering so transport regressions can run offline. */
(function(root) {
  'use strict';
  const writes = new Set(['post_goods_receipt', 'reverse_goods_receipt', 'send_email', 'place_call', 'save_note']);
  const prepareToWrite = {prepare_goods_receipt:'post_goods_receipt', prepare_reversal:'reverse_goods_receipt', prepare_email:'send_email', prepare_call:'place_call', prepare_note:'save_note'};
  class VoicePolicy {
    constructor(config, catalog, now = () => Date.now()) {
      this.config = config;
      this.catalog = catalog || config.tools || [];
      this.now = now;
      this.draft = null;
      this.uncertain = false;
      this.context = [];
      this.call = null;
      this.basePrompt = config.system_prompt || "";
    }
    user(text) {
      if (this.call && /^(?:(?:please|okay|ok|thanks(?:[, ]+Alex)?)[,. ]+)?(?:end (?:the )?call|hang up|goodbye|bye)[.!]?$/i.test(text.trim())) this.endCall();
      if (!/^(yes|confirm|yes[ ,]+confirm|i confirm)[.!]?$/i.test(text.trim())) this.draft = null;
    }
    begin(name) {
      if (writes.has(name) || prepareToWrite[name]) this.draft = null;
    }
    result(name, data, failed) {
      if (writes.has(name) && (failed || data.error)) this.uncertain = true;
      if (prepareToWrite[name]) {
        this.draft = !failed && data.prepared && data.draft_token
          ? {tool:prepareToWrite[name], expires:this.now()+115000} : null;
      }
      if (name === 'place_call' && !failed && data.completed === true && data.simulated === true &&
          data.record?.status === 'simulated_call_logged' && data.record?.details?.recipient?.id === 'alex' &&
          /damag|broken|broke|crack|torn/i.test(data.record.details.purpose || '')) {
        this.call = {name:'Alex Morgan'};
        this.draft = null;
      }
      // Only known result fields supply vocabulary; no arbitrary tool text becomes instructions.
      const items = data.matches || (data.MAKTX ? [data] : []);
      this.context = items.slice(0,12).flatMap(item => [item.MATNR, item.MAKTX, ...(name === 'find_colleague' ? [item.name] : [])])
        .filter(value => typeof value === 'string' && value.length <= 80);
    }
    endCall() { this.call = null; this.draft = null; }
    allows(name) {
      if (this.call) return false;
      if (this.uncertain && (writes.has(name) || prepareToWrite[name])) return false;
      return !writes.has(name) || Boolean(this.draft && this.draft.expires > this.now() && this.draft.tool === name);
    }
    update() {
      return {system_prompt:(this.call ? '\n\nACTIVE FICTIONAL CALL SIMULATION — ALEX MORGAN\nThe confirmed demo call has been logged. You now voice fictional Alex, not GlovesOn, for a damaged-delivery practice conversation. No real person has answered. Begin once: "Simulated call. Hi Lena, Alex here. What happened?" Then wait for the worker. Ask one relevant question at a time: which items, then how many are damaged, only if not already clear from the worker. If a number or item is unclear, ask again; never guess. Never speak the worker’s part. After the facts are clear, say: "Keep those items aside if it is safe to do so, and follow the site damage procedure. Say end call when you are ready." Do not claim to move stock, send anyone, notify a person, save a note, or take any other action. All tools are disabled during this simulation. Handle corrections naturally. If asked to do an operation, ask the worker to end the call first. This is role-play, never a real call, medical advice or a safety assessment. The worker can say end call, hang up or goodbye, or press End simulated call. Do not look up, validate or search material identifiers. Accept the worker’s stated identifier as a reported fact, without claiming it is verified. Earlier ERP instructions and tool results belong to GlovesOn, not this call. An unavailable tool is not a failed material lookup; do not ask the worker to repeat a clear identifier because of it. Stay Alex until the application ends this mode.' : this.basePrompt), tools:this.catalog.filter(t => this.allows(t.name)), input:{
        keyterms:[...new Set([...(this.config.input?.keyterms || []), ...this.context])].slice(0,100)
      }};
    }
  }
  function safeDiagnostic(value) {
    if (Array.isArray(value)) return value.map(safeDiagnostic);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
      .filter(([key]) => !/token|secret|capability|authorization|audio|config|confirmed_utterance|user_confirmation/i.test(key))
      .map(([key,v]) => [key,safeDiagnostic(v)]));
    return value;
  }
  root.GlovesOnVoice = {VoicePolicy, safeDiagnostic, writes};
  if (typeof module !== 'undefined') module.exports = root.GlovesOnVoice;
})(globalThis);
