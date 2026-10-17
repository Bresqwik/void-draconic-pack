// priority: 10
// /afk: AFK an/aus. Automatisch AFK nach 5 Min. ohne Bewegung/Umschauen/Chat/Klicks; jede Aktivität holt zurück.
// Anzeige: Team vd_afk mit grauem „[AFK] “ vor dem Namen (Tab-Liste und über dem Kopf), Chat-Hinweis für alle.
// Wer 10 Min. oder länger AFK ist, zählt bei der Neustart-Abstimmung nicht mit (restart_vote.js nutzt vdAfkLong).
// Schlafen: playersSleepingPercentage = 1 – ein Schlafender reicht, AFK-Spieler blockieren also nie.
// Stand fürs Dashboard: vd-afk.json {players: {Name: {since, manual}}, time}. Rhino: in Funktionen let statt const.
const VD_AFK_AUTO = 5 * 60 * 1000     // automatisch AFK nach 5 Min.
const VD_AFK_VOTE = 10 * 60 * 1000    // ab 10 Min. AFK zählt man bei der Abstimmung nicht mit
const VD_AFK_TEAM = 'vd_afk'
let vdAfk = {}                         // Name -> { afk, since, manual, last, pos, grace }

function vdAfkState(name) {
  if (!vdAfk[name]) vdAfk[name] = { afk: false, since: 0, manual: false, last: Date.now(), pos: null, grace: 0 }
  return vdAfk[name]
}

function vdAfkSave() {
  let out = {}
  Object.keys(vdAfk).forEach(n => { let s = vdAfk[n]; if (s.afk) out[n] = { since: s.since, manual: s.manual } })
  try { JsonIO.write('vd-afk.json', { players: out, time: Date.now() }) } catch (x) { }
}

// Für restart_vote.js: true, wenn der Spieler mindestens 10 Minuten AFK ist
function vdAfkLong(name) {
  let s = vdAfk[String(name)]
  return !!(s && s.afk && Date.now() - s.since >= VD_AFK_VOTE)
}

function vdAfkSet(server, p, on, manual) {
  let name = String(p.username)
  let s = vdAfkState(name)
  if (s.afk === on) return
  let now = Date.now()
  if (on) {
    s.afk = true; s.since = manual ? now : s.last; s.manual = !!manual; s.grace = now + 3000
    server.runCommandSilent(`team join ${VD_AFK_TEAM} ${name}`)
    server.tell(Text.gray(`${name} ist jetzt AFK.`))
  } else {
    let mins = Math.max(0, Math.round((now - s.since) / 60000))
    s.afk = false; s.manual = false; s.last = now
    server.runCommandSilent(`team leave ${name}`)
    server.tell(Text.gray(`${name} ist wieder da` + (mins >= 1 ? ` (${mins} Min. AFK).` : '.')))
  }
  vdAfkSave()
}

function vdAfkActive(server, p) {
  let s = vdAfkState(String(p.username))
  if (Date.now() < s.grace) return
  s.last = Date.now()
  if (s.afk) vdAfkSet(server, p, false, false)
}

ServerEvents.loaded(event => {
  let server = event.server
  server.runCommandSilent(`team add ${VD_AFK_TEAM}`)
  server.runCommandSilent(`team modify ${VD_AFK_TEAM} prefix {"text":"[AFK] ","color":"gray"}`)
  server.runCommandSilent(`team modify ${VD_AFK_TEAM} color gray`)
  vdAfkSave()
})

PlayerEvents.loggedIn(event => {
  let name = String(event.player.username)
  event.server.runCommandSilent(`team leave ${name}`)
  vdAfk[name] = { afk: false, since: 0, manual: false, last: Date.now(), pos: null, grace: 0 }
  vdAfkSave()
})

PlayerEvents.loggedOut(event => {
  let name = String(event.player.username)
  event.server.runCommandSilent(`team leave ${name}`)
  delete vdAfk[name]
  vdAfkSave()
})

// Bewegung / Umschauen einmal pro Sekunde prüfen
PlayerEvents.tick(event => {
  let p = event.player
  if (p.age % 20 !== 0) return
  let s = vdAfkState(String(p.username))
  let yr = 0, xr = 0
  try { yr = Number(p.getYRot()); xr = Number(p.getXRot()) } catch (x) { try { yr = Number(p.yaw); xr = Number(p.pitch) } catch (y) { } }
  let cur = [Number(p.x), Number(p.y), Number(p.z), yr, xr]
  let prev = s.pos
  s.pos = cur
  if (prev) {
    let moved = Math.abs(cur[0] - prev[0]) + Math.abs(cur[2] - prev[2]) > 0.3 && !p.isPassenger()
    let looked = Math.abs(cur[3] - prev[3]) + Math.abs(cur[4] - prev[4]) > 1
    if (moved || looked) { vdAfkActive(event.server, p); return }
  }
  if (!s.afk && Date.now() - s.last >= VD_AFK_AUTO) vdAfkSet(event.server, p, true, false)
})

PlayerEvents.chat(event => vdAfkActive(event.server, event.player))
BlockEvents.broken(event => { if (event.player) vdAfkActive(event.server, event.player) })
BlockEvents.placed(event => { if (event.player) vdAfkActive(event.server, event.player) })
BlockEvents.rightClicked(event => vdAfkActive(event.server, event.player))
ItemEvents.rightClicked(event => vdAfkActive(event.server, event.player))

ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event
  event.register(Commands.literal('afk').executes(ctx => {
    let p = ctx.source.getPlayerOrException()
    let s = vdAfkState(String(p.username))
    vdAfkSet(ctx.source.server, p, !s.afk, true)
    return 1
  }))
})
