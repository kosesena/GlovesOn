// Each scene plays once per visit to the card, then reveals its explanation.
(() => {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('.how-story').forEach(card => {
    const play = card.querySelector('.how-story-play');
    const video = card.querySelector('video');
    const details = card.querySelector('.how-story-details');
    const toggle = card.querySelector('.how-story-toggle');
    let version = 0;
    const reveal = () => {
      version++;
      video.pause();
      card.classList.remove('is-playing');
      details.hidden = false;
      play.hidden = true;
      play.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.textContent = 'Replay ↺';
    };
    const reset = () => {
      version++;
      video.pause();
      card.classList.remove('is-playing');
      details.hidden = true;
      play.hidden = false;
      play.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = 'Details ↗';
    };
    const start = async () => {
      if (!details.hidden || card.classList.contains('is-playing')) return;
      if (reducedMotion.matches) return reveal();
      const current = ++version;
      if (!video.getAttribute('src')) video.src = video.dataset.src;
      video.muted = true;
      video.currentTime = 0;
      card.classList.add('is-playing');
      try { await video.play(); } catch (_) {
        if (current === version) reveal();
      }
    };
    card.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') start();
    });
    card.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse' && !card.contains(document.activeElement)) reset();
    });
    play.addEventListener('click', start);
    toggle.addEventListener('click', () => {
      if (details.hidden) reveal();
      else { reset(); start(); }
    });
    video.addEventListener('ended', reveal);
    video.addEventListener('error', reveal);
    window.addEventListener('hashchange', reset);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) reset();
    });
  });
})();
