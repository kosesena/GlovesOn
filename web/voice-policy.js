/* Conversation policy is separate from rendering so transport regressions can run offline. */
(function(root) {
  'use strict';
  const writes = new Set(['post_goods_receipt', 'reverse_goods_receipt']);
  const prepareToWrite = {prepare_goods_receipt:'post_goods_receipt', prepare_reversal:'reverse_goods_receipt'};
  class VoicePolicy {
    constructor(config, catalog, now = () => Date.now()) {
      this.config = config;
      this.catalog = catalog || config.tools || [];
      this.now = now;
      this.draft = null;
      this.uncertain = false;
      this.context = [];
    }
    user(text) {
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
      // Only known result fields supply vocabulary; no arbitrary tool text becomes instructions.
      const items = data.matches || (data.MAKTX ? [data] : []);
      this.context = items.slice(0,12).flatMap(item => [item.MATNR, item.MAKTX])
        .filter(value => typeof value === 'string' && value.length <= 80);
    }
    allows(name) {
      if (this.uncertain && (writes.has(name) || prepareToWrite[name])) return false;
      return !writes.has(name) || Boolean(this.draft && this.draft.expires > this.now() && this.draft.tool === name);
    }
    update() {
      return {tools:this.catalog.filter(t => this.allows(t.name)), input:{
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
