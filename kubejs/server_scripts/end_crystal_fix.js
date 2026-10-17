// priority: 0
// Fix für YUNG's Better End Island: Nach dem Drachen-Respawn bleiben die 4 Beschwörungskristalle am Ausgangsportal stehen
// (Invulnerable, lassen sich nicht zerstören) – Vanilla würde sie beim Erscheinen des Drachen sprengen.
// 1) Stirbt der Drache: 5 s später übrig gebliebene unverwundbare Kristalle am Portal (0/57/0, Umkreis 14) entfernen.
// 2) Reserve alle 5 Min.: Liegen dort unverwundbare Kristalle und lebt kein Drache, beim zweiten Treffer in Folge entfernen
//    (ein laufender Respawn dauert < 1 Min. und wird so nie unterbrochen). Rhino: in Funktionen let statt const.
const VD_EC_KILL = 'execute in minecraft:the_end run kill @e[type=minecraft:end_crystal,x=0,y=58,z=0,distance=..14,nbt={Invulnerable:1b}]'
let vdEcSeen = false

function vdEcClean(server, why) {
  let n = server.runCommandSilent(VD_EC_KILL)
  if (n > 0) console.info(`[End-Kristalle] ${n} hängende Beschwörungskristalle entfernt (${why})`)
}

EntityEvents.death('minecraft:ender_dragon', event => {
  let server = event.server
  server.scheduleInTicks(100, () => { try { vdEcClean(server, 'Drache besiegt') } catch (x) { console.warn('[End-Kristalle] ' + x) } })
})

ServerEvents.tick(event => {
  let server = event.server
  if (server.tickCount % 6000 !== 0) return
  try {
    let stuck = server.runCommandSilent('execute in minecraft:the_end if entity @e[type=minecraft:end_crystal,x=0,y=58,z=0,distance=..14,nbt={Invulnerable:1b}]') > 0
    let dragon = server.runCommandSilent('execute in minecraft:the_end if entity @e[type=minecraft:ender_dragon]') > 0
    if (stuck && !dragon && vdEcSeen) { vdEcClean(server, 'kein Drache, seit 5 Min. hängend'); vdEcSeen = false }
    else vdEcSeen = stuck && !dragon
  } catch (x) { }
})
