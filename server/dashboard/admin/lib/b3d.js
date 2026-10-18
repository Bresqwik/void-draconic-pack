// Gemeinsame 3D-Engine für die Bauanleitungen (Void & Draconic, Admin-Dashboard).
// Original-Blockmodelle aus den Mod-JARs (models.json, gebacken), Kachel-Raster, Seiten-Einstellungen, Stoff-Fluss, Bau-Schritte.
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

export const SIDE={in:['Input','#c0392b'],out:['Output','#2f6fe0'],lin:['Left Input','#e8742c'],rin:['Right Input','#9b4dd8'],
  io:['Input/Output','#8e44ad'],extra:['Extra','#e0b925'],energy:['Energy','#2fa84f'],ext:['Externer Input','#14b8a6']};
export const MED={item:['Items','#c9a46a'],gas:['Gase','#b07cff'],fluid:['Flüssigkeit','#3b9bff'],energy:['Strom','#2fa84f'],heat:['Wärme','#ff7a3d'],redstone:['Redstone','#ff4d4d']};
const FACEN={n:[0,0,-1],s:[0,0,1],w:[-1,0,0],e:[1,0,0],u:[0,1,0],d:[0,-1,0]};
const FACEDE={n:'Norden',s:'Süden',w:'Westen',e:'Osten',u:'Oben',d:'Unten'};
const ROTY={north:0,east:-Math.PI/2,south:Math.PI,west:Math.PI/2};
const TINT={flux_point_colour:'#b56cff',flux_plug_colour:'#b56cff',flux_plug_on:'#ffffff',models_fluid_tank_side_off:'#c58cff',laser_node:'#ff5a7a'};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

export async function start(C){
  const $=id=>document.getElementById(id);
  const BAKE=await (await fetch(new URL('./models.json',import.meta.url))).json();
  // ---------- Blöcke vorbereiten ----------
  const TYPES=C.types||{};
  const B=C.blocks.map((b,i)=>{const t=b.t?TYPES[b.t]||{}:{};return {...t,...b,_i:i};});
  B.forEach(b=>{ if(b.step==null) b.step=0; });
  const byId={}; B.forEach(b=>{ if(b.id) byId[b.id]=b; });
  // Belegung + automatische Anschlüsse für Kabel/Rohre + Anschluss-Prüfung
  const OPP={n:'s',s:'n',w:'e',e:'w',u:'d',d:'u'}; const occ=new Map(); const K=(x,y,z)=>x+','+y+','+z;
  const R=b=>((b.w||1)-1)/2;
  B.forEach(b=>{ for(let dx=-R(b);dx<=R(b);dx++) for(let dz=-R(b);dz<=R(b);dz++) for(let dy=0;dy<(b.h||1);dy++) occ.set(K(b.x+dx,b.y+dy,b.z+dz),b); });
  const nbOf=(b,f)=>{const n=FACEN[f], r=R(b)+1; return occ.get(K(b.x+n[0]*r, f==='u'?b.y+(b.h||1):b.y+n[1], b.z+n[2]*r));};
  const faceOf=(b,f,med)=>(b.faces||[]).find(fc=>fc[0]===f&&(!med||fc[2]===med));
  const TMED={cable:'energy',tube:'gas',pipe:'fluid'};
  B.forEach(b=>{ if(TMED[b.m]&&!b.con) b.con=Object.keys(FACEN).filter(f=>{const nb=nbOf(b,f); if(!nb) return false; if(nb.m===b.m) return true;
    const fc=faceOf(nb,OPP[f],TMED[b.m]); if(b.m==='cable') return ['flux_point','flux_plug'].includes(nb.m)||(fc&&fc[1]==='energy');
    if(b.m==='tube') return nb.m==='radioactive_waste_barrel'||(fc&&fc[2]==='gas'); return !!fc;}); });
  const issues=[];
  B.forEach(b=>(b.faces||[]).forEach(([f,typ,med])=>{ const nb=nbOf(b,f), fc=nb&&faceOf(nb,OPP[f],med); let ok=false;
    if(typ==='energy') ok=!!nb&&(['cable','flux_point','flux_plug'].includes(nb.m)||(fc&&fc[2]==='energy'));
    else if(typ==='out') ok=!!nb&&((nb.m==='tube'&&med==='gas')||(nb.m==='pipe'&&med==='fluid')||nb.m==='radioactive_waste_barrel'||(fc&&['in','lin','rin','extra','io'].includes(fc[1])&&fc[2]===med));
    else if(typ==='ext'||med==='redstone') ok=true;
    else ok=!!nb&&((nb.m==='tube'&&med==='gas')||(nb.m==='pipe'&&med==='fluid')||(fc&&['out','io'].includes(fc[1])&&fc[2]===med));
    if(!ok) issues.push(`${b.name} ${f} ${typ}/${med} → ${nb?nb.name:'nichts'}`); }));
  if(issues.length) console.warn('B3D-CHECK',issues); else console.info('B3D-CHECK ok');
  window.B3D_ISSUES=issues;
  const STEPS=C.steps; const LAYERS=[...new Set(B.map(b=>b.y))].sort((a,b)=>a-b);
  const O=C.origin||[0,0,0]; // Bezugspunkt fürs Auseinanderziehen
  // ---------- Renderer ----------
  const host=$('view'); const coarse=matchMedia('(pointer:coarse)').matches;
  const renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});
  renderer.setPixelRatio(Math.min(devicePixelRatio,coarse?1.5:2)); renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=C.exposure||1.05;
  renderer.shadowMap.enabled=!coarse; renderer.shadowMap.type=THREE.PCFSoftShadowMap; host.prepend(renderer.domElement);
  const IMG={}; await Promise.all(Object.entries(BAKE.tex).map(([k,s])=>new Promise(r=>{const i=new Image();i.onload=()=>{IMG[k]=i;r();};i.onerror=r;i.src=s;})));
  const TC={};
  function tex(name,tint,rep){
    const key=name+(tint||'')+(rep||''); if(TC[key]) return TC[key];
    const im=IMG[name]; const N=512, cv=document.createElement('canvas'); cv.width=cv.height=N; const g=cv.getContext('2d'); g.imageSmoothingEnabled=false;
    if(im){const s=Math.min(im.width,im.height); g.drawImage(im,0,0,s,s,0,0,N,N);} else {g.fillStyle='#777';g.fillRect(0,0,N,N);}
    if(tint&&im){g.globalCompositeOperation='multiply';g.fillStyle=tint;g.fillRect(0,0,N,N);g.globalCompositeOperation='destination-in';const s=Math.min(im.width,im.height);g.drawImage(im,0,0,s,s,0,0,N,N);g.globalCompositeOperation='source-over';}
    const t=new THREE.CanvasTexture(cv); t.colorSpace=THREE.SRGBColorSpace; t.magFilter=THREE.NearestFilter; t.minFilter=THREE.LinearMipmapLinearFilter;
    t.anisotropy=renderer.capabilities.getMaxAnisotropy(); if(rep){t.wrapS=t.wrapT=THREE.RepeatWrapping;} return TC[key]=t;
  }
  const GEO={};
  function modelParts(m){
    if(GEO[m]) return GEO[m]; const out=[];
    if(m.startsWith('cube:')){ const [_,n]=m.split(':'); const g=new THREE.BoxGeometry(1,1,1); g.translate(.5,.5,.5);
      out.push([g,new THREE.MeshStandardMaterial({map:tex(n),roughness:.8,metalness:.1})]); return GEO[m]=out; }
    const md=BAKE.models[m]; if(!md){ const g=new THREE.BoxGeometry(1,1,1); g.translate(.5,.5,.5); out.push([g,new THREE.MeshStandardMaterial({color:'#888'})]); return GEO[m]=out; }
    for(const [k,arr] of Object.entries(md)){
      const [name,tf]=k.split('|'); const n=arr.length/5; const pos=new Float32Array(n*3), uv=new Float32Array(n*2);
      for(let i=0;i<n;i++){pos[i*3]=arr[i*5];pos[i*3+1]=arr[i*5+1];pos[i*3+2]=arr[i*5+2];uv[i*2]=arr[i*5+3];uv[i*2+1]=arr[i*5+4];}
      const g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.BufferAttribute(pos,3)); g.setAttribute('uv',new THREE.BufferAttribute(uv,2)); g.computeVertexNormals();
      const glass=/glass|side_off/.test(name);
      out.push([g,new THREE.MeshStandardMaterial({map:tex(name,tf?TINT[name]||'#ffffff':null),alphaTest:glass?0:.5,transparent:glass,opacity:glass?.5:1,
        side:THREE.DoubleSide,roughness:.62,metalness:.25,depthWrite:!glass})]);
    }
    return GEO[m]=out;
  }
  // ---------- Szene ----------
  const scene=new THREE.Scene(); const bg=C.background||'#0d1622';
  scene.background=new THREE.Color(bg); scene.fog=new THREE.Fog(bg,(C.fog||[40,90])[0],(C.fog||[40,90])[1]);
  const camera=new THREE.PerspectiveCamera(42,1,.05,500);
  const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.maxDistance=C.maxDist||60; controls.minDistance=2; controls.maxPolarAngle=Math.PI*.495;
  const CENTER=new THREE.Vector3(...C.center); controls.target.copy(CENTER); camera.position.set(...C.cam);
  scene.add(new THREE.HemisphereLight('#eef4ff','#3a3a46',.75)); scene.add(new THREE.AmbientLight('#ffffff',.22));
  const sun=new THREE.DirectionalLight('#fff3e0',1.9); sun.position.copy(CENTER).add(new THREE.Vector3(-10,22,14)); sun.target.position.copy(CENTER); scene.add(sun,sun.target);
  const SR=C.shadowRange||14; sun.castShadow=true; sun.shadow.mapSize.set(2048,2048); Object.assign(sun.shadow.camera,{left:-SR,right:SR,top:SR,bottom:-SR,near:1,far:80}); sun.shadow.bias=-.0005; sun.shadow.normalBias=.02;
  const rim=new THREE.DirectionalLight('#9fc4ff',.55); rim.position.copy(CENTER).add(new THREE.Vector3(16,8,-12)); scene.add(rim);
  function resize(){const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.fov=w/h<.8?66:w/h<1.2?52:40;camera.updateProjectionMatrix();}
  new ResizeObserver(resize).observe(host);

  const S={mode:'step',step:STEPS.length-1,layer:LAYERS.length-1,sides:true,flow:true,labels:true,floor:false,spread:false,hull:false,haz:true,cut:false,edges:true,detail:true,sel:null};
  const world=new THREE.Group(), floorG=new THREE.Group(), sideG=new THREE.Group(), flowG=new THREE.Group(), labG=new THREE.Group(), hazG=new THREE.Group(), extraG=new THREE.Group();
  const edgeG=new THREE.Group(), measG=new THREE.Group(); scene.add(world,floorG,sideG,flowG,labG,hazG,extraG,edgeG,measG);
  let pick=[];
  const GAP=()=>0;
  const P=b=>new THREE.Vector3(O[0]+(b.x-O[0])*(1+GAP()), b.y>O[1]?O[1]+(b.y-O[1])*(1+GAP()*.6):b.y, O[2]+(b.z-O[2])*(1+GAP()));
  const visible=b=>{ if(S.cut&&C.cut&&C.cut(b)) return false; return S.mode==='step'?b.step<=S.step:b.y<=LAYERS[S.layer]; };
  const isNew=b=>S.mode==='step'?b.step===S.step:b.y===LAYERS[S.layer];
  const ground=C.ground||{x0:-3,x1:8,z0:-3,z1:7,y:0,tex:'mc_stone'};

  function build(){
    world.clear(); pick=[];
    const groups={};
    for(const b of B){ if(!visible(b)) continue;
      if(['cable','tube','pipe','dust','torch','lever','repeater','comparator','water'].includes(b.m)){ world.add(special(b)); continue; }
      const k=b.m+'|'+(b.rot||'north')+'|'+(isNew(b)?1:0)+'|'+(b.hull&&S.hull?1:0)+'|'+(b.ghost?1:0); (groups[k]=groups[k]||[]).push(b); }
    const m4=new THREE.Matrix4(), r4=new THREE.Matrix4(), o4=new THREE.Matrix4().makeTranslation(-.5,0,-.5);
    for(const [k,list] of Object.entries(groups)){
      const [m,rot,nw,hl,gh]=k.split('|');
      for(const [geo,mat0] of modelParts(m)){
        let mat=mat0;
        if(nw==='1'||hl==='1'||gh==='1'){ mat=mat0.clone();
          if(nw==='1'){mat.emissive=new THREE.Color('#b07cff');mat.emissiveIntensity=.22;}
          if(hl==='1'){mat.transparent=true;mat.opacity=.14;mat.depthWrite=false;}
          if(gh==='1'){mat.transparent=true;mat.opacity=.35;mat.depthWrite=false;} }
        const im=new THREE.InstancedMesh(geo,mat,list.length);
        list.forEach((b,i)=>{ const p=P(b); r4.makeRotationY(ROTY[rot]); m4.makeTranslation(p.x+.5,p.y,p.z+.5).multiply(r4).multiply(o4); im.setMatrixAt(i,m4); });
        im.castShadow=hl!=='1'&&gh!=='1'; im.receiveShadow=true; im.userData.list=list; world.add(im); pick.push(im);
      }
      if(m==='turbine_rotor') for(const b of list) for(const r of [0,Math.PI/2]){
        const bl=new THREE.Mesh(new THREE.PlaneGeometry(2.7,.55),new THREE.MeshStandardMaterial({map:tex('item_turbine_blade'),transparent:true,alphaTest:.1,side:THREE.DoubleSide,metalness:.5,roughness:.4}));
        bl.rotation.x=-Math.PI/2; const g=new THREE.Group(); g.add(bl); const p=P(b); g.position.set(p.x+.5,p.y+.5,p.z+.5); g.rotation.y=r+b.y*.35; g.userData.spin=true; world.add(g); }
    }
    buildFloor(); buildEdges(); buildSides(); buildFlow(); buildLabels(); buildHaz(); if(C.extra) {extraG.clear(); C.extra({THREE,S,P,group:extraG,sprite,byId});}
    selBox(); legend(); stepTitle(); side();
  }
  function special(b,noPick){
    const g=new THREE.Group(); const p=noPick?new THREE.Vector3():P(b); g.position.set(p.x,p.y,p.z);
    if(b.m==='cable'||b.m==='tube'||b.m==='pipe'){
      const nm={cable:'universal_cable',tube:'pressurized_tube',pipe:'mechanical_pipe'}[b.m];
      const mc=new THREE.MeshStandardMaterial({map:tex('models_multipart_ultimate_'+nm),roughness:.5,metalness:.4});
      const mv=new THREE.MeshStandardMaterial({map:tex('models_multipart_ultimate_'+nm+'_vertical'),roughness:.5,metalness:.4});
      const c=new THREE.Mesh(new THREE.BoxGeometry(.375,.375,.375),mc); c.position.set(.5,.5,.5); g.add(c);
      const con=b.con||[]; // Richtungen: n,s,w,e,u,d
      for(const f of con){ const n=FACEN[f]; const L=.5-.1875+.0; const a=new THREE.Mesh(new THREE.BoxGeometry(n[0]?L:.25,n[1]?L:.25,n[2]?L:.25),mv);
        a.position.set(.5+n[0]*(.1875+L/2),.5+n[1]*(.1875+L/2),.5+n[2]*(.1875+L/2)); g.add(a); }
    } else if(b.m==='water'){ const m=new THREE.Mesh(new THREE.BoxGeometry(1,1,1),new THREE.MeshStandardMaterial({color:'#2f7fe0',transparent:true,opacity:.7,roughness:.1,metalness:.1})); m.position.set(.5,.5,.5); g.add(m);
    } else if(b.m==='dust'){ const m=new THREE.Mesh(new THREE.BoxGeometry(.98,.04,.98),new THREE.MeshStandardMaterial({map:tex('mc_redstone_dust_dot','#ff2a2a'),transparent:true,alphaTest:.1})); m.position.set(.5,.02,.5); g.add(m);
    } else if(b.m==='torch'){ const m=new THREE.Mesh(new THREE.BoxGeometry(.16,.62,.16),new THREE.MeshStandardMaterial({map:tex('mc_redstone_torch'),transparent:true,alphaTest:.1})); m.position.set(.5,.31,.5); g.add(m);
    } else if(b.m==='lever'){ const m=new THREE.Mesh(new THREE.BoxGeometry(.3,.55,.3),new THREE.MeshStandardMaterial({map:tex('mc_lever'),transparent:true,alphaTest:.1})); m.position.set(.5,.27,.5); g.add(m);
    } else if(b.m==='comparator'){ const mats=[0,1,2,3,4,5].map(i=>new THREE.MeshStandardMaterial({map:tex(i===2?'mc_comparator':'mc_stone')})); const m=new THREE.Mesh(new THREE.BoxGeometry(1,.13,1),mats); m.position.set(0,.065,0);
      const r=new THREE.Group(); r.position.set(.5,0,.5); r.rotation.y=ROTY[b.rot||'north']; r.add(m); g.add(r);
    } else if(b.m==='repeater'){ const mats=[0,1,2,3,4,5].map(i=>new THREE.MeshStandardMaterial({map:tex(i===2?'mc_repeater':'mc_stone')})); const m=new THREE.Mesh(new THREE.BoxGeometry(1,.13,1),mats); m.position.set(.5,.065,.5); g.add(m); }
    if(!noPick) g.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;o.userData.block=b;pick.push(o);}});
    return g;
  }
  // ---------- Kachel-Boden mit Raster und Achsen-Nummern ----------
  function buildFloor(){
    floorG.clear(); const G=ground;
    const W=G.x1-G.x0+1, D=G.z1-G.z0+1;
    const tx=tex(G.tex||'mc_stone','',1).clone(); tx.wrapS=tx.wrapT=THREE.RepeatWrapping; tx.repeat.set(W,D); tx.needsUpdate=true;
    const slab=new THREE.Mesh(new THREE.BoxGeometry(W,1,D),new THREE.MeshStandardMaterial({map:tx,roughness:.95,color:'#d7dbe2',transparent:S.floor,opacity:S.floor?.2:1,depthWrite:!S.floor}));
    slab.position.set(G.x0+W/2,G.y-.5,G.z0+D/2); slab.receiveShadow=true; floorG.add(slab);
    // Rasterlinien über jeder Kachel, jede 5. kräftig gelb
    const thin=[],thick=[]; const y=G.y+.006; const wc5=C.worldCoords; const f5x=x=>wc5?x%5===0:(x-G.x0)%5===0, f5z=z=>wc5?z%5===0:(z-G.z0)%5===0;
    for(let x=G.x0;x<=G.x1+1;x++) (f5x(x)?thick:thin).push(x,y,G.z0,x,y,G.z1+1);
    for(let z=G.z0;z<=G.z1+1;z++) (f5z(z)?thick:thin).push(G.x0,y,z,G.x1+1,y,z);
    for(const [arr,col,op] of [[thin,'#000000',.6],[thick,'#ffd84d',.85]]){ const lg=new THREE.BufferGeometry(); lg.setAttribute('position',new THREE.Float32BufferAttribute(arr,3));
      floorG.add(new THREE.LineSegments(lg,new THREE.LineBasicMaterial({color:col,transparent:true,opacity:op}))); }
    // Achsen-Nummern
    const wc=C.worldCoords; const step=(G.x1-G.x0)>24?5:1;
    for(let x=G.x0;x<=G.x1;x++){ if((x-G.x0)%step&&!f5x(x)) continue; const s=sprite(String(wc?x:x-G.x0+1),(wc?f5x(x):f5x(x+1))?'#ffd84d':'#9fb0c6',.26,true); s.position.set(x+.5,G.y+.05,G.z0-.55); floorG.add(s); }
    for(let z=G.z0;z<=G.z1;z++){ if((z-G.z0)%step&&!f5z(z)) continue; const s=sprite(String(wc?z:z-G.z0+1),(wc?f5z(z):f5z(z+1))?'#ffd84d':'#9fb0c6',.26,true); s.position.set(G.x0-.6,G.y+.05,z+.5); floorG.add(s); }
    const n=sprite(wc?'x →':'Spalte →','#e7ecf3',.28,true); n.position.set(G.x0+.5,G.y+.05,G.z0-1.25); floorG.add(n);
    const w=sprite(wc?'z ↓':'Reihe ↓','#e7ecf3',.28,true); w.position.set(G.x0-1.5,G.y+.05,G.z0+.5); floorG.add(w);
    const nn=sprite('N ↑','#ff6b6b',.32,true); nn.position.set(G.x0-1.5,G.y+.05,G.z0-1.25); floorG.add(nn);
  }
  // Kanten-Linien um jeden Block, damit man Blöcke und Längen abzählen kann
  function buildEdges(){
    edgeG.clear(); if(!S.edges) return;
    const pos=[]; const E=[[0,0,0,1,0,0],[0,0,0,0,1,0],[0,0,0,0,0,1],[1,1,1,0,1,1],[1,1,1,1,0,1],[1,1,1,1,1,0],[1,0,0,1,1,0],[1,0,0,1,0,1],[0,1,0,1,1,0],[0,1,0,0,1,1],[0,0,1,1,0,1],[0,0,1,0,1,1]];
    for(const b of B){ if(!visible(b)||['cable','tube','pipe','dust','torch','lever','water'].includes(b.m)) continue; if(b.hull&&S.hull) continue;
      const h=b.h||1, r=R(b), w=2*r+1; for(const [a,c,d,f,g,k] of E) pos.push(b.x-r+a*w,b.y+c*h,b.z-r+d*w,b.x-r+f*w,b.y+g*h,b.z-r+k*w); }
    if(!pos.length) return; const lg=new THREE.BufferGeometry(); lg.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
    edgeG.add(new THREE.LineSegments(lg,new THREE.LineBasicMaterial({color:'#06080c',transparent:true,opacity:.7})));
  }
  function faceQuad(b,f,col){
    const h=b.h||1, n=FACEN[f]; const geo=new THREE.PlaneGeometry(.82,.82);
    const q=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:.62,side:THREE.DoubleSide,depthWrite:false}));
    q.position.copy(P(b)).add(new THREE.Vector3(.5,.5,.5)).addScaledVector(new THREE.Vector3(...n),.53+(f==='u'||f==='d'?0:R(b))); if(f==='u'&&h>1) q.position.y+=h-1; if(f!=='u'&&f!=='d'&&h>1) q.position.y+=(h-1)/2;
    if(f==='w'||f==='e') q.rotation.y=Math.PI/2; else if(f==='u'||f==='d') q.rotation.x=Math.PI/2; q.renderOrder=5; return q;
  }
  function buildSides(){
    sideG.clear(); if(!S.sides) return;
    for(const b of B){ if(!visible(b)||!b.faces) continue;
      for(const [f,typ,med,txt,extl] of b.faces){ const q=faceQuad(b,f,SIDE[typ][1]); sideG.add(q);
        const brd=new THREE.LineSegments(new THREE.EdgesGeometry(q.geometry),new THREE.LineBasicMaterial({color:'#ffffff',transparent:true,opacity:.8}));
        brd.position.copy(q.position); brd.rotation.copy(q.rotation); brd.renderOrder=6; sideG.add(brd);
        const always=typ==='ext'||!!extl;
        if(S.labels&&(S.sel===b||always)&&f!=='d'){ const lbl=always?'⇢ '+(extl||txt||'Externer Input'):SIDE[typ][0]+(med&&med!=='energy'?' · '+MED[med][0]:'');
          const s=sprite(lbl,always?SIDE.ext[1]:SIDE[typ][1],always?.22:.24,true); s.position.copy(q.position).addScaledVector(new THREE.Vector3(...FACEN[f]),always?.42:.18); if(f==='u') s.position.y+=.12; sideG.add(s); } } }
  }
  const flowParts=[];
  function buildFlow(){
    flowG.clear(); flowParts.length=0; if(!S.flow||!C.flows) return;
    for(const fl of C.flows){ const A=byId[fl.a],Bb=byId[fl.b]; if(!A||!Bb||!visible(A)||!visible(Bb)) continue;
      const p0=P(A).add(new THREE.Vector3(.5,(fl.ya??.5),.5)), p1=P(Bb).add(new THREE.Vector3(.5,(fl.yb??.5),.5)); const color=fl.col||MED[fl.med][1];
      const tube=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,p0.distanceTo(p1),8),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.45,depthTest:false}));
      tube.position.copy(p0).lerp(p1,.5); tube.lookAt(p1); tube.rotateX(Math.PI/2); tube.renderOrder=8; flowG.add(tube);
      for(let i=0;i<3;i++){ const s=new THREE.Mesh(fl.med==='item'?new THREE.BoxGeometry(.11,.11,.11):new THREE.SphereGeometry(.065,12,8),new THREE.MeshBasicMaterial({color,depthTest:false,transparent:true}));
        s.renderOrder=9; s.userData={p0,p1,o:i/3}; flowG.add(s); flowParts.push(s); } }
  }
  function buildLabels(){
    labG.clear(); if(!S.labels) return;
    for(const b of B){ if(!visible(b)||!b.lab) continue; const q=P(b);
      const above=B.find(o=>o!==b&&o.x===b.x&&o.z===b.z&&o.y===b.y+(b.h||1)&&visible(o)&&o.lab);
      const col=b.labCol||(b.haz?'#ffd84d':'#e7ecf3'); const s=sprite(b.lab,col,b.labScale||.32);
      s.position.set(q.x+.5,q.y+(b.h||1)+.42+(above?1+GAP()*.6:0),q.z+.5); labG.add(s); }
    if(S.flow&&C.flows) for(const fl of C.flows){ const A=byId[fl.a],Bb=byId[fl.b]; if(!fl.name||!A||!Bb||!visible(A)||!visible(Bb)) continue;
      const s=sprite(fl.name,fl.col||MED[fl.med][1],.17,true); s.position.copy(P(A).add(P(Bb)).multiplyScalar(.5)).add(new THREE.Vector3(.5,(fl.ya??.5)-.32,.5)); labG.add(s); }
  }
  function buildHaz(){
    hazG.clear(); if(!S.haz||!C.hazards) return;
    for(const h of C.hazards){ const c=new THREE.Vector3(...h.pos);
      if(h.r){ const sph=new THREE.Mesh(new THREE.SphereGeometry(h.r,40,20),new THREE.MeshBasicMaterial({color:h.col||'#ff3b3b',wireframe:true,transparent:true,opacity:.14,depthWrite:false})); sph.position.copy(c); sph.userData.pulse=1; hazG.add(sph);
        const ring=new THREE.Mesh(new THREE.RingGeometry(h.r-.15,h.r+.15,96),new THREE.MeshBasicMaterial({color:h.col||'#ff3b3b',side:THREE.DoubleSide,transparent:true,opacity:.75}));
        ring.rotation.x=-Math.PI/2; ring.position.set(c.x,ground.y+.03,c.z); hazG.add(ring); }
      if(h.label){ const s=sprite(h.label,h.col||'#ff6b6b',h.scale||.6); s.position.copy(c).add(new THREE.Vector3(0,h.ly??(h.r?h.r+1:1),0)); hazG.add(s); } }
  }
  function sprite(text,color,scale=.8,thin=false){const H=128,mc=document.createElement('canvas').getContext('2d');mc.font='700 64px system-ui,sans-serif';
    const W=Math.max(150,Math.ceil(mc.measureText(text).width)+70);const c=document.createElement('canvas');c.width=W;c.height=H;const g=c.getContext('2d');
    g.font='700 64px system-ui,sans-serif';g.fillStyle=thin?'#0c0f15d0':'#0c0f15e6';g.beginPath();g.roundRect(6,14,W-12,H-28,22);g.fill();g.lineWidth=5;g.strokeStyle=color;g.stroke();
    g.fillStyle=color;g.textAlign='center';g.textBaseline='middle';g.fillText(text,W/2,H/2+3);
    const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=8;
    const s=new THREE.Sprite(new THREE.SpriteMaterial({map:t,depthTest:false,transparent:true}));s.scale.set(scale*W/H,scale,1);s.renderOrder=20;return s;}
  let selMesh=null;
  function selBox(){ if(selMesh){scene.remove(selMesh);selMesh=null;} if(!S.sel) return; const h=S.sel.h||1, w=S.sel.w||1;
    selMesh=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w+.06,h+.06,w+.06)),new THREE.LineBasicMaterial({color:'#ffd84d'}));
    selMesh.position.copy(P(S.sel)).add(new THREE.Vector3(.5,h/2,.5)); scene.add(selMesh); }

  // ---------- Bedienelemente ----------
  const ctr=$('controls'); let h='';
  if(C.layers) h+=`<div class="seg" id="modeSeg"><button data-m="step" class="on">Bau-Schritte</button><button data-m="layer">Ebenen</button></div>`;
  const opt=(id,txt,on)=>`<label class="chk"><input type="checkbox" id="${id}"${on?' checked':''}> ${txt}</label>`;
  h+=`<button id="btnRuler" class="rulerBtn" type="button" title="Lineal: Block anklicken, zweiten Block mit Shift anklicken">📏 Lineal</button>`; h+=opt('optEdges','Block-Kanten',true); h+=opt('optDetail','Detailansicht',true);
  if(B.some(b=>b.faces)) h+=opt('optSides','Seiten-Einstellungen',true);
  if(C.flows) h+=opt('optFlow','Stoff-Fluss',true);
  h+=opt('optLab','Beschriftung',true);
  if(B.some(b=>b.hull)) h+=opt('optHull','Hülle durchsichtig',false);
  if(C.hazards) h+=opt('optHaz','Gefahrenzonen',true);
  if(C.cut) h+=opt('optCut','Schnitt',false);
  h+=opt('optFloor','Boden durchsichtig',false);
  ctr.innerHTML=h;
  const on=(id,f)=>{const e=$(id); if(e) e.onchange=ev=>f(ev.target.checked);};
  on('optEdges',v=>{S.edges=v;buildEdges();}); $('btnRuler').onclick=()=>{S.ruler=!S.ruler; $('btnRuler').classList.toggle('on',S.ruler); S.measB=null; measure();}; on('optDetail',v=>{S.detail=v;detail();}); on('optSides',v=>{S.sides=v;buildSides();legend();}); on('optFlow',v=>{S.flow=v;buildFlow();buildLabels();});
  on('optLab',v=>{S.labels=v;buildLabels();buildSides();}); on('optHull',v=>{S.hull=v;build();}); on('optHaz',v=>{S.haz=v;buildHaz();});
  on('optCut',v=>{S.cut=v;build();}); on('optFloor',v=>{S.floor=v;buildFloor();});
  const slider=$('slider');
  function stepTitle(){ const el=$('stepTitle');
    if(S.mode==='step'){const st=STEPS[S.step];el.innerHTML=`Schritt ${S.step+1}/${STEPS.length}: ${esc(st.t)}<small>${esc(st.s)}</small>`;}
    else{const y=LAYERS[S.layer];el.innerHTML=`Ebene y ${y}<small>${B.filter(b=>b.y===y).length} Blöcke in dieser Ebene · alles darüber ausgeblendet</small>`;} }
  function setPos(v){ if(S.mode==='step') S.step=v; else S.layer=v; slider.value=v; build(); }
  slider.max=STEPS.length-1; slider.value=S.step; slider.oninput=e=>setPos(+e.target.value);
  $('prev').onclick=()=>setPos(Math.max(0,+slider.value-1)); $('next').onclick=()=>setPos(Math.min(+slider.max,+slider.value+1));
  document.querySelectorAll('#modeSeg button').forEach(bt=>bt.onclick=()=>{document.querySelectorAll('#modeSeg button').forEach(x=>x.classList.toggle('on',x===bt));
    S.mode=bt.dataset.m; slider.max=S.mode==='step'?STEPS.length-1:LAYERS.length-1; slider.value=S.mode==='step'?S.step:S.layer; build();});
  const nameOf=b=>b.name||'Block';
  function legend(){
    const cnt={}; B.filter(b=>isNew(b)&&visible(b)).forEach(b=>{const n=b.listName||nameOf(b).replace(/ \(.*\)| „.*“/,'');cnt[n]=(cnt[n]||0)+1;});
    let h=`<b style="margin-bottom:2px">${S.mode==='step'?'Neu in diesem Schritt':'In dieser Ebene'}</b>`+Object.entries(cnt).map(([n,c])=>`<div>${esc(n)}<b style="margin-left:auto;padding-left:10px">${c}</b></div>`).join('');
    if(S.sides&&B.some(b=>b.faces)){ const used=new Set(B.flatMap(b=>(b.faces||[]).map(f=>f[1]))); h+=`<b style="margin:8px 0 2px">Seiten (wie im Mekanism-GUI)</b>`+[...used].map(k=>`<div><span class="sw" style="background:${SIDE[k][1]}"></span>${SIDE[k][0]}</div>`).join(''); }
    $('legend').innerHTML=h; }
  const sideB=$('sideBody'), sheet=$('sheet'); $('handle').onclick=()=>sheet.classList.toggle('open');
  const phone=()=>matchMedia('(max-width:760px)').matches;
  const chip=typ=>`<span class="chip" style="background:${SIDE[typ][1]}">${SIDE[typ][0]}</span>`;
  const coordTxt=b=>C.worldCoords?`${b.x} / ${b.y} / ${b.z}`:`Spalte ${b.x-ground.x0+1} · Reihe ${b.z-ground.z0+1} · Höhe ${b.y-ground.y+1}`;
  function blockList(){ const cnt={}; B.filter(b=>!b.ghost&&!b.existing).forEach(b=>{const n=b.listName||nameOf(b).replace(/ \(.*\)| „.*“/,'');cnt[n]=(cnt[n]||0)+1;});
    return `<table class="t">`+Object.entries(cnt).sort((a,b)=>b[1]-a[1]).map(([n,c])=>`<tr><td>${esc(n)}</td><td class="r">${c}</td></tr>`).join('')+`</table>`; }
  function side(){
    const b=S.sel;
    if(!b){ $('handleTxt').textContent='Übersicht & Blockliste';
      sideB.innerHTML=(C.overview||'')+`<h4>Blöcke anspringen</h4><div class="mini">${B.filter(x=>x.id&&x.lab).map(x=>`<button data-go="${x.id}">${esc(x.lab)}</button>`).join('')}</div>
        <h4>Blockliste (alle Blöcke im Bau)</h4>${blockList()}
        <div class="muted" style="font-size:12.5px;margin-top:8px">Tipp: Block antippen für alle Einstellungen. <b>Lineal:</b> einen Block anklicken, dann einen zweiten mit <b>Shift</b> anklicken (am Handy: „📏 Lineal“ einschalten und zwei Blöcke antippen) – zeigt Länge, Breite und Höhe in Blöcken. Die gelben Linien im Boden markieren jede 5. Kachel. Modelle und Texturen sind die Originale aus den Mods auf dem Server.</div>`;
      sideB.querySelectorAll('[data-go]').forEach(x=>x.onclick=()=>{S.sel=byId[x.dataset.go];selBox();side();buildSides();detail();focus(S.sel);}); return; }
    $('handleTxt').textContent=nameOf(b);
    let h=`<button class="link" id="bk">← Übersicht</button><h2 style="margin-top:8px">${esc(nameOf(b))}</h2><div class="coord">${coordTxt(b)}</div>`;
    if(b.what) h+=`<div class="card">${b.what}</div>`;
    if(b.upg) h+=`<div class="card"><b>Upgrades:</b> ${b.upg}</div>`;
    if(b.faces){ h+=`<h4>Seiten-Einstellungen (Configurator)</h4><table class="t">`+b.faces.map(([f,typ,med,txt,extl])=>`<tr><td style="width:70px"><b>${FACEDE[f]}</b></td><td>${chip(typ)} ${med?`<span class="muted">${MED[med][0]}</span>`:''}<div style="margin-top:3px">${extl?`<b style="color:${SIDE.ext[1]}">⇢ ${esc(extl)}</b><br>`:''}${txt||''}</div></td></tr>`).join('')+`</table>`;
      if(!b.noNone) h+=`<div class="muted" style="font-size:12.5px;margin-top:6px">Alle anderen Seiten: None. „Output“ heißt: im GUI bei diesem Typ Auto-Eject einschalten.</div>`; }
    if(b.haz) h+=`<div class="card hz">☢ ${b.hazTxt||'<b>Radioaktiv:</b> Nie gefüllt abbauen, sonst wird Strahlung frei. Beim Umbauen Hazmat tragen.'}</div>`;
    if(b.warn) h+=`<div class="card wn">⚠ ${b.warn}</div>`;
    const st=STEPS[b.step]; if(st) h+=`<div class="card"><b>Bau-Schritt ${b.step+1}:</b> ${esc(st.t)}<div class="muted">${esc(st.s)}</div></div>`;
    sideB.innerHTML=h; $('bk').onclick=()=>{S.sel=null;selBox();side();buildSides();detail();};
  }
  function focus(b){ if(!b) return; const t=P(b).add(new THREE.Vector3(.5,(b.h||1)/2,.5)); const d=camera.position.clone().sub(controls.target); controls.target.copy(t); camera.position.copy(t).add(d.setLength(Math.min(d.length(),8))); if(phone()) sheet.classList.add('open'); }
  // ---------- Detailansicht ----------
  const dBox=document.createElement('div'); dBox.id='detail';
  dBox.style.cssText='position:absolute;right:12px;top:12px;width:min(320px,44vw);aspect-ratio:1;background:#0d1118f0;border:1px solid #2b3547;border-radius:12px;overflow:hidden;display:none;z-index:5;box-shadow:0 8px 24px #0009';
  dBox.innerHTML='<div id="dTitle" style="position:absolute;left:10px;top:8px;right:34px;font:600 12.5px system-ui;color:#e7ecf3;pointer-events:none;text-shadow:0 1px 2px #000"></div><button id="dClose" style="position:absolute;right:6px;top:4px;background:none;border:0;color:#8a96a8;font-size:18px;cursor:pointer" aria-label="Detailansicht schließen">✕</button><div style="position:absolute;left:10px;bottom:6px;font:11px system-ui;color:#8a96a8;pointer-events:none">Detailansicht · ziehen zum Drehen</div>';
  host.appendChild(dBox);
  const r2=new THREE.WebGLRenderer({antialias:true,alpha:true}); r2.setPixelRatio(Math.min(devicePixelRatio,2)); r2.outputColorSpace=THREE.SRGBColorSpace; r2.toneMapping=THREE.ACESFilmicToneMapping;
  dBox.prepend(r2.domElement); r2.domElement.style.display='block';
  const sc2=new THREE.Scene(); sc2.add(new THREE.HemisphereLight('#eef4ff','#3a3a46',.9)); const dl=new THREE.DirectionalLight('#fff3e0',1.6); dl.position.set(3,6,4); sc2.add(dl);
  const cam2=new THREE.PerspectiveCamera(35,1,.05,50); cam2.position.set(2.6,2.1,3.2);
  const oc2=new OrbitControls(cam2,r2.domElement); oc2.enableDamping=true; oc2.autoRotate=true; oc2.autoRotateSpeed=1.2; oc2.enablePan=false; oc2.minDistance=1.6; oc2.maxDistance=8;
  const dG=new THREE.Group(); sc2.add(dG);
  $('dClose').onclick=()=>{S.detail=false; const c=$('optDetail'); if(c) c.checked=false; detail();};
  function detail(){
    const b=S.sel; dBox.style.display=(S.detail&&b)?'block':'none'; if(!(S.detail&&b)) return;
    dG.clear(); const h=b.h||1;
    $('dTitle').textContent=nameOf(b);
    if(['cable','tube','pipe','dust','torch','lever','repeater','comparator','water'].includes(b.m)){ const g=special(b,true); g.position.set(-.5,0,-.5); dG.add(g); }
    else for(const [geo,mat] of modelParts(b.m)){ const m=new THREE.Mesh(geo,mat); const g=new THREE.Group(); m.position.set(-.5,0,-.5); g.add(m); g.rotation.y=ROTY[b.rot||'north']; const sc=1/Math.max(b.w||1,(b.h||1)/1.4,1); g.scale.setScalar(sc); dG.add(g); }
    // Bodenplatte mit Raster 3 × 3 und Himmelsrichtungen
    const gp=[]; for(let i=-1.5;i<=1.5;i++){ gp.push(i,0,-1.5,i,0,1.5,-1.5,0,i,1.5,0,i); }
    const lg=new THREE.BufferGeometry(); lg.setAttribute('position',new THREE.Float32BufferAttribute(gp,3)); dG.add(new THREE.LineSegments(lg,new THREE.LineBasicMaterial({color:'#3a475c'})));
    for(const [t,x,z,c] of [['N',0,-1.25,'#ff6b6b'],['S',0,1.25,'#9fb0c6'],['W',-1.25,0,'#9fb0c6'],['O',1.25,0,'#9fb0c6']]){ const s=sprite(t,c,.26,true); s.position.set(x,.02,z); dG.add(s); }
    const ed=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1,h,1)),new THREE.LineBasicMaterial({color:'#ffd84d',transparent:true,opacity:.6})); ed.position.set(0,h/2,0); dG.add(ed);
    const seen={};
    for(const [f,typ,med,txt,extl] of (b.faces||[])){ const n=FACEN[f];
      const q=new THREE.Mesh(new THREE.PlaneGeometry(.86,.86),new THREE.MeshBasicMaterial({color:SIDE[typ][1],transparent:true,opacity:.7,side:THREE.DoubleSide,depthWrite:false}));
      q.position.set(n[0]*.51,(f==='u'?h:f==='d'?0:.5)+(f==='u'?.01:f==='d'?-.01:0),n[2]*.51); if(f==='w'||f==='e') q.rotation.y=Math.PI/2; else if(f==='u'||f==='d') q.rotation.x=Math.PI/2; dG.add(q);
      if(seen[f]) continue; seen[f]=1;
      const all=(b.faces||[]).filter(x=>x[0]===f); const txt2=FACEDE[f]+': '+[...new Set(all.map(x=>SIDE[x[1]][0]))].join('/')+' · '+all.map(x=>MED[x[2]]?MED[x[2]][0]:'').filter(Boolean).join(' + ');
      const s=sprite(txt2,all.some(x=>x[4])?SIDE.ext[1]:SIDE[typ][1],.22,true);
      s.position.set(n[0]*1.1,(f==='u'?h+.4:f==='d'?-.3:.5+(n[0]?.16:-.16)),n[2]*1.1); dG.add(s); }
    oc2.target.set(0,h/2,0); cam2.position.set(2.6,h/2+1.6,3.2).multiplyScalar(Math.max(1,h*.75)); oc2.update();
    const w=dBox.clientWidth||300; r2.setSize(w,w); cam2.aspect=1; cam2.updateProjectionMatrix();
  }
  // ---------- Lineal ----------
  const mBox=document.createElement('div'); mBox.id='measure';
  mBox.style.cssText='position:absolute;left:50%;top:12px;transform:translateX(-50%);background:#0d1118f0;border:1px solid #2dd4e8;border-radius:12px;padding:8px 12px;font:13px system-ui;color:#e7ecf3;display:none;z-index:6;box-shadow:0 8px 24px #0009;max-width:calc(100% - 24px);text-align:center';
  host.appendChild(mBox);
  const hint=document.createElement('div'); hint.style.cssText='position:absolute;left:50%;top:12px;transform:translateX(-50%);background:#0d1118e0;border:1px dashed #2dd4e8;border-radius:10px;padding:6px 10px;font:12.5px system-ui;color:#9fe8f2;display:none;z-index:6;pointer-events:none;white-space:nowrap';
  host.appendChild(hint);
  function measure(){
    measG.clear(); const a=S.sel, b=S.measB;
    hint.style.display=(S.ruler&&!(a&&b))?'block':'none'; hint.textContent=!a?'📏 Lineal: ersten Block antippen':'📏 Jetzt den zweiten Block antippen';
    if(!a||!b){ mBox.style.display='none'; return; }
    const x0=Math.min(a.x,b.x), x1=Math.max(a.x,b.x)+1, z0=Math.min(a.z,b.z), z1=Math.max(a.z,b.z)+1;
    const y0=Math.min(a.y,b.y), y1=Math.max(a.y+(a.h||1),b.y+(b.h||1));
    const L=x1-x0, W=z1-z0, H=y1-y0;
    // Messbox
    const box=new THREE.Mesh(new THREE.BoxGeometry(L,H,W),new THREE.MeshBasicMaterial({color:'#2dd4e8',transparent:true,opacity:.08,depthWrite:false}));
    box.position.set(x0+L/2,y0+H/2,z0+W/2); measG.add(box);
    const ed=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(L,H,W)),new THREE.LineBasicMaterial({color:'#2dd4e8',depthTest:false,transparent:true}));
    ed.position.copy(box.position); ed.renderOrder=15; measG.add(ed);
    // Maßketten mit Zahlen
    const lab=(txt,x,y,z)=>{const s=sprite(txt,'#2dd4e8',.34); s.position.set(x,y,z); measG.add(s);};
    if(L>0) lab(`↔ ${L} ${L===1?'Block':'Blöcke'}`,x0+L/2,y0+.15,z1+.35);
    if(W>0) lab(`↕ ${W} ${W===1?'Block':'Blöcke'}`,x1+.35,y0+.15,z0+W/2);
    if(H>0) lab(`⇕ ${H} hoch`,x1+.35,y0+H/2,z1+.35);
    // Mittellinie A → B
    const pa=new THREE.Vector3(a.x+.5,a.y+(a.h||1)/2,a.z+.5), pb=new THREE.Vector3(b.x+.5,b.y+(b.h||1)/2,b.z+.5);
    const lg=new THREE.BufferGeometry().setFromPoints([pa,pb]); const ln=new THREE.Line(lg,new THREE.LineBasicMaterial({color:'#ffd84d',depthTest:false})); ln.renderOrder=16; measG.add(ln);
    for(const [p,c] of [[pa,'A'],[pb,'B']]){ const s=sprite(c,'#ffd84d',.3); s.position.copy(p).add(new THREE.Vector3(0,.75,0)); measG.add(s); }
    const dx=Math.abs(a.x-b.x), dy=Math.abs(a.y-b.y), dz=Math.abs(a.z-b.z);
    const gap=(d)=>d>1?` (${d-1} frei dazwischen)`:d===1?' (direkt daneben)':'';
    mBox.style.display='block';
    mBox.innerHTML=`<b style="color:#2dd4e8">📏 ${esc(nameOf(a))} → ${esc(nameOf(b))}</b>
      <div style="margin-top:4px;display:flex;gap:6px 14px;flex-wrap:wrap;justify-content:center">
       <span>Länge (x, Ost-West): <b>${L}</b></span><span>Breite (z, Nord-Süd): <b>${W}</b></span><span>Höhe (y): <b>${H}</b></span></div>
      <div class="muted" style="font-size:12px;margin-top:3px">Abstand: x ${dx}${gap(dx)} · z ${dz}${gap(dz)} · y ${dy} — alle Zahlen in Blöcken, Start- und Endblock mitgezählt <button id="mClose" style="margin-left:6px;background:none;border:0;color:#8a96a8;cursor:pointer">✕</button></div>`;
    $('mClose').onclick=()=>{S.measB=null; measure();};
  }
  // ---------- Auswahl ----------
  const ray=new THREE.Raycaster(),mouse=new THREE.Vector2(),tip=$('tip'); let down=null;
  function hit(ev){const r=renderer.domElement.getBoundingClientRect();mouse.set(((ev.clientX-r.left)/r.width)*2-1,-((ev.clientY-r.top)/r.height)*2+1);ray.setFromCamera(mouse,camera);
    const x=ray.intersectObjects(pick,false)[0]; if(!x) return null; return x.object.isInstancedMesh?x.object.userData.list[x.instanceId]:x.object.userData.block;}
  renderer.domElement.addEventListener('pointermove',ev=>{if(ev.pointerType==='touch')return;const b=hit(ev);
    if(b){tip.style.display='block';tip.style.left=ev.clientX+14+'px';tip.style.top=ev.clientY+12+'px';tip.innerHTML=`<b>${esc(nameOf(b))}</b> <span class="coord">${coordTxt(b)}</span>`;renderer.domElement.style.cursor='pointer';}
    else{tip.style.display='none';renderer.domElement.style.cursor='';}});
  renderer.domElement.addEventListener('pointerleave',()=>tip.style.display='none');
  renderer.domElement.addEventListener('pointerdown',ev=>down=[ev.clientX,ev.clientY]);
  renderer.domElement.addEventListener('pointerup',ev=>{if(!down)return;const mv=Math.hypot(ev.clientX-down[0],ev.clientY-down[1]);down=null;if(mv>6)return;
    const b=hit(ev);
    if(b&&S.sel&&b!==S.sel&&(ev.shiftKey||(S.ruler&&!S.measB))){ S.measB=b; measure(); return; }
    S.sel=b; S.measB=null; selBox();side();buildSides();detail();measure(); if(phone()&&!S.ruler) sheet.classList.toggle('open',!!S.sel);});
  const clock=new THREE.Clock();
  function loop(){const t=clock.getElapsedTime();controls.update();
    for(const p of flowParts){const {p0,p1,o}=p.userData;const k=(t*.45+o)%1;p.position.copy(p0).lerp(p1,k);p.rotation.y=t*2;}
    world.children.forEach(o=>{if(o.userData.spin)o.rotation.y+=.015;});
    hazG.children.forEach(o=>{if(o.userData.pulse)o.material.opacity=.1+.05*Math.sin(t*2);});
    extraG.children.forEach(o=>{if(o.userData.blink)o.material.opacity=.6+.3*Math.sin(t*6);});
    renderer.render(scene,camera); if(dBox.style.display==='block'){oc2.update();r2.render(sc2,cam2);} requestAnimationFrame(loop);}
  $('loading')?.remove(); build(); resize(); loop();
}
