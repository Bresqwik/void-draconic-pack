// priority: 0
// /lag [text]: Jeder Spieler kann einen Lag-Moment markieren. Der Befehl schreibt eine gut auffindbare Zeile ins
// Server-Log (latest.log, Suchwort "LAG-MARKE") und legt einen Bericht in lag-reports/ ab. Der Dashboard-Sammler
// ergänzt Pregen-Stand und Systemlast und zeigt die Meldungen im Dashboard. So lässt sich vor und nach der Marke
// im Log nachsehen, woran es lag.
// Rhino: level.dimension und level.players sind Eigenschaften; in Funktionen let statt const.
const VdLagKey = Java.loadClass('net.minecraft.resources.ResourceKey')
const VdLagReg = Java.loadClass('net.minecraft.core.registries.Registries')
let VdLagLogger = null
try { VdLagLogger = Java.loadClass('org.apache.logging.log4j.LogManager').getLogger('VD-LAG') } catch (x) { }
const vdLagLast = {}  // Spieler -> Zeitpunkt der letzten Meldung (Schutz vor Spam)

function vdLagDim(server, level) {
  let id = level.dimension
  let ms = 0
  try {
    let times = server.getTickTime(VdLagKey.create(VdLagReg.DIMENSION, id))
    let sum = 0
    for (let i = 0; i < times.length; i++) sum += Number(times[i])
    ms = times.length ? sum / times.length / 1e6 : 0
  } catch (x) { }
  let chunks = 0, ents = 0
  try { chunks = level.getChunkSource().getLoadedChunksCount() } catch (x) { }
  try { ents = level.getEntities().size() } catch (x) { }
  return { id: String(id), ms: Math.round(ms * 10) / 10, players: level.players.size(), chunks: chunks, entities: ents }
}

function vdLag(ctx, text) {
  let p = ctx.source.getPlayerOrException()
  let server = p.server
  let name = String(p.getGameProfile().getName())
  let now = Date.now()
  if (vdLagLast[name] && now - vdLagLast[name] < 30000) {
    p.tell(Text.gray('[Lag] Bitte höchstens alle 30 Sekunden melden.'))
    return 0
  }
  vdLagLast[name] = now
  let dims = []
  server.getAllLevels().forEach(level => { try { dims.push(vdLagDim(server, level)) } catch (x) { } })
  dims.sort((a, b) => b.ms - a.ms)
  let online = []
  server.getPlayerList().getPlayers().forEach(o => {
    try { online.push({ name: String(o.getGameProfile().getName()), dim: String(o.level.dimension), pos: [Math.floor(o.x), Math.floor(o.y), Math.floor(o.z)] }) } catch (x) { }
  })
  let mspt = Math.round(server.getAverageTickTime() * 10) / 10
  let report = {
    time: now, player: name, text: String(text || '').slice(0, 200),
    dim: String(p.level.dimension), pos: [Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)],
    mspt: mspt, tps: Math.round(Math.min(20, 1000 / Math.max(50, mspt)) * 10) / 10,
    dims: dims.slice(0, 8), online: online
  }
  JsonIO.write(`lag-reports/${now}-${name}.json`, report)
  let top = dims.slice(0, 3).map(d => `${d.id} ${d.ms}ms/${d.chunks}ch/${d.entities}e`).join(', ')
  let line = `===== LAG-MARKE ${name} @ ${report.dim} ${report.pos.join(' ')} | MSPT ${mspt} | ${top}${report.text ? ' | "' + report.text + '"' : ''} =====`
  if (VdLagLogger) VdLagLogger.warn(line); else console.warn(line)
  p.tell(Text.of('[Lag] ').gold().append(Text.gray(`Danke! Marke gesetzt um ${new Date(now).toLocaleTimeString('de-DE')} (MSPT ${mspt}). Wir schauen ins Log.`)))
  // Admins (OP) bekommen einen Hinweis
  server.getPlayerList().getPlayers().forEach(o => {
    try {
      if (o !== p && server.getPlayerList().isOp(o.getGameProfile())) o.tell(Text.of('[Lag] ').gold().append(Text.gray(`${name} hat Lag gemeldet (${report.dim}, MSPT ${mspt}).`)))
    } catch (x) { }
  })
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('lag')
    .executes(ctx => vdLag(ctx, ''))
    .then(Commands.argument('text', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => vdLag(ctx, Arguments.GREEDY_STRING.getResult(ctx, 'text')))))
})
