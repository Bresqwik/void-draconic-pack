// priority: 0
// Neustart-Abfrage für Updates: Das Server-Skript mc-restart-vote legt restart-vote/request.json an
// ({id, version, client, eta_min, info: [Zeilen „Was ist neu“]}). Alle Online-Spieler bekommen eine Nachricht mit [Annehmen]/[Ablehnen] (/neustart ja|nein).
// Kein Vote: ein einziges Nein (oder 10 Min. ohne alle Antworten) = abbrechen, das Update kommt beim nächsten Neustart.
// Stimmen alle zu (auch wer später dazukommt, muss zustimmen): 60 s Countdown, dann result.json {state:"go"} –
// den eigentlichen Neustart macht mc-restart-vote (systemctl). Rhino: in Funktionen let statt const.
const VD_RV_TIMEOUT = 10 * 60 * 20
let vdRv = null   // { id, version, client, eta, yes: {name:true}, start, countdown }
let vdRvLastId = null

function vdRvPrefix() { return Text.of('[Update] ').gold() }

function vdRvResult(state, extra) {
  JsonIO.write('restart-vote/result.json', Object.assign({ id: vdRv ? vdRv.id : null, state: state, time: Date.now() }, extra || {}))
}

function vdRvAsk(p) {
  let c = vdRv.client
  p.tell(vdRvPrefix().append(Text.white(`Version ${vdRv.version} ist bereit. `))
    .append(c ? Text.yellow('Client-Neustart nötig: Ja – nach dem Neustart das Spiel neu starten, Prism lädt das Update.')
              : Text.green('Client-Neustart nötig: Nein – betrifft nur den Server.')))
  if (vdRv.info.length) {
    p.tell(vdRvPrefix().append(Text.white('Was ist neu:')))
    vdRv.info.forEach(l => p.tell(Text.of('  • ').gold().append(Text.gray(l))))
  }
  p.tell(vdRvPrefix().append(Text.gray(`Der Server ist ca. ${vdRv.eta} Min. offline. Alle Online-Spieler müssen zustimmen; dann startet der Server nach 1 Minute neu. `))
    .append(Text.of('[Annehmen]').green().bold().clickRunCommand('/neustart ja').hover(Text.gray('Neustart zustimmen')))
    .append(Text.of(' '))
    .append(Text.of('[Ablehnen]').red().bold().clickRunCommand('/neustart nein').hover(Text.gray('Später – das Update kommt beim nächsten Neustart'))))
  try { p.playNotifySound('minecraft:block.note_block.bell', 'master', 1, 1) } catch (x) { }
}

function vdRvNames(server) {
  let out = []
  server.players.forEach(p => out.push(String(p.getGameProfile().getName())))
  return out
}

function vdRvCancel(server, why) {
  server.tell(vdRvPrefix().append(Text.gray(`Neustart abgebrochen (${why}). Das Update kommt beim nächsten Neustart, wenn niemand online ist.`)))
  vdRvResult('declined', { reason: why })
  vdRv = null
}

function vdRvCheck(server) {
  if (!vdRv || vdRv.countdown != null) return
  let names = vdRvNames(server)
  if (names.length === 0) return
  let missing = names.filter(n => !vdRv.yes[n])
  if (missing.length > 0) return
  vdRv.countdown = 60
  server.tell(vdRvPrefix().append(Text.green('Alle haben zugestimmt – der Server startet in 1 Minute neu. ')).append(Text.gray(`Wieder da in ca. ${vdRv.eta} Min.`)))
}

function vdRvAnswer(ctx, yes) {
  let p = ctx.source.getPlayerOrException()
  let name = String(p.getGameProfile().getName())
  if (!vdRv) { p.tell(vdRvPrefix().append(Text.gray('Gerade steht keine Neustart-Abfrage an.'))); return 0 }
  if (vdRv.countdown != null) { p.tell(vdRvPrefix().append(Text.gray('Der Neustart läuft bereits.'))); return 0 }
  if (!yes) { vdRvCancel(ctx.source.server, `${name} hat abgelehnt`); return 1 }
  vdRv.yes[name] = true
  let names = vdRvNames(ctx.source.server)
  let open = names.filter(n => !vdRv.yes[n]).length
  ctx.source.server.tell(vdRvPrefix().append(Text.gray(`${name} stimmt zu` + (open > 0 ? ` – warte noch auf ${open} Spieler.` : '.'))))
  vdRvCheck(ctx.source.server)
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event
  event.register(Commands.literal('neustart')
    .then(Commands.literal('ja').executes(ctx => vdRvAnswer(ctx, true)))
    .then(Commands.literal('nein').executes(ctx => vdRvAnswer(ctx, false))))
})

PlayerEvents.loggedIn(e => {
  if (!vdRv || vdRv.countdown != null) return
  let p = e.player
  e.server.scheduleInTicks(160, () => { try { if (vdRv) vdRvAsk(p) } catch (x) { } })
})

PlayerEvents.loggedOut(e => {
  if (vdRv) e.server.scheduleInTicks(5, () => vdRvCheck(e.server))
})

ServerEvents.tick(e => {
  let server = e.server
  if (server.tickCount % 20 !== 0) return
  // neue Anfrage?
  let req = null
  try { req = JsonIO.read('restart-vote/request.json') } catch (x) { }
  if (req && req.id != null) {
    let id = String(req.id)
    if (id !== vdRvLastId) {
      vdRvLastId = id
      // Schon beantwortet (z. B. Neustart, bevor die Anfrage gelöscht wurde)? Dann nicht erneut fragen.
      let old = null
      try { old = JsonIO.read('restart-vote/result.json') } catch (x) { }
      if (old && String(old.id) === id && (String(old.state) === 'go' || String(old.state) === 'declined')) return
      vdRv = { id: id, version: String(req.version), client: String(req.client) === 'true',
               eta: Number(req.eta_min) || 7, yes: {}, start: server.tickCount, countdown: null, info: [] }
      try { if (req.info) req.info.forEach(x => vdRv.info.push(String(x))) } catch (x) { }
      vdRvResult('asking')
      server.players.forEach(p => vdRvAsk(p))
    }
  }
  if (!vdRv) return
  if (vdRv.countdown == null) {
    if (server.tickCount - vdRv.start > VD_RV_TIMEOUT) vdRvCancel(server, 'nicht alle haben innerhalb von 10 Minuten zugestimmt')
    return
  }
  vdRv.countdown--
  let c = vdRv.countdown
  if (c === 30 || c === 10 || (c <= 5 && c > 0)) server.tell(vdRvPrefix().append(Text.yellow(`Neustart in ${c} Sekunde${c === 1 ? '' : 'n'}.`)))
  if (c <= 0) {
    server.tell(vdRvPrefix().append(Text.red(`Neustart jetzt – bis gleich (ca. ${vdRv.eta} Min.)!`)))
    vdRvResult('go')
    vdRv = null
  }
})
