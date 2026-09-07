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
    // Bekleme pozu: idle klibi ayaklari da hareket ettiriyordu (yerinde
    // yuruyus). Onun yerine kollari govde onunde kenetli sabit bir poz tutuyor,
    // ustune nefes ve arada kulakliga uzanan el biniyor. Bind rotasyonlari
    // saklanip ustune delta ekleniyor.
    const bones = {}; gltf.scene.traverse(o => { if (o.isBone) bones[o.name] = o; });
    const bind = {}; for (const [n, b] of Object.entries(bones)) bind[n] = b.rotation.clone();
    // key: [dx, dy, dz] bind pozuna eklenir. Deneyerek ayarlandi.
    const restPose = {
      RightArm:     [ .18,  0,   -.30],
      LeftArm:      [ .18,  0,    .30],
      RightForeArm: [1.28,  .15, -.10],
      LeftForeArm:  [1.28, -.15,  .10],
      RightHand:    [ .10,  0,    0  ],
      LeftHand:     [ .10,  0,    0  ],
      Spine02:      [ .04,  0,    0  ],
    };
    // Kulaklik dokunma jesti. Poz TAHMIN DEGIL, olcum: iki kemikli analitik IK
    // parmak ucunu kulaklik kupasindan 13.6 mm oteye koyuyor, avuc kafaya
    // donuk, yuze giren tek bir tepe noktasi yok. Sayilar MUTLAK YEREL
    // kuaterniyon - kemigin donusunun yerine gecerler. Onceki iki deneme bind
    // pozuna Euler farki ekledigi icin bozuldu: restPose'un bukumu jestin
    // bukumuyle ust uste biniyordu.
    const touchEnd = {
      RightArm:     new THREE.Quaternion( .182833,  .457002, -.112686, .863147),
      RightForeArm: new THREE.Quaternion(-.805635, -.007894, -.408775, .428711),
      RightHand:    new THREE.Quaternion( .256318,  .666348, -.411145, .566781),
    };
    // Ara nokta: kol once yana aciliyor. Dogrudan slerp elin 306 tepe noktasini
    // yuzun icinden geciriyor ve kafa payi yarim milimetreye dusuyor; bu yol
    // %12 daha uzun ama yuze hic girmiyor ve kafayla arasi 89 mm kaliyor.
    const touchVia = {
      RightArm:     new THREE.Quaternion( .215778, -.372928, -.159126, .888281),
      RightForeArm: new THREE.Quaternion( .225803,  .083197, -.031354, .970107),
      RightHand:    new THREE.Quaternion( .093683,  .009770, -.001906, .995552),
    };
    // Her kemik kendi yay uzunlugunca bolunuyor. Ortak tek bir orta nokta
    // kullanmak bilegi tam ortada bir karede 7 kat hizlandiriyor, goze kamci
    // gibi carpiyordu - yollar 3.6 kat farkli uzunlukta.
    const touchSplit = { RightArm: .366, RightForeArm: .177, RightHand: .086 };
    const TOUCH = { period: 10, rise: .62, hold: .30, fall: .68 };
    const touchSpan = TOUCH.rise + TOUCH.hold + TOUCH.fall;
    const touchScratch = new THREE.Quaternion();
    let touchClock = 0, touchNow = 0;

    const smoothstep = (x) => x * x * (3 - 2 * x);

    function touchWeight(clock) {
      const t = clock - (TOUCH.period - touchSpan);
      if (t <= 0 || t >= touchSpan) return 0;
      if (t < TOUCH.rise) return smoothstep(t / TOUCH.rise);
      if (t < TOUCH.rise + TOUCH.hold) return 1;
      return smoothstep(1 - (t - TOUCH.rise - TOUCH.hold) / TOUCH.fall);
    }

    function applyTouch(w) {
      for (const name of Object.keys(touchEnd)) {
        const b = bones[name]; if (!b) continue;
        const f = touchSplit[name];
        if (w <= f) touchScratch.copy(b.quaternion).slerp(touchVia[name], w / f);
        else        touchScratch.copy(touchVia[name]).slerp(touchEnd[name], (w - f) / (1 - f));
        b.quaternion.copy(touchScratch);
      }
    }

    function applyRest(t) {
      for (const [n, b] of Object.entries(bones)) if (bind[n]) b.rotation.copy(bind[n]);
      for (const [n, d] of Object.entries(restPose)) {
        const b = bones[n]; if (!b) continue;
        b.rotation.x += d[0]; b.rotation.y += d[1]; b.rotation.z += d[2];
      }
      // Nefes: gogus ve basta cok hafif salinim.
      if (bones.Spine01) bones.Spine01.rotation.x += Math.sin(t) * .022;
      if (bones.Head)    bones.Head.rotation.x    += Math.sin(t * .9 + 1) * .015;
    }
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
      // Kol kulakliga uzanmisken selam klibine gecmek bilegi tek karede yarim
      // metre isinliyordu. Selam kozmetik: jest bitene kadar yok sayiyoruz.
      if (touchNow > 0) return;
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
        // Sigorta yuruyus suresinden turuyor: sabit 2600 ms, uzun bir yuruyuste
        // ekrani karakterden once degistiriyordu.
        const expect = Math.max(.9, Math.abs(travelTo - travelFrom) / 1.5) * 1000 + 600;
        setTimeout(() => { if (arrival === resolve) { arrival = null; resolve(); } }, expect);
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
      // .88 -> .78: kulakliga uzanan kol govdeden 0.59 m disari cikiyor,
      // .88'de ise sol kenara sadece 0.36 m kaliyordu ve kol panel sinirinda
      // kesiliyordu. Bedeli figurun ~50 piksel saga kaymasi; sol bosluk 278
      // piksel oldugu icin hala kendi seridinde ve ilk kartin uzaginda.
      home = -camera.right * .78; near = home;
      if (phase === 'idle' && !arrival) actor.position.x = home;
    }
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(hero); resize();
    let previous = performance.now();
    renderer.setAnimationLoop(now => {
      const dt = Math.min((now - previous) / 1000, .05); previous = now;
      if (!visible || document.hidden || reduced.matches) return;
      elapsed += dt;
      if (phase === 'idle') {
        // Klip yok: sabit bekleme pozu + nefes, her karede. Ayaklar bind
        // pozunda sabit kaldigi icin "yerinde yurume" bitiyor.
        applyRest(elapsed * 1.6);
        touchClock += dt; if (touchClock >= TOUCH.period) touchClock -= TOUCH.period;
        touchNow = touchWeight(touchClock);
        if (touchNow > 0) applyTouch(touchNow);
        actor.position.y = Math.sin(elapsed * 1.6) * .006;
        actor.rotation.z = Math.sin(elapsed * .8) * .004;
      } else {
        mixer.update(dt);
        touchNow = 0;
        actor.position.y = 0; actor.rotation.z = 0;
      }
      if (phase === 'walk') {
        const duration = Math.max(.9, Math.abs(travelTo - travelFrom) / 1.5);
        const t = Math.min(1, (elapsed - phaseStart) / duration);
        actor.position.x = THREE.MathUtils.lerp(travelFrom, travelTo, t);
        const facing = travelTo < travelFrom ? -Math.PI / 2 : Math.PI / 2;
        actor.rotation.y = THREE.MathUtils.lerp(actor.rotation.y, facing, Math.min(1, dt * 8));
        if (t === 1) { phase = 'idle'; phaseStart = elapsed; touchClock = TOUCH.period - touchSpan - 2; if (current) { current.stop(); current = null; }
          if (arrival) { const done = arrival; arrival = null; done(); } else if (!returning) wave(); }
      } else {
        actor.rotation.y = THREE.MathUtils.lerp(actor.rotation.y, 0, Math.min(1, dt * 7));
        if (phase === 'wave' && elapsed - phaseStart > data.wave.duration) { phase = 'idle'; phaseStart = elapsed; touchClock = TOUCH.period - touchSpan - 2; if (current) { current.stop(); current = null; } }
      }
      renderer.render(scene, camera);
    });
    observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { threshold: .1 });
    observer.observe(hero);
  } catch (error) { fallback(); console.warn('Avatar fallback:', error.message); }
}
reduced.addEventListener('change', () => {
  if (reduced.matches) { fallback(); observer?.disconnect(); resizeObserver?.disconnect(); renderer?.dispose(); renderer?.domElement.remove(); greet?.remove(); loaded = false; }
  else start();
});
start();
