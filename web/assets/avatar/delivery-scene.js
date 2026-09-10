import * as T from './vendor/three.module.js';
// A true 3D receiving vignette. The source illustration remains the fallback.
export function createDeliveryScene(host) {
  const renderer = new T.WebGLRenderer({alpha:true, antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=T.PCFSoftShadowMap;
  renderer.outputColorSpace=T.SRGBColorSpace;
  host.append(renderer.domElement);
  const scene=new T.Scene();
  const camera=new T.PerspectiveCamera(36,1,.1,30);
  const start=new T.Vector3(3,2.5,6.7), end=new T.Vector3(.15,1.12,2.3);
  const target=new T.Vector3(0,1.35,0);
  scene.add(new T.HemisphereLight(0xfffae9,0x7e896b,2.3));
  const sun=new T.DirectionalLight(0xffefcf,3.1);sun.position.set(-3,6,5);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-4;sun.shadow.camera.right=4;sun.shadow.camera.top=5;sun.shadow.camera.bottom=-3;sun.shadow.normalBias=.035;scene.add(sun);
  const material=(color)=>new T.MeshStandardMaterial({color,roughness:.78});
  const green=material('#465339'), slat=material('#778469'), orange=material('#b96029'), kraft=material('#c99a5c'), tape=material('#ebd1a2');
  // Bevelled silhouettes echo the softly rounded reference illustration.
  function box(w,h,d,mat,x,y,z,parent=scene,r=.035){
    r=Math.min(r,w/4,h/4,d/4);const shape=new T.Shape();
    shape.moveTo(-w/2+r,-h/2);shape.lineTo(w/2-r,-h/2);shape.quadraticCurveTo(w/2,-h/2,w/2,-h/2+r);shape.lineTo(w/2,h/2-r);shape.quadraticCurveTo(w/2,h/2,w/2-r,h/2);shape.lineTo(-w/2+r,h/2);shape.quadraticCurveTo(-w/2,h/2,-w/2,h/2-r);shape.lineTo(-w/2,-h/2+r);shape.quadraticCurveTo(-w/2,-h/2,-w/2+r,-h/2);
    const geo=new T.ExtrudeGeometry(shape,{depth:d-2*r,bevelEnabled:true,bevelThickness:r,bevelSize:r,bevelSegments:3,steps:1,curveSegments:5});geo.translate(0,0,-d/2+r);
    const mesh=new T.Mesh(geo,mat);mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;
  }
  box(2.65,.16,.9,orange,0,.12,0);
  box(.18,2.85,.26,green,-1.12,1.59,-.22);box(.18,2.85,.26,green,1.12,1.59,-.22);box(2.4,.2,.3,green,0,3.03,-.22);
  // Recessed loading passage: the parcel crosses the opening rather than a wall.
  box(2.08,2.75,.07,material('#394331'),0,1.55,-1.85);
  box(.08,2.75,1.55,green,-1.04,1.55,-1.02);box(.08,2.75,1.55,green,1.04,1.55,-1.02);
  box(2.08,.06,1.9,material('#8b8f75'),0,.2,-.85);
  const shutter=new T.Group();scene.add(shutter);
  for(let i=0;i<12;i++)box(2.08,.208,.09,slat,0,.32+i*.222,-.22,shutter,.012);
  const parcel=new T.Group();scene.add(parcel);
  box(.95,.95,.8,kraft,0,0,0,parcel,.025);
  box(.13,.95,.012,tape,0,0,.412,parcel,.004);box(.13,.012,.8,tape,0,.487,0,parcel,.004);
  // Canvas label is high-resolution, then repeated as accessible HTML details.
  const label=document.createElement('canvas');label.width=1024;label.height=512;const ctx=label.getContext('2d');
  ctx.fillStyle='#fffcf1';ctx.fillRect(0,0,1024,512);ctx.fillStyle='#294131';ctx.font='bold 44px sans-serif';ctx.fillText('DELIVERY / MATERIAL 4711',55,83);ctx.font='bold 82px sans-serif';ctx.fillText('M8 Hex Bolts',55,193);ctx.font='44px sans-serif';ctx.fillText('40 pieces · M8 × 40',55,270);ctx.fillText('Confirm before posting',55,339);
  for(let i=0;i<65;i++)ctx.fillRect(55+i*14,388,2+(i*7%6),65);
  const texture=new T.CanvasTexture(label);texture.colorSpace=T.SRGBColorSpace;
  const tag=new T.Mesh(new T.PlaneGeometry(.81,.405),new T.MeshBasicMaterial({map:texture}));tag.position.set(0,.01,.424);parcel.add(tag);
  const floor=new T.Mesh(new T.PlaneGeometry(200,200),new T.ShadowMaterial({opacity:.17}));floor.rotation.x=-Math.PI/2;floor.position.y=.02;floor.receiveShadow=true;scene.add(floor);
  let beginning=0,active=false,complete=null;
  const ease=t=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
  function resize(){const {width,height}=host.getBoundingClientRect();renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();}
  const observer=new ResizeObserver(resize);observer.observe(host);resize();
  function render(time){
    if(!active)return;
    const t=(time-beginning)/1000;
    shutter.scale.y=1-ease(t/.9)*.91;shutter.position.y=(1-shutter.scale.y)*2.9;
    // Nothing arrives until the shutter has fully opened.
    parcel.visible=t>=1.05;
    parcel.position.set(0,.66,-1.25+1.53*ease((t-1.05)/1.15));
    const zoom=ease((t-2.25)/1.65);camera.position.lerpVectors(start,end,zoom);camera.lookAt(target.clone().lerp(new T.Vector3(0,.69,.7),zoom));
    renderer.render(scene,camera);
    if(t>5.1){active=false;renderer.setAnimationLoop(null);complete?.();}
  }
  function reset(){active=false;renderer.setAnimationLoop(null);renderer.domElement.style.opacity='0';}
  reset();
  document.addEventListener('visibilitychange',()=>{if(document.hidden)reset();});
  return {play(done){resize();complete=done;beginning=performance.now();active=true;renderer.domElement.style.opacity='1';renderer.setAnimationLoop(render);},reset};
}
