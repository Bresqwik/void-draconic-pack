// priority: 0
// Neustart-Abfrage für Updates: Das Server-Skript mc-restart-vote legt restart-vote/request.json an
// ({id, version, client, eta_min, info: [Zeilen „Was ist neu“]}). Alle Online-Spieler bekommen eine Nachricht mit
// [Annehmen] / [Ja, in … Min.] / [Ablehnen] (/neustart ja | ja <1–60> | nein). Mit Zeit: Neustart erst nach der längsten
// gewünschten Wartezeit aller Zustimmungen (höchstens 60 Min.); ungültige Zeit → Hinweis und erneute Frage.
// Kein Vote: ein einziges Nein (oder 10 Min. ohne alle Antworten) = abbrechen, das Update kommt beim nächsten Neustart.
// Stimmen alle zu (auch wer später dazukommt, muss zustimmen; wer ≥10 Min. AFK ist, zählt nicht mit – afk.js): 60 s Countdown, dann result.json {state:"go"} –
// den eigentlichen Neustart macht mc-restart-vote (systemctl). Rhino: in Funktionen let statt const.
const VD_RV_TIMEOUT = 10 * 60 * 20
const VD_RV_MAX_DELAY = 60   // Minuten
let vdRv = null   // { id, version, client, eta, yes: {name:true}, delay: {name:min}, start, countdown }
let vdRvLastId = null

function vdRvPrefix() { return Text.of('[Update] ').gold() }

function vdRvResult(state, extra) {
  JsonIO.write('restart-vote/result.json', Object.assign({ id: vdRv ? vdRv.id : null, state: state, time: Date.now() }, extra || {}))
}

// Hinweis, ob die Spieler nach dem Neustart ihr Spiel neu starten müssen (Pack-Update mit Client-Änderungen)
function vdRvClientHint() {
  return vdRv && vdRv.client
    ? Text.yellow('Danach bitte das Spiel neu starten – Prism lädt dabei das Update.')
    : Text.green('Danach einfach wieder verbinden – kein Spiel-Neustart nötig.')
}

function vdRvAsk(p) {
  let c = vdRv.client
  p.tell(vdRvPrefix().append(Text.white(`Version ${vdRv.version} ist bereit. `))
    .append(c ? Text.yellow('Client-Neustart nötig: Ja – nach dem Neustart das Spiel neu starten, Prism lädt das Update.')
              : Text.green('Client-Neustart nötig: Nein – betrifft nur den Server.')))
  p.tell(vdRvPrefix().append(Text.white('Was ist neu:')))
  if (vdRv.info.length) vdRv.info.forEach(l => p.tell(Text.of('  • ').gold().append(Text.gray(l))))
  else p.tell(Text.of('  • ').gold().append(Text.gray('Kleine Korrekturen und Verbesserungen.')))
  p.tell(vdRvPrefix().append(Text.gray(`Der Server ist ca. ${vdRv.eta} Min. offline. Alle Online-Spieler müssen zustimmen; dann startet der Server nach 1 Minute neu. `))
    .append(Text.of('[Annehmen]').green().bold().clickRunCommand('/neustart ja').hover(Text.gray('Neustart zustimmen')))
    .append(Text.of(' '))
    .append(Text.of('[Ja, in … Min.]').yellow().bold().clickSuggestCommand('/neustart ja ')
      .hover(Text.gray(`Zustimmen, aber erst später neu starten: Minuten eintippen (1–${VD_RV_MAX_DELAY}), z. B. /neustart ja 15`)))
    .append(Text.of(' '))
    .append(Text.of('[Ablehnen]').red().bold().clickRunCommand('/neustart nein').hover(Text.gray('Später – das Update kommt beim nächsten Neustart'))))
  try { p.playNotifySound('minecraft:block.note_block.bell', 'master', 1, 1) } catch (x) { }
}

// Wer 10 Min. oder länger AFK ist (afk.js), muss nicht zustimmen
function vdRvAfk(name) { try { return vdAfkLong(name) } catch (x) { return false } }

function vdRvNames(server) {
  let out = []
  server.players.forEach(p => { let n = String(p.getGameProfile().getName()); if (!vdRvAfk(n)) out.push(n) })
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
  if (names.length === 0 && server.players.size() === 0) return   // leer: das Server-Skript startet ohnehin direkt neu
  let missing = names.filter(n => !vdRv.yes[n])
  if (missing.length > 0) return
  // längste gewünschte Wartezeit der aktuell Zustimmenden (mindestens 1 Minute)
  let wait = 0, who = ''
  names.forEach(n => { let d = vdRv.delay[n] || 0; if (d > wait) { wait = d; who = n } })
  vdRv.countdown = Math.max(60, wait * 60)
  vdRvResult('countdown', { seconds: vdRv.countdown })
  if (wait > 1) server.tell(vdRvPrefix().append(Text.green(`Alle haben zugestimmt – der Server startet in ${wait} Minuten neu `))
    .append(Text.gray(`(Wunsch von ${who}). Wieder da ca. ${vdRv.eta} Min. danach. `)).append(vdRvClientHint()))
  else server.tell(vdRvPrefix().append(Text.green('Alle haben zugestimmt – der Server startet in 1 Minute neu. ')).append(Text.gray(`Wieder da in ca. ${vdRv.eta} Min. `)).append(vdRvClientHint()))
}

// Restzeit als Text („12 Min.“ / „45 Sek.“)
function vdRvRest(sec) { return sec >= 60 ? `${Math.ceil(sec / 60)} Min.` : `${sec} Sek.` }

// delayText: null = ohne Zeit, sonst die eingetippte Minutenangabe
function vdRvAnswer(ctx, yes, delayText) {
  let p = ctx.source.getPlayerOrException()
  let name = String(p.getGameProfile().getName())
  if (!vdRv) { p.tell(vdRvPrefix().append(Text.gray('Gerade steht keine Neustart-Abfrage an.'))); return 0 }
  if (vdRv.countdown != null) { p.tell(vdRvPrefix().append(Text.gray(`Der Neustart läuft bereits – noch ${vdRvRest(vdRv.countdown)}.`))); return 0 }
  if (!yes) { vdRvCancel(ctx.source.server, `${name} hat abgelehnt`); return 1 }
  let delay = 0
  if (delayText != null) {
    let t = String(delayText).trim()
    let m = /^(\d{1,3})\s*(m|min|min\.|minute|minuten)?$/i.exec(t)
    let n = m ? parseInt(m[1], 10) : NaN
    if (!m || !(n >= 1 && n <= VD_RV_MAX_DELAY)) {
      p.tell(vdRvPrefix().append(Text.red(`„${t}“ geht nicht – bitte eine Zeit von 1 bis ${VD_RV_MAX_DELAY} Minuten angeben, z. B. /neustart ja 15. `))
        .append(Text.gray('Deine Antwort wurde nicht gezählt.')))
      vdRvAsk(p)
      return 0
    }
    delay = n
  }
  vdRv.yes[name] = true
  vdRv.delay[name] = delay
  let names = vdRvNames(ctx.source.server)
  let open = names.filter(n => !vdRv.yes[n]).length
  ctx.source.server.tell(vdRvPrefix().append(Text.gray(`${name} stimmt zu` + (delay > 0 ? ` (Neustart frühestens in ${delay} Min.)` : '') +
    (open > 0 ? ` – warte noch auf ${open} Spieler.` : '.'))))
  vdRvCheck(ctx.source.server)
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('neustart')
    .then(Commands.literal('ja').executes(ctx => vdRvAnswer(ctx, true, null))
      .then(Commands.argument('minuten', Arguments.GREEDY_STRING.create(event))
        .executes(ctx => vdRvAnswer(ctx, true, Arguments.GREEDY_STRING.getResult(ctx, 'minuten')))))
    .then(Commands.literal('nein').executes(ctx => vdRvAnswer(ctx, false, null))))
})

PlayerEvents.loggedIn(e => {
  if (!vdRv) return
  let p = e.player
  if (vdRv.countdown != null) {
    e.server.scheduleInTicks(160, () => { try { if (vdRv && vdRv.countdown != null) p.tell(vdRvPrefix().append(Text.yellow(`Update ${vdRv.version}: Der Server startet in ${vdRvRest(vdRv.countdown)} neu. `)).append(vdRvClientHint())) } catch (x) { } })
    return
  }
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
               eta: Number(req.eta_min) || 7, yes: {}, delay: {}, start: server.tickCount, countdown: null, info: [] }
      try { if (req.info) req.info.forEach(x => vdRv.info.push(String(x))) } catch (x) { }
      vdRvResult('asking')
      server.players.forEach(p => vdRvAsk(p))
    }
  }
  if (!vdRv) return
  if (vdRv.countdown == null) {
    if (server.tickCount % 200 === 0) vdRvCheck(server)   // falls jemand inzwischen 10 Min. AFK ist
    if (server.tickCount - vdRv.start > VD_RV_TIMEOUT) vdRvCancel(server, 'nicht alle haben innerhalb von 10 Minuten zugestimmt')
    return
  }
  // alle weg während einer langen Wartezeit → nicht weiter warten
  if (server.players.size() === 0 && vdRv.countdown > 1) vdRv.countdown = 1
  vdRv.countdown--
  let c = vdRv.countdown
  if (c >= 120 && (c % 600 === 0 || c === 300 || c === 120)) server.tell(vdRvPrefix().append(Text.yellow(`Neustart in ${c / 60} Minuten (Update ${vdRv.version}).`)))
  if (c === 60) server.tell(vdRvPrefix().append(Text.yellow('Neustart in 1 Minute. ')).append(vdRvClientHint()))
  if (c === 30 || c === 10 || (c <= 5 && c > 0)) server.tell(vdRvPrefix().append(Text.yellow(`Neustart in ${c} Sekunde${c === 1 ? '' : 'n'}.`)))
  if (c <= 0) {
    server.tell(vdRvPrefix().append(Text.red(`Neustart jetzt – bis gleich (ca. ${vdRv.eta} Min.)! `)).append(vdRvClientHint()))
    vdRvResult('go')
    vdRv = null
  }
})
