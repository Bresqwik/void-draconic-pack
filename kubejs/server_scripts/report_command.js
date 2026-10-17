// priority: 0
// /meldung <text>: Spieler melden Fehler, Bugs oder Auffälligkeiten („Rezept X geht nicht“, „Quest Y hängt“ …).
// Gespeichert in meldungen/<zeit>-<name>.json (Zeit, Spieler, Ort, Text); der Dashboard-Sammler zeigt sie im Fenster
// „Meldungen“ neben den Lag-Meldungen (mit Archivieren/Löschen). Rhino: in Funktionen let statt const.
const vdReportLast = {}  // Spieler -> letzte Meldung (Schutz vor Spam)

function vdReport(ctx, text) {
  let p = ctx.source.getPlayerOrException()
  let name = String(p.getGameProfile().getName())
  let now = Date.now()
  text = String(text || '').trim().slice(0, 500)
  if (!text) {
    p.tell(Text.of('[Meldung] ').aqua().append(Text.gray('Bitte mit Text: /meldung <was ist passiert?>')))
    return 0
  }
  if (vdReportLast[name] && now - vdReportLast[name] < 30000) {
    p.tell(Text.of('[Meldung] ').aqua().append(Text.gray('Bitte höchstens alle 30 Sekunden melden.')))
    return 0
  }
  vdReportLast[name] = now
  let report = {
    time: now, player: name, text: text,
    dim: String(p.level.dimension), pos: [Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)],
    held: ''
  }
  try { report.held = String(p.mainHandItem.id) } catch (x) { }
  console.info(`[Meldung] ${name} @ ${report.dim} ${report.pos.join(' ')}: ${text}`)
  // Ordner meldungen/ liefert das Pack mit (LIESMICH.txt); fehlt er trotzdem, steht die Meldung oben im Log
  try { JsonIO.write(`meldungen/${now}-${name}.json`, report) } catch (x) { console.warn('[Meldung] Datei nicht gespeichert: ' + x) }
  p.tell(Text.of('[Meldung] ').aqua().append(Text.gray('Danke! Deine Meldung ist gespeichert – wir schauen sie uns an.')))
  ctx.source.server.getPlayerList().getPlayers().forEach(o => {
    try {
      if (o !== p && vdAdminInfo(ctx.source.server, o)) o.tell(Text.of('[Meldung] ').aqua().append(Text.gray(`${name}: ${text}`)))
    } catch (x) { }
  })
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('meldung')
    .executes(ctx => vdReport(ctx, ''))
    .then(Commands.argument('text', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => vdReport(ctx, Arguments.GREEDY_STRING.getResult(ctx, 'text')))))
})
