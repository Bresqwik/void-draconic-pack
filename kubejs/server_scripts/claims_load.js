// priority: 0
// Claims & Last fürs Dashboard: Alle 5 Minuten misst Observable 10 Sekunden lang die echte Tickzeit jedes Mobs,
// jeder Maschine (Block-Entity) und jedes Block-Ticks. Das Skript ordnet die Zeiten den FTB-Chunks-Claims zu und
// schreibt pro Team geclaimte/forcegeladene Chunks (x/Limit) und die Last in ms/Tick nach vd-claims.json.
// Der Dashboard-Sammler liest die Datei. Läuft gerade eine Observable-Messung eines Spielers, wird ausgesetzt.
// Rhino: in Funktionen let statt const.
let VdObs = null, VdObsProps = null, VdChunksAPI = null, VdTeamsAPI = null
try {
  VdObs = Java.loadClass('observable.Observable')
  VdObsProps = Java.loadClass('observable.Props')
  VdChunksAPI = Java.loadClass('dev.ftb.mods.ftbchunks.api.FTBChunksAPI')
  VdTeamsAPI = Java.loadClass('dev.ftb.mods.ftbteams.api.FTBTeamsAPI')
} catch (x) { console.warn('[Claims-Last] Mod fehlt: ' + x) }
// Observable.getPROFILER() ist für Rhino unsichtbar (die Klasse verweist auf Client-Klassen) – daher über das Lazy-Feld
let vdObsProf = null
function vdProfiler() {
  if (vdObsProf) return vdObsProf
  let f = VdObs.INSTANCE.getClass().getDeclaredField('PROFILER$delegate')
  f.setAccessible(true)
  vdObsProf = f.get(null).getValue()
  return vdObsProf
}
let vdClaimsWarned = false
function vdClaimsWarn(x) { if (!vdClaimsWarned) { vdClaimsWarned = true; console.warn('[Claims-Last] ' + x) } }

const VD_CLAIMS_EVERY = 6000   // Ticks zwischen zwei Messungen (5 Min.)
const VD_CLAIMS_WINDOW = 200   // Messdauer in Ticks (10 s)
let vdClaims = { next: 1200, start: -1, startMs: 0 }
// Nach "kubejs reload" mitten in einer Messung würde Observable sonst weiterlaufen
try { if (VdObs && !VdObsProps.notProcessing) vdProfiler().setNotProcessing(true) } catch (x) { }

// Force-Load-Wächter: Force-Chunks laufen immer (auch offline). Wird es zu teuer oder läuft eine Farm über, steht eine
// Warnung im Dashboard, und Team-Mitglieder + OPs bekommen im Spiel einen Hinweis (je Team und Grund höchstens alle 30 Min.).
const VD_FL = { ms: 5, msCrit: 10, items: 300, itemsCrit: 1000, mobs: 60, mobsCrit: 150, every: 36000 }
let vdFlLast = {}
function vdForceWarnings(t, fms, mspt) {
  let w = []
  let at = h => h ? ` bei ${h.x} / ${h.z}` : ''
  if (fms >= VD_FL.ms) w.push({ key: 'ms', level: fms >= VD_FL.msCrit ? 'crit' : 'warn',
    text: `Force-Chunks brauchen ${fms.toFixed(1)} ms pro Tick` + (t.hot && t.hot.cause ? ` (am meisten: ${t.hot.cause}${at(t.hot)})` : '') })
  if (t.fitems >= VD_FL.items) w.push({ key: 'items', level: t.fitems >= VD_FL.itemsCrit ? 'crit' : 'warn',
    text: `${t.fitems} Items liegen in Force-Chunks – läuft eine Farm über?` })
  if (t.hot && t.hot.mobs >= VD_FL.mobs) w.push({ key: 'mobs', level: t.hot.mobs >= VD_FL.mobsCrit ? 'crit' : 'warn',
    text: `${t.hot.mobs} Mobs in einem Force-Chunk${at(t.hot)}` })
  if (mspt >= 45 && fms >= mspt * 0.25) w.push({ key: 'limit', level: 'crit',
    text: `Server am Limit (${mspt.toFixed(0)} ms/Tick), davon ${Math.round(fms / mspt * 100)} % in diesen Force-Chunks` })
  if (w.length && !t.online) w.forEach(x => { x.text += ' – niemand vom Team online' })
  return w
}
function vdForceNotify(server, list) {
  let now = server.tickCount
  list.forEach(t => {
    (t.warn || []).forEach(w => {
      let k = t.id + '|' + w.key
      if (vdFlLast[k] && now - vdFlLast[k] < VD_FL.every) return
      vdFlLast[k] = now
      console.info(`[Force-Load] ${t.name}: ${w.text}`)
      server.getPlayerList().getPlayers().forEach(p => {
        let name = String(p.getGameProfile().getName())
        let op = false
        try { op = server.getPlayerList().isOp(p.getGameProfile()) } catch (x) { }
        if (!op && t.members.indexOf(name) < 0) return
        let pre = w.level == 'crit' ? Text.of('[Force-Load] ').red() : Text.of('[Force-Load] ').gold()
        p.tell(pre.append(Text.gray(`${t.name}: ${w.text}`)))
      })
    })
  })
}

function vdClaimsCollect(server, prof, ticks, wallMs) {
  // 1) Messwerte pro Chunk sammeln
  let chunks = {}
  let total = 0
  let add = (dim, x, z, ns, kind, name, bx, by, bz) => {
    let key = dim + '|' + (x >> 4) + '|' + (z >> 4)
    let c = chunks[key] || (chunks[key] = { ns: 0, entities: 0, blocks: 0, items: {} })
    c.ns += ns
    total += ns
    if (kind == 'e') c.entities++; else c.blocks++
    let it = c.items[name] || (c.items[name] = { ns: 0, n: 0, pos: [bx, by, bz] })
    it.ns += ns
    it.n++
  }
  prof.timingsMap.entrySet().forEach(en => {
    try {
      let e = en.getKey()
      let ns = Number(en.getValue().getTime())
      add(String(e.level.dimension), e.getBlockX(), e.getBlockZ(), ns, 'e', String(e.type), e.getBlockX(), e.getBlockY(), e.getBlockZ())
    } catch (x) { }
  })
  prof.blockTimingsMap.entrySet().forEach(dimEn => {
    let dim = String(dimEn.getKey().location())
    dimEn.getValue().entrySet().forEach(en => {
      try {
        let p = en.getKey()
        let d = en.getValue()
        add(dim, p.getX(), p.getZ(), Number(d.getTime()), 'b', String(d.getName()), p.getX(), p.getY(), p.getZ())
      } catch (x) { }
    })
  })

  // 2) Claims den Teams zuordnen
  let mgr = VdChunksAPI.api().getManager()
  let teams = {}
  let claimedKeys = {}
  let teamEntry = (team) => {
    let id = String(team.getId())
    if (teams[id]) return teams[id]
    let data = mgr.getOrCreateData(team)
    let members = []
    team.getMembers().forEach(u => {
      // Name nur für Online-Spieler; sonst UUID (der Dashboard-Sammler löst sie über usercache.json auf)
      let n = null
      try { let pl = server.getPlayerList().getPlayer(u); if (pl) n = pl.getGameProfile().getName() } catch (x) { }
      members.push(String(n || u))
    })
    teams[id] = {
      name: String(team.getName().getString()), party: !!team.isPartyTeam(), members: members,
      online: team.getOnlineMembers().size(),
      claims: 0, max_claims: data.getMaxClaimChunks(), force: 0, max_force: data.getMaxForceLoadChunks(),
      ns: 0, entities: 0, blocks: 0, items: {}, dims: {},
      fns: 0, fitems: 0, fmobs: 0, hot: null   // nur Force-Chunks: Zeit, Item-Entities, Mobs, teuerster Chunk
    }
    return teams[id]
  }
  mgr.getAllClaimedChunks().forEach(cc => {
    try {
      let t = teamEntry(cc.getTeamData().getTeam())
      let pos = cc.getPos()
      let dim = String(pos.dimension().location())
      let key = dim + '|' + pos.x() + '|' + pos.z()
      claimedKeys[key] = true
      t.claims++
      if (cc.isForceLoaded()) t.force++
      t.dims[dim] = (t.dims[dim] || 0) + 1
      let c = chunks[key]
      if (c) {
        t.ns += c.ns
        t.entities += c.entities
        t.blocks += c.blocks
        Object.keys(c.items).forEach(k => {
          let it = t.items[k] || (t.items[k] = { ns: 0, n: 0, pos: c.items[k].pos })
          it.ns += c.items[k].ns
          it.n += c.items[k].n
        })
        if (cc.isForceLoaded()) {
          let drops = c.items['minecraft:item'] ? c.items['minecraft:item'].n : 0
          t.fns += c.ns
          t.fitems += drops
          t.fmobs += c.entities - drops
          if (!t.hot || c.ns > t.hot.ns) {
            let cause = Object.keys(c.items).sort((a, b) => c.items[b].ns - c.items[a].ns)[0]
            t.hot = { ns: c.ns, dim: dim, x: pos.x() * 16 + 8, z: pos.z() * 16 + 8, mobs: c.entities - drops, items: drops,
                      cause: cause ? cause.replace(/^(block|entity)\./, '') + ' ×' + c.items[cause].n : '' }
          }
        }
      }
    } catch (x) { }
  })
  // Spieler ohne Claims auch zeigen (eigenes Team, wenn sie in keiner Party sind)
  try {
    let tm = VdTeamsAPI.api().getManager()
    tm.getTeams().forEach(team => {
      if (team.isServerTeam()) return
      if (team.isPlayerTeam()) {
        let cur = tm.getTeamForPlayerID(team.getId()).orElse(null)
        if (cur && String(cur.getId()) != String(team.getId())) return
      }
      teamEntry(team)
    })
  } catch (x) { }

  let wildNs = 0
  Object.keys(chunks).forEach(k => { if (!claimedKeys[k]) wildNs += chunks[k].ns })
  let mspt = Number(server.getAverageTickTime())
  let perTick = ns => Math.round(ns / ticks / 1e4) / 100
  let list = Object.keys(teams).map(id => {
    let t = teams[id]
    let top = Object.keys(t.items).map(k => ({ name: k, n: t.items[k].n, ms: perTick(t.items[k].ns), pos: t.items[k].pos }))
      .sort((a, b) => b.ms - a.ms).slice(0, 5)
    return {
      id: id, name: t.name, party: t.party, members: t.members, online: t.online,
      claims: t.claims, max_claims: t.max_claims, force: t.force, max_force: t.max_force,
      ms: perTick(t.ns), pct: mspt > 0 ? Math.round(perTick(t.ns) / mspt * 1000) / 10 : 0,
      entities: t.entities, blocks: t.blocks, top: top, dims: t.dims,
      force_ms: perTick(t.fns), force_items: t.fitems, force_mobs: t.fmobs,
      hot: t.hot ? { ms: perTick(t.hot.ns), dim: t.hot.dim, x: t.hot.x, z: t.hot.z, mobs: t.hot.mobs, items: t.hot.items, cause: t.hot.cause } : null,
      warn: vdForceWarnings(t, perTick(t.fns), mspt)
    }
  }).sort((a, b) => b.ms - a.ms || b.claims - a.claims)
  vdForceNotify(server, list)
  JsonIO.write('vd-claims.json', {
    time: Date.now(), ticks: ticks, window_s: Math.round(wallMs / 100) / 10, mspt: Math.round(mspt * 10) / 10,
    measured_ms: perTick(total), wild_ms: perTick(wildNs), teams: list
  })
}

ServerEvents.tick(event => {
  if (!VdObs || !VdChunksAPI) return
  let server = event.server
  let tc = server.tickCount
  try {
    let prof = vdProfiler()
    if (vdClaims.start < 0) {
      if (tc < vdClaims.next) return
      vdClaims.next = tc + VD_CLAIMS_EVERY
      if (!VdObsProps.notProcessing) return   // jemand nutzt Observable gerade selbst
      prof.startRunning(false)
      vdClaims.start = tc
      vdClaims.startMs = Date.now()
    } else if (tc - vdClaims.start >= VD_CLAIMS_WINDOW) {
      prof.setNotProcessing(true)
      let ticks = tc - vdClaims.start
      let wall = Date.now() - vdClaims.startMs
      vdClaims.start = -1
      try { vdClaimsCollect(server, prof, ticks, wall) } catch (x) { vdClaimsWarn(x) }
      prof.timingsMap.clear()
      prof.blockTimingsMap.clear()
    }
  } catch (x) { vdClaimsWarn(x); vdClaims.start = -1; vdClaims.next = tc + VD_CLAIMS_EVERY }
})
