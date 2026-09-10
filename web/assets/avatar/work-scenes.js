import * as T from './vendor/three.module.js';
export function createWorkScene(host,kind) {
  const renderer=new T.WebGLRenderer({alpha:true,antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;host.append(renderer.domElement);
  const scene=new T.Scene(),camera=new T.PerspectiveCamera(36,1,.1,30);
  scene.add(new T.HemisphereLight(0xfff8e5,0x738064,2.5));const light=new T.DirectionalLight(0xffefcf,3);light.position.set(-3,6,5);light.castShadow=true;light.shadow.mapSize.set(1024,1024);light.shadow.normalBias=.03;scene.add(light);
  const mat=c=>new T.MeshStandardMaterial({color:c,roughness:.8});const green=mat('#48573a'),orange=mat('#b9632d'),binmat=mat('#778466'),paper=mat('#fff9e8');
  function box(w,h,d,m,x,y,z,parent=scene){const shape=new T.Shape(),r=Math.min(.03,w/5,h/5,d/5);shape.moveTo(-w/2+r,-h/2);shape.lineTo(w/2-r,-h/2);shape.quadraticCurveTo(w/2,-h/2,w/2,-h/2+r);shape.lineTo(w/2,h/2-r);shape.quadraticCurveTo(w/2,h/2,w/2-r,h/2);shape.lineTo(-w/2+r,h/2);shape.quadraticCurveTo(-w/2,h/2,-w/2,h/2-r);shape.lineTo(-w/2,-h/2+r);shape.quadraticCurveTo(-w/2,-h/2,-w/2+r,-h/2);const geometry=new T.ExtrudeGeometry(shape,{depth:d-2*r,bevelEnabled:true,bevelSize:r,bevelThickness:r,bevelSegments:2,steps:1});geometry.translate(0,0,-d/2+r);const mesh=new T.Mesh(geometry,m);mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  function label(lines,w,h){const cv=document.createElement('canvas');cv.width=1024;cv.height=Math.round(1024*h/w);const ctx=cv.getContext('2d');ctx.fillStyle='#fffaeb';ctx.fillRect(0,0,cv.width,cv.height);ctx.fillStyle='#2b4334';lines.forEach((line,i)=>{ctx.font=i===0?'bold 72px sans-serif':'48px sans-serif';ctx.fillText(line,60,110+i*112);});const tex=new T.CanvasTexture(cv);tex.colorSpace=T.SRGBColorSpace;return new T.Mesh(new T.PlaneGeometry(w,h),new T.MeshBasicMaterial({map:tex}));}
  let focus,focusTarget,start,end,lookStart,lookEnd;
  if(kind==='storage'){
    for(const x of [-1.1,1.1])box(.15,3,.65,green,x,1.6,0);
    for(let row=0;row<3;row++){
      const y=.3+row*.9;box(2.35,.13,.95,orange,0,y,0);
      for(let col=0;col<2;col++){const group=new T.Group();group.position.set(-.53+col*1.06,y+.4,0);scene.add(group);box(.88,.66,.72,binmat,0,0,0,group);box(.95,.065,.79,green,0,.34,0,group);const tag=label(row===1&&col===0?['MATERIAL 4711','M8 Hex Bolts','A–03–02','240 on hand']:['STOCK',`A–0${row+2}–0${col+1}`],.66,.40);tag.position.set(0,.015,.373);group.add(tag);if(row===1&&col===0)focus=group;}
    }
    focusTarget=focus.position.clone();start=new T.Vector3(3,2.5,6.5);end=new T.Vector3(-.6,1.63,2.5);lookStart=new T.Vector3(0,1.5,0);lookEnd=new T.Vector3(-.53,1.6,.6);
  }else{
    box(2.5,.14,1.3,green,0,1,0);for(const x of [-1.03,1.03])for(const z of [-.48,.48])box(.15,.94,.15,green,x,.49,z);
    box(.18,.52,.18,green,0,1.36,-.38);box(1.48,.94,.14,green,0,1.94,-.43);const screen=label(['RECEIPT REVIEW','Material 4711','40 pieces','Confirm reversal'],1.29,.75);screen.position.set(0,1.95,-.35);scene.add(screen);
    focus=new T.Group();focus.position.set(-.28,1.10,.2);focus.rotation.x=-Math.PI/2;scene.add(focus);box(.91,1.13,.025,paper,0,0,0,focus);const receipt=label(['RECEIPT REVIEW','M8 Hex Bolts · 40','Bin A–03–02','Keep both records'],.84,1.02);receipt.position.z=.02;focus.add(receipt);
    box(.27,.34,.27,orange,.87,1.23,-.19);for(let i=0;i<3;i++){const pen=box(.027,.43,.027,green,.8+i*.06,1.53,-.2);pen.rotation.z=(i-1)*.13;}
    start=new T.Vector3(3,3,6);end=new T.Vector3(-.28,1.53,2.7);lookStart=new T.Vector3(0,1.25,0);lookEnd=new T.Vector3(-.28,1.55,.4);
  }
  const floor=new T.Mesh(new T.PlaneGeometry(200,200),new T.ShadowMaterial({opacity:.15}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
  const ease=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x);};let begin=0,active=false,done;
  function resize(){const b=host.getBoundingClientRect();renderer.setSize(b.width,b.height,false);camera.aspect=b.width/b.height;camera.updateProjectionMatrix();}new ResizeObserver(resize).observe(host);
  function frame(now){if(!active)return;const t=(now-begin)/1000,p=ease((t-.4)/1.2),zoom=ease((t-1.1)/1.8);if(kind==='storage')focus.position.z=focusTarget.z+p*.48;else{focus.rotation.x=-Math.PI/2+p*Math.PI/2;focus.position.y=1.1+p*.5;focus.position.z=.2+p*.25;}camera.position.lerpVectors(start,end,zoom);camera.lookAt(lookStart.clone().lerp(lookEnd,zoom));renderer.render(scene,camera);if(t>4.4){active=false;renderer.setAnimationLoop(null);done?.();}}
  function reset(){active=false;renderer.setAnimationLoop(null);renderer.domElement.style.opacity='0';}reset();document.addEventListener('visibilitychange',()=>{if(document.hidden)reset();});
  return{reset,play(callback){resize();done=callback;begin=performance.now();active=true;frame(begin);renderer.domElement.style.opacity='1';renderer.setAnimationLoop(frame);}};
}
