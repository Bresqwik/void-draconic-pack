// Bauplan-Seite aus derselben Projekt-Konfiguration wie die 3D-Ansicht.
// 2D-Plan (Kacheln mit Original-Texturen, Raster, Achsen-Nummern), Seiten-Einstellungen, Block-/Maschinenliste, Materialliste, Bau-Schritte.
const SIDE={in:['Input','#c0392b'],out:['Output','#2f6fe0'],lin:['Left Input','#e8742c'],rin:['Right Input','#9b4dd8'],
  io:['Input/Output','#8e44ad'],extra:['Extra','#e0b925'],energy:['Energy','#2fa84f'],ext:['Externer Input','#14b8a6']};
const MED={item:'Items',gas:'Gase',fluid:'Flüssigkeit',energy:'Strom',heat:'Wärme',redstone:'Redstone'};
const FACEDE={n:'Norden',s:'Süden',w:'Westen',e:'Osten',u:'Oben',d:'Unten'};
const ARROW={n:[0,-1],s:[0,1],w:[-1,0],e:[1,0]};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// Welche Textur zeigt die Draufsicht? (erste passende des Modells)
const TOPTEX={cable:'models_multipart_ultimate_universal_cable',tube:'models_multipart_ultimate_pressurized_tube',pipe:'models_multipart_ultimate_mechanical_pipe',water:null,dust:'mc_redstone_dust_dot',torch:'mc_redstone_torch',lever:'mc_lever',repeater:'mc_repeater',comparator:'mc_comparator'};
const COLOR={cable:'#3a4a5c',tube:'#5b6b7a',water:'#2f7fe0'};

export async function guide(C){
  const G=C.guide||{}; const $=id=>document.getElementById(id);
  const BAKE=await (await fetch(new URL('./models.json',import.meta.url))).json();
  const TYPES=C.types||{}; const B=C.blocks.map((b,i)=>({...(b.t?TYPES[b.t]||{}:{}),...b,_i:i})); B.forEach(b=>{if(b.step==null)b.step=0;});
  const topTex=b=>{ if(b.m in TOPTEX) return TOPTEX[b.m]; if(b.m.startsWith('cube:')) return b.m.slice(5);
    const md=BAKE.models[b.m]; if(!md) return null; const ks=Object.keys(md).map(k=>k.split('|')[0]);
    return ks.find(k=>/top|controller|frame|casing|valve|vent|port|glass|chamber|tank|barrel|factory|_on$|laser|node|enderchest/.test(k)&&!/led|ports$/.test(k))||ks[0]; };
  const nameOf=b=>b.name||'Block'; const listName=b=>b.listName||nameOf(b).replace(/ \(.*\)| „.*“/,'');
  const gr=C.ground||{x0:-2,x1:6,z0:-2,z1:4,y:0};
  // ---------- Kopf, Navigation ----------
  const secs=[['ueberblick','Überblick'],['plan','Bauplan'],['seiten','Seiten-Einstellungen'],['bloecke','Block-/Maschinenliste'],['material','Materialliste'],['schritte','Bau-Schritte'],...(G.sections||[]).map(s=>[s.id,s.title])];
  $('toc').innerHTML=secs.map(([id,t])=>`<a href="#${id}">${t}</a>`).join('')+`<a href="${G.link3d||'3d.html'}">◈ 3D-Ansicht</a>`;
  let h='';
  h+=`<section id="ueberblick"><h2>Überblick</h2><p class="lead">${G.lead||''}</p>`;
  if(G.kpis) h+=`<div class="kpi">${G.kpis.map(([v,l])=>`<div><b>${v}</b><span>${l}</span></div>`).join('')}</div>`;
  if(G.chain) h+=`<div class="card tw" style="margin-top:12px"><table class="t"><tr><th>Maschine</th><th>Rezept</th><th>${G.chainHead||'Menge'}</th></tr>${G.chain.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</table></div>`;
  if(G.note) h+=`<div class="muted" style="font-size:13px;margin-top:8px">${G.note}</div>`;
  h+=`<a class="big3d" href="${G.link3d||'3d.html'}">◈ 3D-Ansicht öffnen<span>Original-Modelle, Seiten-Einstellungen, Stoff-Fluss, Bau-Schritte</span></a></section>`;
  // ---------- 2D-Plan ----------
  const LAYERS=[...new Set(B.map(b=>b.y))].sort((a,b)=>a-b);
  const defLayer=G.planLayer??(LAYERS.includes(gr.y)?gr.y:LAYERS[0]);
  h+=`<section id="plan"><h2>Bauplan</h2><p class="lead">Von oben gesehen, Norden ist oben. Jede Kachel ist ein Block, jede 5. Linie ist gelb. Die Zahlen am Rand ${C.worldCoords?'sind die Weltkoordinaten':'zählen Spalten und Reihen'}. <b>Tippe auf einen Block</b> für seine Einstellungen.</p>
    <div class="layers" id="layerBtns"></div><div class="grid2"><div class="card"><div id="planSvg"></div><div class="legend" id="planLegend"></div></div><div class="card" id="info"></div></div></section>`;
  // ---------- Seiten-Einstellungen ----------
  const withFaces=B.filter(b=>b.faces&&b.faces.length);
  h+=`<section id="seiten"><h2>Seiten-Einstellungen</h2><p class="lead">Mit dem <b>Configurator</b>: Modus mit Shift + Rechtsklick in die Luft wählen (Items, Gase, Flüssigkeiten, Energie), dann Shift + Rechtsklick auf die Fläche, bis der Typ stimmt. <b>Auto-Eject</b> im GUI beim jeweiligen Typ einschalten, wo „Output“ steht. Alle anderen Seiten auf <b>None</b>.</p>
    <div class="card tw"><table class="t"><tr><th>Block</th><th>Seite</th><th>Typ</th><th>Einstellung</th></tr>${withFaces.map(b=>b.faces.map((f,i)=>`<tr><td>${i?'':esc(nameOf(b))}</td><td>${FACEDE[f[0]]}</td><td><span class="chip" style="background:${SIDE[f[1]][1]}">${SIDE[f[1]][0]}</span> <span class="muted">${MED[f[2]]||''}</span></td><td>${f[4]?`<b style="color:${SIDE.ext[1]}">⇢ ${esc(f[4])}</b><br>`:''}${esc(f[3]||'')}</td></tr>`).join('')).join('')}</table></div></section>`;
  // ---------- Block-/Maschinenliste ----------
  const cnt={}, info={}; const NEWB=B.filter(b=>!b.ghost&&!b.existing), OLD=B.length-NEWB.length; NEWB.forEach(b=>{const n=listName(b); cnt[n]=(cnt[n]||0)+1; if(!info[n]) info[n]=b;});
  h+=`<section id="bloecke"><h2>Block- und Maschinenliste</h2><p class="lead">Jeder Block, der gesetzt wird, gezählt aus dem Bauplan.</p>
    <div class="card tw"><table class="t"><tr><th></th><th>Block</th><th>Aufgabe</th><th style="text-align:right">Anzahl</th></tr>${Object.entries(cnt).sort((a,b)=>b[1]-a[1]).map(([n,c])=>{const b=info[n];const tx=topTex(b);
      return `<tr><td style="width:34px">${tx&&BAKE.tex[tx]?`<img class="ic" src="${BAKE.tex[tx]}" alt="">`:`<span class="ic" style="background:${COLOR[b.m]||'#555'}"></span>`}</td><td><b>${esc(n)}</b></td><td class="muted">${(b.short||b.what||'').replace(/<[^>]+>/g,'').slice(0,140)}</td><td class="n">${c}</td></tr>`;}).join('')}
      <tr><td></td><td><b>Neu zu setzen</b></td><td class="muted">${OLD?OLD+' Blöcke stehen schon (nur zur Orientierung im Plan)':''}</td><td class="n">${NEWB.length}</td></tr></table></div></section>`;
  // ---------- Materialliste ----------
  const M=G.materials||{};
  h+=`<section id="material"><h2>Materialliste</h2><div class="grid2">`;
  if(M.craft) h+=`<div class="card"><h3>Was du craften musst</h3><table class="t">${M.craft.map(([n,c,r])=>`<tr><td><b>${esc(n)}</b>${r?`<div class="muted" style="font-size:12.5px">${esc(r)}</div>`:''}</td><td class="n">${c}</td></tr>`).join('')}</table></div>`;
  if(M.raw) h+=`<div class="card"><h3>${M.rawTitle||'Rohstoffe gesamt'}</h3><table class="t">${M.raw.map(([n,c])=>`<tr><td>${esc(n)}</td><td class="n">${c}</td></tr>`).join('')}</table>${M.rawNote?`<div class="muted" style="font-size:12.5px;margin-top:6px">${M.rawNote}</div>`:''}</div>`;
  h+=`</div>${M.extra||''}</section>`;
  // ---------- Bau-Schritte ----------
  h+=`<section id="schritte"><h2>Bau-Schritte</h2><div class="card" style="padding:10px 14px"><div style="display:flex;justify-content:space-between;font-size:13px"><span>Fortschritt</span><span id="progTxt">0</span></div><div class="progress"><i id="progBar"></i></div></div>
    ${C.steps.map((s,i)=>{const c={};B.filter(b=>b.step===i).forEach(b=>{const n=listName(b);c[n]=(c[n]||0)+1;});
      return `<div class="step" data-i="${i}"><div class="n">${i+1}</div><div><h3>${esc(s.t)}</h3><div>${esc(s.s)}</div>${Object.keys(c).length?`<div class="muted" style="font-size:13px;margin-top:4px">${Object.entries(c).map(([n,k])=>`${k}× ${esc(n)}`).join(' · ')}</div>`:''}<label class="check"><input type="checkbox" data-i="${i}"> erledigt</label></div></div>`;}).join('')}</section>`;
  for(const s of (G.sections||[])) h+=`<section id="${s.id}"><h2>${s.title}</h2>${s.html}</section>`;
  $('content').innerHTML=h;
  // Fortschritt merken
  const key='steps-'+(G.key||location.pathname);
  let done=[]; try{done=JSON.parse(localStorage.getItem(key)||'[]')}catch(e){}
  const upd=()=>{const n=document.querySelectorAll('#schritte input:checked').length;$('progTxt').textContent=n+' / '+C.steps.length;$('progBar').style.width=(n/C.steps.length*100)+'%';};
  document.querySelectorAll('#schritte input').forEach(c=>{const i=+c.dataset.i; if(done.includes(i)){c.checked=true;c.closest('.step').classList.add('done');}
    c.onchange=()=>{c.closest('.step').classList.toggle('done',c.checked);const d=[...document.querySelectorAll('#schritte input:checked')].map(x=>+x.dataset.i);try{localStorage.setItem(key,JSON.stringify(d))}catch(e){}upd();};}); upd();
  // ---------- 2D-Plan zeichnen ----------
  let layer=defLayer, sel=null;
  const xs=[gr.x0,gr.x1], zs=[gr.z0,gr.z1];
  function plan(){
    const S=G.cell||(gr.x1-gr.x0>16?30:56), P=34, W=(xs[1]-xs[0]+1), H=(zs[1]-zs[0]+1);
    let s=`<svg viewBox="0 0 ${W*S+P+8} ${H*S+P+8}" role="img" aria-label="Bauplan Ebene ${layer}" style="image-rendering:pixelated">`;
    const X=x=>P+(x-xs[0])*S, Z=z=>P+(z-zs[0])*S; const f5x=x=>C.worldCoords?x%5===0:(x-xs[0])%5===0, f5z=z=>C.worldCoords?z%5===0:(z-zs[0])%5===0;
    for(let x=xs[0];x<=xs[1];x++) for(let z=zs[0];z<=zs[1];z++) s+=`<rect x="${X(x)}" y="${Z(z)}" width="${S}" height="${S}" fill="${(x+z)%2?'#1a212d':'#161c27'}"/>`;
    // Blöcke darunter (eine Ebene tiefer) blass, Blöcke dieser Ebene voll
    const RR=b=>((b.w||1)-1)/2; const here=B.filter(b=>b.y<=layer&&b.y+(b.h||1)>layer), below=B.filter(b=>b.y+(b.h||1)===layer&&!here.some(o=>o.x===b.x&&o.z===b.z));
    const cell=(b,op)=>{const tx=topTex(b); const x=X(b.x-RR(b)),y=Z(b.z-RR(b)), Q=S*(b.w||1);
      let r=tx&&BAKE.tex[tx]&&!(b.w>1)?`<image href="${BAKE.tex[tx]}" x="${x+1}" y="${y+1}" width="${Q-2}" height="${Q-2}" opacity="${op}" preserveAspectRatio="none"/>`:`<rect x="${x+2}" y="${y+2}" width="${Q-4}" height="${Q-4}" rx="4" fill="${b.col||COLOR[b.m]||'#666'}" opacity="${op}"/>`;
      return r;};
    below.forEach(b=>s+=cell(b,.25));
    here.forEach(b=>{ s+=`<g class="cell${sel===b?' sel':''}" data-i="${b._i}">${cell(b,1)}<rect class="b" x="${X(b.x-RR(b))+1}" y="${Z(b.z-RR(b))+1}" width="${S*(b.w||1)-2}" height="${S*(b.w||1)-2}" fill="transparent" stroke="${b.haz?'#ffd84d':'#0009'}" stroke-width="${b.haz?2:1}"/>`;
      if(b.short2||b.abbr) s+=`<text x="${X(b.x)+S/2}" y="${Z(b.z)+S*(1+RR(b))-5}" text-anchor="middle" fill="#fff" font-size="${Math.max(9,S/4.2)}" font-weight="800" style="paint-order:stroke;stroke:#000;stroke-width:3px;pointer-events:none">${esc(b.abbr||b.short2)}</text>`;
      for(const f of (b.faces||[])){ if(!ARROW[f[0]]||!['out','in','lin','rin','extra','io'].includes(f[1])) continue; const [dx,dz]=ARROW[f[0]];
        const cx=X(b.x)+S/2+dx*S*(.38+RR(b)), cz=Z(b.z)+S/2+dz*S*(.38+RR(b)); s+=`<rect x="${cx-(dx?3:S*.22)}" y="${cz-(dz?3:S*.22)}" width="${dx?6:S*.44}" height="${dz?6:S*.44}" fill="${SIDE[f[1]][1]}" style="pointer-events:none"/>`; }
      s+='</g>'; });
    // Rasterlinien + Achsen
    for(let x=xs[0];x<=xs[1]+1;x++) s+=`<line x1="${X(x)}" y1="${P}" x2="${X(x)}" y2="${Z(zs[1]+1)}" stroke="${f5x(x)?'#ffd84d':'#000'}" stroke-opacity="${f5x(x)?.6:.5}" stroke-width="${f5x(x)?1.4:1}"/>`;
    for(let z=zs[0];z<=zs[1]+1;z++) s+=`<line x1="${P}" y1="${Z(z)}" x2="${X(xs[1]+1)}" y2="${Z(z)}" stroke="${f5z(z)?'#ffd84d':'#000'}" stroke-opacity="${f5z(z)?.6:.5}" stroke-width="${f5z(z)?1.4:1}"/>`;
    const every=W>24?5:1;
    for(let x=xs[0];x<=xs[1];x++) if((x-xs[0])%every===0||f5x(x)) s+=`<text x="${X(x)+S/2}" y="${P-10}" text-anchor="middle" fill="${f5x(x+1)&&!C.worldCoords||C.worldCoords&&f5x(x)?'#ffd84d':'#8a96a8'}" font-size="11">${C.worldCoords?x:x-xs[0]+1}</text>`;
    for(let z=zs[0];z<=zs[1];z++) if((z-zs[0])%every===0||f5z(z)) s+=`<text x="${P-6}" y="${Z(z)+S/2+4}" text-anchor="end" fill="${f5z(z+1)&&!C.worldCoords||C.worldCoords&&f5z(z)?'#ffd84d':'#8a96a8'}" font-size="11">${C.worldCoords?z:z-zs[0]+1}</text>`;
    s+=`<text x="4" y="14" fill="#ff6b6b" font-size="12" font-weight="700">N ↑</text></svg>`;
    $('planSvg').innerHTML=s;
    $('planSvg').querySelectorAll('.cell').forEach(g=>g.onclick=()=>{sel=B[+g.dataset.i];plan();show();});
    const used=new Set(); here.forEach(b=>(b.faces||[]).forEach(f=>used.add(f[1])));
    $('planLegend').innerHTML=[...used].map(k=>`<span><i class="sw" style="background:${SIDE[k][1]}"></i>${SIDE[k][0]}</span>`).join('')+`<span class="muted">Balken am Blockrand = Seite mit dieser Einstellung</span>`;
    $('layerBtns').innerHTML=LAYERS.map(y=>`<button class="${y===layer?'on':''}" data-y="${y}">Ebene ${C.worldCoords?'y '+y:y-gr.y+1}${y<gr.y?' (Boden)':''}</button>`).join('');
    $('layerBtns').querySelectorAll('button').forEach(bt=>bt.onclick=()=>{layer=+bt.dataset.y;plan();});
  }
  function show(){
    const b=sel; if(!b){$('info').innerHTML=`<h3>Block antippen</h3><div class="muted">Hier erscheinen Aufgabe, Upgrades und alle Seiten-Einstellungen des Blocks.</div>`;return;}
    const coord=C.worldCoords?`${b.x} / ${b.y} / ${b.z}`:`Spalte ${b.x-gr.x0+1} · Reihe ${b.z-gr.z0+1} · Ebene ${b.y-gr.y+1}`;
    $('info').innerHTML=`<h3>${esc(nameOf(b))}</h3><div class="muted" style="font:12px ui-monospace,monospace">${coord}</div><div style="margin-top:8px">${b.what||''}</div>
      ${b.upg?`<div style="margin-top:8px"><span class="pill">${b.upg}</span></div>`:''}
      ${b.faces?`<table class="t" style="margin-top:8px">${b.faces.map(f=>`<tr><td style="width:70px"><b>${FACEDE[f[0]]}</b></td><td><span class="chip" style="background:${SIDE[f[1]][1]}">${SIDE[f[1]][0]}</span> <span class="muted">${MED[f[2]]||''}</span><div>${f[4]?`<b style="color:${SIDE.ext[1]}">⇢ ${esc(f[4])}</b><br>`:''}${esc(f[3]||'')}</div></td></tr>`).join('')}</table>`:''}
      ${b.haz?`<div class="warn">☢ Radioaktiv: nie gefüllt abbauen.</div>`:''}`;
  }
  plan(); show();
}
