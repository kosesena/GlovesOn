// Hover previews on desktop; explicit buttons also support touch and keyboards.
(() => {
  document.querySelectorAll('.how-story').forEach(card => {
    const front = card.querySelector('.how-story-play');
    const back = card.querySelector('.how-story-details');
    const toggle = card.querySelector('.how-story-toggle');
    let flipped = false;
    let timers = [];
    const delivery = card.classList.contains('delivery-story');
    let scene;
    let run = 0;
    async function preview() {
      if (!delivery || matchMedia('(prefers-reduced-motion: reduce)').matches) return flip(true);
      const current = ++run;
      try {
        scene ||= await (card.dataset.scene
          ? import('/assets/avatar/work-scenes.js').then(module => module.createWorkScene(card.querySelector('.delivery-canvas'), card.dataset.scene))
          : import('/assets/avatar/delivery-scene.js').then(module => module.createDeliveryScene(card.querySelector('.delivery-canvas'))));
        if (current !== run) return;
        card.classList.add('is-arriving');
        scene.play(() => { if (current === run) flip(true); });
      } catch (_) { if (current === run) flip(true); }
    }
    function flip(next) {
      timers.forEach(clearTimeout);
      if (!next) { run++; scene?.reset(); card.classList.remove('is-arriving', 'is-close'); }
      flipped = next;
      card.classList.toggle('is-flipped', next);
      back.inert = !next;
      back.setAttribute('aria-hidden', String(!next));
      front.setAttribute('aria-expanded', String(next));
      toggle.setAttribute('aria-expanded', String(next));
      toggle.textContent = next ? 'Back ↺' : 'Details ↗';
    }
    card.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') preview();
    });
    card.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse') flip(false);
    });
    front.addEventListener('click', () => { preview(); });
    toggle.addEventListener('click', () => flip(!flipped));
    card.addEventListener('keydown', event => {
      if (event.key === 'Escape') { flip(false); toggle.focus(); }
    });
    window.addEventListener('hashchange', () => flip(false));
  });
})();
