import * as THREE from './vendor/three.module.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

// Karakter lobide yasiyor - acilis sayfasinda degil, cunku orada 8 MB'lik bir
// GLB 68 KB'lik bir gorselin yerini alamaz. Lobiye gelen kisi zaten "vardiyaya
// basla" demis biri; bekleyecek kadar ilgileniyor.
const hero = document.querySelector('#avatarStage');
const photo = null;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let renderer, observer, resizeObserver, greet, bubble, visible = false, loaded = false;
const fallback = () => {
  renderer?.setAnimationLoop(null);
  if (renderer) renderer.domElement.hidden = true;
  if (greet) greet.hidden = true;
  if (bubble) bubble.hidden = true;
};
async function start() {
  if (!hero || reduced.matches || loaded) return;
  loaded = true;
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.domElement.className = 'avatar-motion';
    renderer.domElement.setAttribute('aria-hidden', 'true');
    renderer.domElement.addEventListener('webglcontextlost', fallback);
    const [gltf, data] = await Promise.all([
      new GLTFLoader().loadAsync('/assets/avatar/worker.glb'),
      fetch('/assets/avatar/motions.json?v=3').then(r => { if (!r.ok) throw Error('Motion unavailable'); return r.json(); })
    ]);
    if (reduced.matches) { renderer.dispose(); loaded = false; return; }
    const scene = new THREE.Scene();
    // Dikey kadraj 2.37 -> 2.05 birim: figur ayni sahnede daha buyuk duruyor.
    const camera = new THREE.OrthographicCamera(-2, 2, 1.90, -.15, .1, 20);
    camera.position.set(0, 0, 6);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9b927f, 2.5));
    const light = new THREE.DirectionalLight(0xffffff, 2.7);
    light.position.set(3, 5, 4); scene.add(light);
    const actor = new THREE.Group(); actor.add(gltf.scene); scene.add(actor);
    const mixer = new THREE.AnimationMixer(gltf.scene);
    const actions = Object.fromEntries(Object.entries(data).map(([name, clip]) => [name, mixer.clipAction(THREE.AnimationClip.parse(clip))]));
    actions.wave.setLoop(THREE.LoopOnce, 1); actions.wave.clampWhenFinished = true;
    let current, elapsed = 0, phase = 'idle', phaseStart = 0, home = .8, near = .2, travelFrom = .8, travelTo = .2;
    let autoIntro = true, returning = false, arrival = null;
    function play(name) {
      const next = actions[name]; if (current === next) return;
      next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).play();
      if (current) { current.fadeOut(.3); next.fadeIn(.3); }
      current = next;
    }
    function walk(back = false) {
      if (phase === 'walk' || reduced.matches) return;
      returning = back; travelFrom = actor.position.x; travelTo = back ? home : near;
      if (Math.abs(travelFrom - travelTo) < .05) { wave(); return; }
      phase = 'walk'; phaseStart = elapsed; play('walk');
    }
    function wave() {
      if (phase === 'walk' || phase === 'wave' || reduced.matches) return;
      phase = 'wave'; phaseStart = elapsed; play('wave');
    }
    play('idle');
    bubble = document.createElement('p');
    bubble.className = 'avatar-line';
    bubble.textContent = 'Pick an area — I’ll meet you there.';
    hero.append(bubble);
    greet = document.createElement('button'); greet.className = 'avatar-greet';
    greet.setAttribute('aria-label', 'Say hello to your warehouse guide');
    greet.addEventListener('pointerenter', wave); greet.addEventListener('click', wave);
    autoIntro = false;
    // Disariya acilan tek kanca: bir alan secildiginde karakter o kartin onune
    // yuruyor ve soz veriyor. Ekran, soz cozulunce degisiyor.
    window.gloveson = window.gloveson || {};
    window.gloveson.avatarWalkTo = (key) => {
      bubble?.classList.add('is-away');
      const card = document.querySelector(`[data-enter="${key}"]`);
      if (!card || reduced.matches || !visible) return null;
      const stage = hero.getBoundingClientRect(), target = card.getBoundingClientRect();
      // Kartin merkezini sahne koordinatina cevir: -half .. +half
      const ratio = ((target.left + target.width / 2) - stage.left) / stage.width;
      const half = camera.right;
      return new Promise(resolve => {
        travelFrom = actor.position.x;
        travelTo = (ratio - .5) * 2 * half * .82;
        if (Math.abs(travelFrom - travelTo) < .05) { resolve(); return; }
        phase = 'walk'; phaseStart = elapsed; play('walk');
        arrival = resolve;
        setTimeout(() => { if (arrival === resolve) { arrival = null; resolve(); } }, 2600);
      });
    };
    hero.append(renderer.domElement, greet);
    function resize() {
      const height = hero.clientHeight, width = hero.clientWidth;
      if (!height || !width) return;
      const half = width / height * 2.05 / 2;
      camera.left = -half; camera.right = half; camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      // Sahnenin ortasi degil sol kenari: ortada durunca secenegin onune
      // geciyor, secmeni bekleyen biri gibi degil secimin kendisi gibi
      // duruyordu. Kenarda bekliyor, alan secilince oraya yuruyor.
      home = -camera.right * .88; near = home;
      if (phase === 'idle' && !arrival) actor.position.x = home;
    }
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(hero); resize();
    let previous = performance.now();
    renderer.setAnimationLoop(now => {
      const dt = Math.min((now - previous) / 1000, .05); previous = now;
      if (!visible || document.hidden || reduced.matches) return;
      elapsed += dt; mixer.update(dt);
      // Nefes sigortasi: idle klibi bir kez durursa karakter sonsuza kadar
      // cansiz kalir ve bunu fark eden tek sey izleyen insan olur. Dongu
      // durmus bir idle gorurse yeniden baslatir - tesihs yerine dayaniklilik.
      if (phase === 'idle' && current === actions.idle && !actions.idle.isRunning()) {
        actions.idle.reset().setEffectiveWeight(1).play();
      }
      // Nefes, klibe emanet degil: idle klibi mixer icinde arada bir oluyor ve
      // sebebi kutunun derinlerinde. Bu iki satir ise donguden geliyor - dongu
      // calistigi surece karakter nefes alir. Genlik bilerek kucuk: 2 birim
      // boyda 8 binde birlik salinim, ekranda ~2 piksel - nefes gibi okunur,
      // yaylanma gibi degil.
      if (phase !== 'walk') {
        actor.position.y = Math.sin(elapsed * 1.6) * .008;
        actor.rotation.z = Math.sin(elapsed * .8) * .005;
      } else {
        actor.position.y = 0; actor.rotation.z = 0;
      }
      if (phase === 'walk') {
        const duration = Math.max(1.6, Math.abs(travelTo - travelFrom) / .48);
        const t = Math.min(1, (elapsed - phaseStart) / duration);
        actor.position.x = THREE.MathUtils.lerp(travelFrom, travelTo, t);
        const facing = travelTo < travelFrom ? -Math.PI / 2 : Math.PI / 2;
        actor.rotation.y = THREE.MathUtils.lerp(actor.rotation.y, facing, Math.min(1, dt * 8));
        if (t === 1) { phase = 'idle'; phaseStart = elapsed; play('idle');
          if (arrival) { const done = arrival; arrival = null; done(); } else if (!returning) wave(); }
      } else {
        actor.rotation.y = THREE.MathUtils.lerp(actor.rotation.y, 0, Math.min(1, dt * 7));
        if (phase === 'wave' && elapsed - phaseStart > data.wave.duration) { phase = 'idle'; phaseStart = elapsed; play('idle'); }
      }
      renderer.render(scene, camera);
    });
    observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { threshold: .1 });
    window.__avatarDebug = () => ({ visible, phase, elapsed: +elapsed.toFixed(2), x: +actor.position.x.toFixed(3),
      idleRunning: actions.idle.isRunning(), idleTime: +actions.idle.time.toFixed(2), mixerTime: +mixer.time.toFixed(2) });
    observer.observe(hero);
  } catch (error) { fallback(); console.warn('Avatar fallback:', error.message); }
}
reduced.addEventListener('change', () => {
  if (reduced.matches) { fallback(); observer?.disconnect(); resizeObserver?.disconnect(); renderer?.dispose(); renderer?.domElement.remove(); greet?.remove(); loaded = false; }
  else start();
});
start();
