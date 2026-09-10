// Hover previews on desktop; explicit buttons also support touch and keyboards.
(() => {
  document.querySelectorAll('.how-story').forEach(card => {
    const front = card.querySelector('.how-story-play');
    const back = card.querySelector('.how-story-details');
    const toggle = card.querySelector('.how-story-toggle');
    let flipped = false;
    function flip(next) {
      flipped = next;
      card.classList.toggle('is-flipped', next);
      back.inert = !next;
      back.setAttribute('aria-hidden', String(!next));
      front.setAttribute('aria-expanded', String(next));
      toggle.setAttribute('aria-expanded', String(next));
      toggle.textContent = next ? 'Back ↺' : 'Details ↗';
    }
    card.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') flip(true);
    });
    card.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse') flip(false);
    });
    front.addEventListener('click', () => flip(true));
    toggle.addEventListener('click', () => flip(!flipped));
    card.addEventListener('keydown', event => {
      if (event.key === 'Escape') { flip(false); toggle.focus(); }
    });
    window.addEventListener('hashchange', () => flip(false));
  });
})();
