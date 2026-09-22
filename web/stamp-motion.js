/* The posted stamp: a full-screen moment played once when a material document lands.
 *
 * A web reproduction of the "made in Figma motion" study Sena sent on 22 September 2026
 * (x.com/solutionb2u, 8.7 s), reimplemented from scratch with our content: a date wheel
 * that becomes a rubber stamp, the document tilting into perspective, the stamp coming
 * down and leaving POSTED · 501 and the posting date, the document flattening again. The
 * toast offers "Reverse", never "Undo", because nothing is deleted. Same beats and
 * timing as the study; the film uses a capture of the same code, so screen and film agree.
 *
 *   playStampMotion({ mblnr, bwart, posted_at, matnr, maktx, menge, meins, bin, werks,
 *                     lgort, before, after, reversal, reverses, hold })
 *
 * Draws itself into a 1280×720 stage scaled to the viewport; removes itself when done.
 * Escape or a click skips it. Honours prefers-reduced-motion by not playing at all.
 */
(function () {
  'use strict';

  const CSS = `
.sm-root { --sm-font: "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif; position: fixed; inset: 0; z-index: 9000; background: radial-gradient(120% 90% at 50% 0%, #fbfbfc 0%, #f3f3f4 55%, #e9e9ec 100%);
  color: #17181a; font-family: "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif; -webkit-font-smoothing: antialiased;
  opacity: 0; transition: opacity .35s ease; overflow: hidden; cursor: default; }
.sm-root.sm-in { opacity: 1; }
.sm-stage { position: absolute; left: 50%; top: 50%; width: 1280px; height: 720px; transform: translate(-50%,-50%) scale(var(--sm-scale, 1)); transform-origin: 50% 50%; }
.sm-root, .sm-root * { box-sizing: border-box; }

.sm-picker { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; padding-top: 65px; }
.sm-picker .sm-kicker { font: 500 10px/1 var(--sm-font); letter-spacing: .14em; color: #8b8f96; text-transform: uppercase; }
.sm-picker h1 { margin: 10px 0 6px; font: 600 21px/1.2 var(--sm-font); letter-spacing: -.01em; }
.sm-picker .sm-sub { margin: 0 0 26px; font-size: 11.5px; color: #8b8f96; }
.sm-picker .sm-date { margin-top: 18px; font: 600 11px/1 var(--sm-font); }
.sm-picker .sm-tabs { margin-top: 14px; display: flex; align-items: center; gap: 16px; }
.sm-seg { display: flex; background: #ececee; border-radius: 8px; padding: 2px; }
.sm-seg span { font: 500 10.5px/1 var(--sm-font); color: #8b8f96; padding: 6px 12px; border-radius: 6px; }
.sm-seg span.on { background: #fff; color: #17181a; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
.sm-dots { display: flex; gap: 8px; }
.sm-dots i { width: 11px; height: 11px; border-radius: 50%; display: block; }
.sm-dots i.on { box-shadow: 0 0 0 2px #fff, 0 0 0 3.5px currentColor; }
.sm-cta { margin-top: 22px; background: #17181a; color: #fff; border: 0; border-radius: 999px; padding: 10px 22px; font: 600 11.5px/1 var(--sm-font); }
.sm-hint { margin-top: 8px; font-size: 9.5px; color: #8b8f96; }
.sm-picker .sm-fade { transition: opacity .55s ease, filter .55s ease; }
.sm-root:not([data-stage="pick"]) .sm-picker .sm-fade { opacity: 0; filter: blur(3px); }

.sm-anchor { position: absolute; left: 50%; top: 163px; width: 0; height: 0; }
.sm-block { position: absolute; left: -125px; top: 0; width: 250px; height: 120px; transform-style: preserve-3d; transition: transform 1.1s cubic-bezier(.5,0,.15,1); will-change: transform; }
.sm-wheel { position: absolute; inset: 0; background: linear-gradient(180deg, #fff 0%, #f6f6f7 100%); border-radius: 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.05), 0 12px 30px -12px rgba(0,0,0,.18); padding: 12px 16px 10px; overflow: hidden; transition: box-shadow .8s ease; }
.sm-wheel .sm-top { display: flex; justify-content: space-between; align-items: center; font: 600 8.5px/1 var(--sm-font); letter-spacing: .18em; color: #8b8f96; }
.sm-wheel .sm-top i { width: 7px; height: 7px; border-radius: 50%; background: var(--sm-ink); display: block; }
.sm-cols { display: grid; grid-template-columns: 1fr 1.4fr 1fr; gap: 6px; margin-top: 8px; height: 62px;
  -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 28%, #000 72%, transparent 100%); mask-image: linear-gradient(180deg, transparent 0, #000 28%, #000 72%, transparent 100%); }
.sm-col { position: relative; overflow: hidden; }
.sm-col ul { list-style: none; margin: 0; padding: 0; position: absolute; left: 0; right: 0; top: 0; transition: transform .9s cubic-bezier(.3,.9,.3,1); }
.sm-col li { height: 20.6px; display: flex; align-items: center; justify-content: center; font: 600 13px/1 var(--sm-font); color: #c3c6cb; border-radius: 6px; margin: 0 4px; transition: color .3s, background .3s; }
.sm-col li.sel { color: #17181a; background: #ececee; }
.sm-labels { display: grid; grid-template-columns: 1fr 1.4fr 1fr; gap: 6px; margin-top: 4px; text-align: center; font: 600 7px/1 var(--sm-font); letter-spacing: .2em; color: #b6b9bf; }
.sm-body { position: absolute; left: 0; right: 0; top: 100%; height: 0; margin-top: -14px; background: linear-gradient(180deg, #f2f2f3 0%, #e4e4e6 55%, #d6d6d9 100%);
  border-radius: 0 0 16px 16px; opacity: 0; box-shadow: inset 0 -8px 12px -8px rgba(0,0,0,.18), inset 10px 0 12px -10px rgba(0,0,0,.08), inset -10px 0 12px -10px rgba(0,0,0,.08);
  transition: height .7s cubic-bezier(.2,.9,.3,1), opacity .3s ease; }
.sm-base { position: absolute; left: 8px; right: 8px; top: 100%; height: 0; margin-top: 34px; border-radius: 0 0 8px 8px / 0 0 10px 10px;
  background: linear-gradient(180deg, #3a3b3f 0%, #17181b 40%, #0c0d0f 100%); box-shadow: 0 6px 10px -4px rgba(0,0,0,.5); opacity: 0;
  transition: height .6s cubic-bezier(.2,.9,.3,1) .15s, opacity .3s ease .15s; }
.sm-base::after { content: ""; position: absolute; left: 6px; right: 6px; bottom: 0; height: 4px; border-radius: 0 0 4px 4px; background: linear-gradient(180deg, var(--sm-ink-dark), var(--sm-ink)); }
.sm-shadow { position: absolute; left: 10px; right: 10px; top: 176px; height: 34px; border-radius: 50%; background: radial-gradient(closest-side, rgba(0,0,0,.28), rgba(0,0,0,0)); filter: blur(6px); opacity: 0; transition: opacity .6s ease, transform 1.1s cubic-bezier(.5,0,.15,1); }

.sm-scene { position: absolute; inset: 0; perspective: 1400px; perspective-origin: 50% 30%; opacity: 0; transition: opacity .7s ease; }
.sm-panchor { position: absolute; left: 50%; top: 50%; width: 0; height: 0; transform-style: preserve-3d; }
.sm-panchor.hit { animation: sm-hit .35s ease-out; }
@keyframes sm-hit { 0% { transform: translateY(0); } 40% { transform: translateY(5px); } 100% { transform: translateY(0); } }
.sm-paper { position: absolute; left: -190px; top: -260px; width: 380px; height: 520px; background: #fbfbfb; border-radius: 3px; padding: 30px 30px 26px;
  box-shadow: 0 30px 60px -30px rgba(0,0,0,.35), 0 2px 6px rgba(0,0,0,.06); --tilt: rotateX(44deg) rotateZ(-5deg) translateZ(-40px);
  transform: var(--tilt) scale(1.75) translateY(-40px); transform-origin: 50% 60%; transition: transform 1.3s cubic-bezier(.55,0,.2,1), box-shadow 1.3s ease;
  transform-style: preserve-3d; font-size: 6.5px; color: #3a3d42; line-height: 1.55; }
.sm-paper .sm-head { display: flex; justify-content: space-between; align-items: flex-start; }
.sm-paper .sm-title { font: 600 13px/1.1 var(--sm-font); color: #17181a; }
.sm-paper .sm-studio { font-size: 6px; color: #8b8f96; margin-top: 3px; }
.sm-paper .sm-logo { width: 16px; height: 16px; border-radius: 4px; background: #e96935; }
.sm-paper .sm-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }
.sm-paper .sm-meta b { font-weight: 600; color: #17181a; }
.sm-paper .sm-lines { margin-top: 18px; }
.sm-paper .sm-lines .sm-h { font: 600 7.5px/1 var(--sm-font); color: #17181a; margin-bottom: 6px; }
.sm-paper table { width: 100%; border-collapse: collapse; }
.sm-paper th { text-align: left; font-weight: 500; color: #8b8f96; padding: 3px 0; border-bottom: 1px solid #e6e7ea; }
.sm-paper td { padding: 4px 0; border-bottom: 1px solid #f0f0f2; }
.sm-paper th:not(:first-child), .sm-paper td:not(:first-child) { text-align: right; }
.sm-paper .sm-total { display: flex; justify-content: flex-end; margin-top: 8px; }
.sm-paper .sm-total div { text-align: right; }
.sm-paper .sm-total .sm-n { font: 600 11px/1.2 var(--sm-font); color: #17181a; }
.sm-paper .sm-why { margin-top: 20px; }
.sm-paper .sm-why b { display: block; font-weight: 600; color: #17181a; margin-bottom: 2px; }
.sm-paper .sm-foot { position: absolute; left: 30px; right: 30px; bottom: 18px; display: flex; justify-content: space-between; color: #8b8f96; font-size: 6px; }
.sm-mark { position: absolute; right: 44px; bottom: 96px; width: 118px; padding: 5px 6px 6px; border: 2.5px solid var(--sm-ink); border-radius: 5px; color: var(--sm-ink); text-align: center;
  transform: rotate(-9deg) scale(1.35); opacity: 0; transform-origin: 50% 50%; box-shadow: inset 0 0 0 1px rgba(0,0,0,.06); }
.sm-mark .sm-k { font: 600 5.5px/1 var(--sm-font); letter-spacing: .28em; }
.sm-mark .sm-d { font: 800 15px/1.05 var(--sm-font); letter-spacing: .02em; margin-top: 2px; }
.sm-mark.on { animation: sm-press .32s cubic-bezier(.2,1.1,.4,1) forwards; }
@keyframes sm-press { 0% { transform: rotate(-9deg) scale(1.35); opacity: 0; } 55% { transform: rotate(-9deg) scale(.96); opacity: 1; } 100% { transform: rotate(-9deg) scale(1); opacity: .88; } }

.sm-toast { position: absolute; left: 50%; bottom: 50px; transform: translate(-50%, 16px); opacity: 0; display: flex; align-items: center; gap: 10px; background: #fff; border-radius: 999px;
  padding: 6px 6px 6px 14px; box-shadow: 0 6px 24px -8px rgba(0,0,0,.25), 0 1px 2px rgba(0,0,0,.06); font: 500 10.5px/1 var(--sm-font); transition: opacity .35s ease, transform .35s ease; white-space: nowrap; }
.sm-toast i { width: 6px; height: 6px; border-radius: 50%; background: var(--sm-ink); display: inline-block; margin-right: 6px; }
.sm-toast .sm-sep { color: #8b8f96; }
.sm-toast button { border: 0; border-radius: 999px; padding: 7px 11px; font: 600 10.5px/1 var(--sm-font); background: #f1f1f3; color: #17181a; }
.sm-toast button.dark { background: #17181a; color: #fff; }
.sm-toast.on { opacity: 1; transform: translate(-50%, 0); }

.sm-endhead { position: absolute; left: 0; right: 0; top: 50px; text-align: center; opacity: 0; transform: translateY(6px); transition: opacity .5s ease .2s, transform .5s ease .2s; }
.sm-endhead .sm-kicker { font: 500 9px/1 var(--sm-font); letter-spacing: .14em; color: #8b8f96; text-transform: uppercase; }
.sm-endhead h1 { margin: 8px 0 4px; font: 600 20px/1.2 var(--sm-font); }
.sm-endhead .sm-sub { font-size: 10.5px; color: #8b8f96; }
.sm-endhead .sm-sub i { width: 6px; height: 6px; border-radius: 50%; background: var(--sm-ink); display: inline-block; margin-right: 5px; vertical-align: 1px; }
.sm-endbar { position: absolute; left: 50%; bottom: 50px; transform: translate(-50%, 8px); opacity: 0; display: flex; gap: 8px; transition: opacity .5s ease .3s, transform .5s ease .3s; }
.sm-endbar button { border: 0; border-radius: 999px; padding: 9px 16px; font: 600 10.5px/1 var(--sm-font); background: #ececee; color: #17181a; }
.sm-endbar button.dark { background: #17181a; color: #fff; }

.sm-root[data-stage="lift"] .sm-scene, .sm-root[data-stage="stamp"] .sm-scene, .sm-root[data-stage="toast"] .sm-scene, .sm-root[data-stage="flat"] .sm-scene, .sm-root[data-stage="end"] .sm-scene { opacity: 1; }
.sm-root[data-stage="lift"] .sm-body, .sm-root[data-stage="stamp"] .sm-body, .sm-root[data-stage="toast"] .sm-body, .sm-root[data-stage="flat"] .sm-body { height: 62px; opacity: 1; }
.sm-root[data-stage="lift"] .sm-base, .sm-root[data-stage="stamp"] .sm-base, .sm-root[data-stage="toast"] .sm-base, .sm-root[data-stage="flat"] .sm-base { height: 18px; opacity: 1; }
.sm-root[data-stage="lift"] .sm-wheel, .sm-root[data-stage="stamp"] .sm-wheel, .sm-root[data-stage="toast"] .sm-wheel { box-shadow: 0 30px 50px -18px rgba(0,0,0,.35); }
.sm-root[data-stage="lift"] .sm-shadow, .sm-root[data-stage="stamp"] .sm-shadow, .sm-root[data-stage="toast"] .sm-shadow { opacity: 1; }
.sm-root[data-stage="lift"]  .sm-block { transform: translate(60px, 150px) scale(.92); transition: transform 1.1s cubic-bezier(.5,0,.15,1); }
.sm-root[data-stage="stamp"] .sm-block { transform: translate(134px, 200px) scale(.88); transition: transform .5s cubic-bezier(.55,0,.9,.45); }
.sm-root[data-stage="toast"] .sm-block { transform: translate(150px, 40px) scale(.92); transition: transform .8s cubic-bezier(.2,.8,.3,1); }
.sm-root[data-stage="flat"] .sm-block, .sm-root[data-stage="end"] .sm-block { transform: translate(60px, -260px) scale(.9); transition: transform 1s cubic-bezier(.5,0,.2,1); }
.sm-root[data-stage="flat"] .sm-shadow, .sm-root[data-stage="end"] .sm-shadow { opacity: 0; }
.sm-root[data-stage="stamp"] .sm-shadow { transform: translateY(-10px) scale(.7); }
.sm-root[data-stage="lift"] .sm-paper, .sm-root[data-stage="stamp"] .sm-paper, .sm-root[data-stage="toast"] .sm-paper { transform: var(--tilt) scale(1.2) translateY(0); }
.sm-root[data-stage="flat"] .sm-paper, .sm-root[data-stage="end"] .sm-paper { transform: rotateX(0) rotateZ(0) translateZ(0) scale(.82) translateY(22px); box-shadow: 0 10px 30px -18px rgba(0,0,0,.3), 0 1px 3px rgba(0,0,0,.05); transition: transform 1.1s cubic-bezier(.6,0,.2,1), box-shadow 1.1s ease; }
.sm-root[data-stage="end"] .sm-endhead { opacity: 1; transform: translateY(0); }
.sm-root[data-stage="end"] .sm-endbar { opacity: 1; transform: translate(-50%, 0); }
`;

  const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  const ROW = 20.6;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const longDate = d => d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const stampDate = d => `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  const shortDate = d => `${d.getDate()} ${MONTHS[d.getMonth()][0]}${MONTHS[d.getMonth()].slice(1).toLowerCase()} ${d.getFullYear()}`;

  function ensureStyle() {
    if (document.getElementById('sm-style')) return;
    const st = document.createElement('style'); st.id = 'sm-style'; st.textContent = CSS; document.head.appendChild(st);
  }

  function build(d) {
    const when = d.posted_at ? new Date((typeof d.posted_at === 'number' ? d.posted_at * 1000 : Date.parse(d.posted_at))) : new Date();
    const reversal = !!d.reversal;
    const ink = reversal ? '#c0392b' : '#e0362b';
    const kind = reversal ? 'REVERSED' : 'POSTED';
    const bwart = d.bwart || (reversal ? '502' : '501');
    const qty = `${d.menge ?? ''}`.trim(), unit = d.meins || 'EA';
    const before = d.before ?? (d.after != null && qty ? d.after + (reversal ? 1 : -1) * Number(qty) : null);
    const stockLine = d.after != null ? `${before ?? '—'} → ${d.after} ${unit}` : '—';
    const matnr = String(d.matnr ?? '').replace(/^0+/, '') || '—';
    const dayStart = new Date(when); dayStart.setDate(when.getDate() - 2);
    const days = [], years = [];
    for (let i = 0; i < 7; i++) { const x = new Date(dayStart); x.setDate(dayStart.getDate() + i); days.push(x.getDate()); }
    for (let y = when.getFullYear() - 2; y <= when.getFullYear() + 2; y++) years.push(y);
    const mi = when.getMonth();
    const months = [-2, -1, 0, 1, 2].map(k => MONTHS[(mi + k + 12) % 12]);
    const root = document.createElement('div');
    root.className = 'sm-root'; root.dataset.stage = 'pick';
    root.style.setProperty('--sm-ink', ink); root.style.setProperty('--sm-ink-dark', reversal ? '#6d1f16' : '#7a1e17');
    root.setAttribute('role', 'presentation');
    root.innerHTML = `
<div class="sm-stage">
  <section class="sm-picker">
    <div class="sm-fade sm-kicker">Plant ${esc(d.werks || '1000')} · Receiving bay · ${esc(qty)} ${esc(unit)}</div>
    <h1 class="sm-fade">Material document ${esc(d.mblnr)}</h1>
    <p class="sm-fade sm-sub">${reversal ? 'The posting date of the reversal. Both documents stay in the record.' : "Choose the posting date. It's printed on the document and saved to its history."}</p>
    <div style="height:120px"></div>
    <div class="sm-fade sm-date"></div>
    <div class="sm-fade sm-tabs">
      <div class="sm-seg"><span class="${reversal ? '' : 'on'}">Posted</span><span class="${reversal ? 'on' : ''}">Reversed</span><span>Refused</span><span>Draft</span></div>
      <div class="sm-dots"><i class="on" style="background:${ink};color:${ink}"></i><i style="background:#2f6fe4"></i><i style="background:#2aa25b"></i><i style="background:#7a4de8"></i><i style="background:#1d1e21"></i></div>
    </div>
    <div class="sm-fade sm-cta">Mark as ${reversal ? 'reversed' : 'posted'}</div>
    <div class="sm-fade sm-hint">confirmed by voice</div>
  </section>
  <section class="sm-scene">
    <div class="sm-panchor">
      <div class="sm-paper">
        <div class="sm-head"><div><div class="sm-title">${reversal ? 'Receipt reversal' : 'Goods receipt'}</div><div class="sm-studio">GlovesOn · Plant ${esc(d.werks || '1000')} / ${esc(d.lgort || '0001')}</div></div><div class="sm-logo"></div></div>
        <div class="sm-meta">
          <div><b>Bin:</b> ${esc(d.bin || '—')}<br><b>Material:</b> ${esc(matnr)}<br><b>Movement:</b> ${esc(bwart)} · ${reversal ? 'reversal of a receipt' : 'receipt without PO'}</div>
          <div><b>Document no.:</b> ${esc(d.mblnr)}<br><b>Document date:</b> ${when.toLocaleDateString('en-GB')}<br><b>Posting date:</b> ${when.toLocaleDateString('en-GB')}</div>
        </div>
        <div class="sm-lines">
          <div class="sm-h">Description of goods</div>
          <table>
            <tr><th>Description</th><th>Quantity</th><th>Unit</th><th>Stock after</th></tr>
            <tr><td>${esc(d.maktx || '—')}</td><td>${esc(qty)}</td><td>${esc(unit)}</td><td>${d.after != null ? esc(d.after) + ' ' + esc(unit) : '—'}</td></tr>
            <tr><td>Bin ${esc(d.bin || '—')}</td><td></td><td></td><td></td></tr>
            <tr><td>Read back, confirmed by voice at ${when.toLocaleTimeString('en-GB')}</td><td></td><td></td><td></td></tr>
          </table>
          <div class="sm-total"><div>Stock<br><span class="sm-n">${esc(stockLine)}</span></div></div>
        </div>
        <div class="sm-why"><b>Why this document exists</b>${reversal
          ? `Reverses ${esc(d.reverses || '')}: the ${esc(qty)} ${esc(unit)} are back out of ${esc(d.bin || 'the bin')}. Nothing is deleted; both documents stay.`
          : `“${esc(qty)} pieces of ${esc(d.maktx || 'the material')} into ${esc(d.bin || 'the bin')}.” — as the agent read it back.<br>Wrong? Say “reverse it”. A reversal takes them back out and both documents stay.`}</div>
        <div class="sm-mark"><div class="sm-k">${kind} · ${esc(bwart)}</div><div class="sm-d">${stampDate(when)}</div></div>
        <div class="sm-foot"><span>Both documents stay in the record.</span><span>gloveson.space</span></div>
      </div>
    </div>
  </section>
  <div class="sm-anchor"><div class="sm-block">
    <div class="sm-shadow"></div><div class="sm-body"></div><div class="sm-base"></div>
    <div class="sm-wheel">
      <div class="sm-top"><span>${kind}</span><i></i></div>
      <div class="sm-cols">
        <div class="sm-col"><ul class="sm-days">${days.map(x => `<li>${x}</li>`).join('')}</ul></div>
        <div class="sm-col"><ul class="sm-months">${months.map(x => `<li>${x}</li>`).join('')}</ul></div>
        <div class="sm-col"><ul class="sm-years">${years.map(x => `<li>${x}</li>`).join('')}</ul></div>
      </div>
      <div class="sm-labels"><span>DAY</span><span>MONTH</span><span>YEAR</span></div>
    </div>
  </div></div>
  <div class="sm-toast"><span><i></i>${kind[0] + kind.slice(1).toLowerCase()} · ${shortDate(when)}</span><span class="sm-sep">·</span><button>${reversal ? 'Open both' : 'Reverse'}</button><button class="dark">Done</button></div>
  <div class="sm-endhead"><div class="sm-kicker">Plant ${esc(d.werks || '1000')} · Receiving bay · ${esc(qty)} ${esc(unit)}</div><h1>Material document ${esc(d.mblnr)}</h1><div class="sm-sub"><i></i>${kind[0] + kind.slice(1).toLowerCase()} on ${longDate(when)}</div></div>
  <div class="sm-endbar"><button>Download PDF</button><button class="dark">${reversal ? 'Back to the record' : 'Next receipt'}</button></div>
</div>`;
    return { root, when, days };
  }

  function fit(root) {
    // Landscape: the whole 1280×720 stage fits. Portrait (a phone): the stage's middle
    // 640 px is what matters, since everything is centred, so let the sides run off.
    const s = innerWidth >= innerHeight
      ? Math.min(innerWidth / 1280, innerHeight / 720)
      : Math.min(innerHeight / 720, innerWidth / 640);
    root.style.setProperty('--sm-scale', s.toFixed(4));
  }

  let current = null;

  function playStampMotion(d) {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve(false);
    if (current) current.stop();
    ensureStyle();
    const { root, when, days } = build(d);
    document.body.appendChild(root);
    fit(root);
    const onResize = () => fit(root);
    addEventListener('resize', onResize);
    const timers = [];
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));
    const col = (cls, i) => { const ul = root.querySelector(cls); ul.style.transform = `translateY(${-(i - 1) * ROW}px)`; [...ul.children].forEach((li, k) => li.classList.toggle('sel', k === i)); };
    const label = root.querySelector('.sm-date');
    const dayIndex = days.indexOf(when.getDate());
    const ddate = k => { const x = new Date(when); x.setDate(when.getDate() - k); return longDate(x); };
    let done;
    const finished = new Promise(r => { done = r; });
    const stop = () => {
      timers.forEach(clearTimeout); removeEventListener('resize', onResize); removeEventListener('keydown', onKey);
      root.classList.remove('sm-in'); setTimeout(() => root.remove(), 380); current = null; done(true);
    };
    const onKey = e => { if (e.key === 'Escape') stop(); };
    addEventListener('keydown', onKey);
    root.addEventListener('click', stop);
    current = { stop };

    // 0.0–1.6 s: the wheel arrives at the posting date. 1.9 s: the card becomes a stamp
    // and the document appears. 3.3 s: the stamp comes down. 3.8 s: the mark. 4.2 s: it
    // lifts, the toast. 5.6 s: the document flattens. 6.6 s: the end state, held.
    col('.sm-days', dayIndex - 2); col('.sm-months', 2); col('.sm-years', 2); label.textContent = ddate(2);
    requestAnimationFrame(() => root.classList.add('sm-in'));
    at(400,  () => { col('.sm-days', dayIndex - 1); label.textContent = ddate(1); });
    at(1000, () => { col('.sm-days', dayIndex);     label.textContent = ddate(0); });
    at(1900, () => { root.dataset.stage = 'lift'; });
    at(3300, () => { root.dataset.stage = 'stamp'; });
    at(3800, () => { root.querySelector('.sm-mark').classList.add('on'); root.querySelector('.sm-panchor').classList.add('hit'); });
    at(4200, () => { root.dataset.stage = 'toast'; });
    at(4500, () => { root.querySelector('.sm-toast').classList.add('on'); });
    at(5600, () => { root.querySelector('.sm-toast').classList.remove('on'); root.dataset.stage = 'flat'; });
    at(6600, () => { root.dataset.stage = 'end'; });
    at(8700 + (d.hold ?? 1300), stop);
    return finished;
  }

  window.playStampMotion = playStampMotion;
})();
