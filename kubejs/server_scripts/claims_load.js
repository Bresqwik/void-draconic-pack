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
      ns: 0, entities: 0, blocks: 0, items: {}, dims: {}
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
      entities: t.entities, blocks: t.blocks, top: top, dims: t.dims
    }
  }).sort((a, b) => b.ms - a.ms || b.claims - a.claims)
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
