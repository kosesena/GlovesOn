import * as THREE from './vendor/three.module.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

// The character lives in the lobby - not on the landing page, where an 8 MB
// GLB cannot take the place of a 68 KB image. Whoever reaches the lobby has
// already said "start the shift"; they are interested enough to wait.
const hero = document.querySelector('#avatarStage');
const photo = null;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let resetStage;
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
    // Transparent until the first frame is ready: however late the model
    // arrives, it fades in rather than popping in.
    renderer.domElement.style.opacity = '0';
    renderer.domElement.style.transition = 'opacity .45s ease';
    renderer.domElement.setAttribute('aria-hidden', 'true');
    renderer.domElement.addEventListener('webglcontextlost', fallback);
    const [gltf, data] = await Promise.all([
      new GLTFLoader().loadAsync('/assets/avatar/worker.glb?v=2'),
      fetch('/assets/avatar/motions.json?v=4').then(r => { if (!r.ok) throw Error('Motion unavailable'); return r.json(); })
    ]);
    if (reduced.matches) { renderer.dispose(); loaded = false; return; }
    const scene = new THREE.Scene();
    // Vertical framing 2.37 -> 2.05 units: the figure stands larger in the same scene.
    const camera = new THREE.OrthographicCamera(-2, 2, 1.90, -.15, .1, 20);
    camera.position.set(0, 0, 6);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9b927f, 2.5));
    const light = new THREE.DirectionalLight(0xffffff, 2.7);
    light.position.set(3, 5, 4); scene.add(light);
    const actor = new THREE.Group(); actor.add(gltf.scene); scene.add(actor);
    const mixer = new THREE.AnimationMixer(gltf.scene);
    // The rest pose: the idle clip also moved the feet (walking in place).
    // Instead we hold a fixed pose, arms clasped in front of the body, with
    // breathing layered on and, occasionally, a hand reaching to the
    // headset. Bind rotations are saved and deltas are added on top.
    const bones = {}; gltf.scene.traverse(o => { if (o.isBone) bones[o.name] = o; });
    const bind = {}; for (const [n, b] of Object.entries(bones)) bind[n] = b.rotation.clone();
    // key: [dx, dy, dz] added to the bind pose. Tuned by trial.
    const restPose = {
      RightArm:     [ .18,  0,   -.30],
      LeftArm:      [ .18,  0,    .30],
      RightForeArm: [1.28,  .15, -.10],
      LeftForeArm:  [1.28, -.15,  .10],
      RightHand:    [ .10,  0,    0  ],
      LeftHand:     [ .10,  0,    0  ],
      Spine02:      [ .04,  0,    0  ],
    };
    // The headset-touch gesture. The pose is MEASURED, not guessed:
    // two-bone analytic IK puts the fingertip 13.6 mm off the headset cup,
    // palm facing the head, not a single vertex entering the face. The
    // numbers are ABSOLUTE LOCAL quaternions - they replace the bone's
    // rotation. The two earlier attempts broke because they added Euler
    // deltas to the bind pose: restPose's bend stacked on the gesture's.
    const touchEnd = {
      RightArm:     new THREE.Quaternion( .182833,  .457002, -.112686, .863147),
      RightForeArm: new THREE.Quaternion(-.805635, -.007894, -.408775, .428711),
      RightHand:    new THREE.Quaternion( .256318,  .666348, -.411145, .566781),
    };
    // The waypoint: the arm opens sideways first. A direct slerp drags 306
    // of the hand's vertices through the face and the head clearance drops
    // to half a millimetre; this path is 12% longer but never enters the
    // face and keeps 89 mm from the head.
    const touchVia = {
      RightArm:     new THREE.Quaternion( .215778, -.372928, -.159126, .888281),
      RightForeArm: new THREE.Quaternion( .225803,  .083197, -.031354, .970107),
      RightHand:    new THREE.Quaternion( .093683,  .009770, -.001906, .995552),
    };
    // Each bone splits at its own arc length. A single shared midpoint made
    // the wrist accelerate 7x in one frame right at the middle, and it read
    // as a whip - the paths differ 3.6x in length.
    const touchSplit = { RightArm: .366, RightForeArm: .177, RightHand: .086 };
    const TOUCH = { period: 10, rise: .62, hold: .30, fall: .68 };
    const touchSpan = TOUCH.rise + TOUCH.hold + TOUCH.fall;
    const touchScratch = new THREE.Quaternion();
    let touchClock = 0, touchNow = 0, idleVariant = 0;
    let lookAt = 0, lookFrom = 0, lookStarted = 0, nextLook = 3.5;
    let lookYaw = 0;
    function updateLook(t) {
      if (t >= nextLook) {
        lookFrom = lookYaw;
        lookAt = Math.random() < .45 ? 0 : (Math.random() - .5) * .24;
        lookStarted = t;
        nextLook = t + 3 + Math.random() * 4;
      }
      const blend = smoothstep(Math.min(1, (t - lookStarted) / .9));
      lookYaw = THREE.MathUtils.lerp(lookFrom, lookAt, blend);
      if (bones.Head) bones.Head.rotation.y += lookYaw;
    }

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
      // Breathing: a very slight sway in the chest and head.
      if (bones.Spine01) bones.Spine01.rotation.x += Math.sin(t) * .022;
      if (bones.Head)    bones.Head.rotation.x    += Math.sin(t * .9 + 1) * .015;
    }
    // Travel uses the mixer; greetings sample arm rotations independently.
    const actions = { walk: mixer.clipAction(THREE.AnimationClip.parse(data.walk)) };
    // Sample the authored greeting on the arm only, keeping the feet planted.
    const greetingClip = THREE.AnimationClip.parse(data.wave);
    const greetingTracks = greetingClip.tracks
      .filter(track => /^(RightShoulder|RightArm|RightForeArm|RightHand)\.quaternion$/.test(track.name))
      .map(track => ({bone: bones[track.name.split('.')[0]], sample: track.createInterpolant()}));
    const greetingRotation = new THREE.Quaternion();
    const WAVE = {rise: 1.25, hold: 2.2, fall: 1.35, poseTime: 1.5};
    let greetingDuration = WAVE.rise + WAVE.hold + WAVE.fall;
    let greetingCount = 0, greetingIsWave = true;
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
      // Switching to the greeting while the arm reaches for the headset
      // teleported the wrist half a metre in one frame. The greeting is
      // cosmetic: ignore it until the gesture finishes.
      if (touchNow > 0) return;
      mixer.stopAllAction(); current = null;
      greetingIsWave = greetingCount++ % 2 === 0;
      greetingDuration = greetingIsWave ? WAVE.rise + WAVE.hold + WAVE.fall : 3.4;
      phase = 'wave'; phaseStart = elapsed;
    }
    bubble = document.createElement('p');
    bubble.className = 'avatar-line';
    bubble.textContent = 'Pick a spot.\nI’ll meet you there.';
    hero.append(bubble);
    greet = document.createElement('button'); greet.className = 'avatar-greet';
    greet.setAttribute('aria-label', 'Say hello to your warehouse guide');
    // Greetings are intentional; moving the pointer past the guide does not restart them.
    greet.addEventListener('click', () => {
      wave();
      // Speech requires an intentional click, never an automatic idle gesture.
      if (phase === 'wave' && 'speechSynthesis' in window && !speechSynthesis.speaking) {
        const utterance = new SpeechSynthesisUtterance(greetingIsWave ? 'Hi there!' : 'Okay!');
        utterance.lang = 'en-US'; utterance.rate = 1; utterance.pitch = 1.1;
        speechSynthesis.speak(utterance);
      }
    });
    autoIntro = false;
    // The one hook exposed outward: when an area is chosen the character
    // walks to that card and returns a promise. The screen changes when the
    // promise resolves.
    window.gloveson = window.gloveson || {};
    window.gloveson.avatarWalkTo = (key) => {
      const card = document.querySelector(`[data-enter="${key}"]`);
      if (!card || reduced.matches || !visible) return null;
      if (arrival) { const cancel = arrival; arrival = null; cancel(); }
      bubble?.classList.add('is-away');
      const stage = hero.getBoundingClientRect(), target = card.getBoundingClientRect();
      // Convert the card's centre into scene coordinates: -half .. +half
      const ratio = ((target.left + target.width / 2) - stage.left) / stage.width;
      const half = camera.right;
      document.getElementById('warehouseRoom')?.classList.add('avatar-travelling');
      return new Promise(resolve => {
        travelFrom = actor.position.x;
        travelTo = (ratio - .5) * 2 * half * .82;
        if (Math.abs(travelFrom - travelTo) < .05) { resolve(); return; }
        phase = 'walk'; phaseStart = elapsed; play('walk');
        arrival = resolve;
        // The fuse derives from the walk duration: a fixed 2600 ms changed
        // the screen before the character on a long walk.
        const expect = Math.max(.9, Math.abs(travelTo - travelFrom) / 1.5) * 1000 + 600;
        setTimeout(() => { if (arrival === resolve) { arrival = null; resolve(); } }, expect);
      }).finally(() => document.getElementById('warehouseRoom')?.classList.remove('avatar-travelling'));
    };
    resetStage = (event) => {
      document.getElementById('warehouseRoom')?.classList.remove('avatar-travelling');
      if (arrival) { const cancel = arrival; arrival = null; cancel(); }
      phase = 'idle'; touchNow = 0; touchClock = 0;
      mixer.stopAllAction(); current = null;
      actor.position.set(home, 0, 0); actor.rotation.set(0, 0, 0);
      if (event.detail === 'lobby') bubble?.classList.remove('is-away');
    };
    window.addEventListener('gloveson:warehouse-stage', resetStage);
    hero.append(renderer.domElement, greet);
    function resize() {
      const height = hero.clientHeight, width = hero.clientWidth;
      if (!height || !width) return;
      const half = width / height * 2.05 / 2;
      camera.left = -half; camera.right = half; camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      // The scene's left edge, not its centre: standing in the middle put
      // the guide in front of the options, reading as the choice itself
      // rather than someone waiting for yours. It waits at the edge and
      // walks over once an area is chosen.
      // .88 -> .78: the arm reaching for the headset extends 0.59 m out of
      // the body, and at .88 only 0.36 m remained to the left edge, so the
      // arm was clipped at the panel boundary. The cost is the figure
      // shifting ~50 px right; the left gap is 278 px, so it still keeps
      // its own lane, well clear of the first card.
      home = Math.max(-camera.right * .78, camera.left + .62); near = home;
      if (phase === 'idle' && !arrival) actor.position.x = home;
    }
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(hero); resize();
    let previous = performance.now();
    renderer.setAnimationLoop(now => {
      const dt = Math.min((now - previous) / 1000, .05); previous = now;
      if (!visible || document.hidden || reduced.matches) return;
      elapsed += dt;
      if (phase === 'idle') {
        // No clip: the fixed rest pose + breathing, every frame. The feet
        // stay in the bind pose, which ends the "walking in place".
        applyRest(elapsed * 1.6);
        touchClock += dt;
        if (touchClock >= TOUCH.period) { touchClock -= TOUCH.period; idleVariant = (idleVariant + 1) % 3; }
        updateLook(elapsed);
        const gesture = touchWeight(touchClock);
        touchNow = gesture;
        if (idleVariant === 0 && gesture > 0) applyTouch(gesture);
        if (idleVariant === 1 && bones.Head) bones.Head.rotation.y += gesture * .18;
        if (idleVariant === 2 && bones.Head) bones.Head.rotation.x += gesture * .08;
        const answering = idleVariant === 0 && gesture > .8;
        bubble.textContent = answering ? (greetingIsWave ? 'Hi there!' : 'Okay!') : 'Pick a spot.\nI’ll meet you there.';
        bubble.classList.toggle('is-speaking', answering);
        if (answering && !greetingIsWave && bones.Head) bones.Head.rotation.x += Math.sin(elapsed * 10) * .018;
        actor.position.y = Math.sin(elapsed * 1.6) * .006;
        actor.rotation.z = Math.sin(elapsed * .8) * .004;
      } else if (phase === 'wave') {
        // Blend the authored wave into and out of the planted rest pose.
        // Restore every bone first so no travel pose can remain on the legs.
        applyRest(elapsed * 1.6);
        const t = elapsed - phaseStart;
        const envelope = smoothstep(Math.max(0, Math.min(1, t / 1.1, (greetingDuration - t) / 1.2)));
        if (greetingIsWave) {
          const progress = Math.max(0, Math.min(1, t / WAVE.rise,
            (greetingDuration - t) / WAVE.fall));
          // Quintic easing starts and ends with zero velocity and acceleration.
          const lift = progress ** 3 * (progress * (progress * 6 - 15) + 10);
          // Blend directly to one stable pose; resampling the source lift introduced jitter.
          for (const {bone, sample} of greetingTracks) {
            if (!bone) continue;
            greetingRotation.fromArray(sample.evaluate(WAVE.poseTime)).normalize();
            // Keep a relaxed elbow bend in the raised greeting pose.
            if (bone === bones.RightForeArm) {
              greetingRotation.multiply(new THREE.Quaternion().setFromAxisAngle(
                new THREE.Vector3(1, 0, 0), .35));
            }
            bone.quaternion.slerp(greetingRotation, lift);
          }
          const hold = (t - WAVE.rise) / WAVE.hold;
          if (hold > 0 && hold < 1 && bones.RightHand) {
            // Two small wrist sweeps with a zero-velocity entrance and exit.
            const soften = Math.sin(Math.PI * hold) ** 2;
            bones.RightHand.rotateZ(Math.sin(hold * Math.PI * 4) * .14 * soften);
          }
        } else {
          // Keep the fitted headset path separate from the waving arm clip.
          applyTouch(envelope);
        }
        const answering = t > .75 && t < 2;
        bubble.textContent = answering ? (greetingIsWave ? 'Hi there!' : 'Okay!') : 'Pick a spot.\nI’ll meet you there.';
        bubble.classList.toggle('is-speaking', answering);
        if (answering && !greetingIsWave && bones.Head) bones.Head.rotation.x += Math.sin(t * 10) * .018;
        if (bones.Head) bones.Head.rotation.x += Math.sin(Math.min(1, t / greetingDuration) * Math.PI) * .06;
        touchNow = 0;
        actor.position.y = 0; actor.rotation.z = 0;
      } else {
        bubble.classList.remove('is-speaking');
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
        if (phase === 'wave' && elapsed - phaseStart > greetingDuration) { phase = 'idle'; phaseStart = elapsed; touchClock = TOUCH.period - touchSpan - 2; if (current) { current.stop(); current = null; } }
      }
      // Keep the greeting target on the guide, clear of the task cards.
      const span = camera.right - camera.left;
      greet.style.left = ((actor.position.x - .34 - camera.left) / span * 100) + '%';
      greet.style.width = (.68 / span * 100) + '%';
      greet.style.top = '0'; greet.style.bottom = 'auto'; greet.style.height = '100%';
      greet.style.pointerEvents = phase === 'walk' ? 'none' : 'auto';
      renderer.render(scene, camera);
      if (renderer.domElement.style.opacity === '0') renderer.domElement.style.opacity = '1';
    });
    observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { threshold: .1 });
    observer.observe(hero);
  } catch (error) { fallback(); console.warn('Avatar fallback:', error.message); }
}
reduced.addEventListener('change', () => {
  if (reduced.matches) { fallback(); observer?.disconnect(); resizeObserver?.disconnect(); renderer?.dispose(); renderer?.domElement.remove(); greet?.remove(); bubble?.remove();
    window.removeEventListener('gloveson:warehouse-stage', resetStage);
    if (window.gloveson) delete window.gloveson.avatarWalkTo;
    loaded = false; }
  else start();
});
start();
