// priority: 0
// Tägliche Void-Kisten: Jeder Spieler kann pro Kalendertag (Europe/Berlin) 2 Void-Kisten abholen.
// Hinweis beim Einloggen und um Mitternacht (für alle, die online sind) mit anklickbarem [Abholen].
// /kiste holt sie ab; ist das Inventar voll, fallen sie vor die Füße. Gespeichert in den Spielerdaten (persistentData).
// Rhino: in Funktionen let statt const.
const VdDailyLocalDate = Java.loadClass('java.time.LocalDate')
const VdDailyZone = Java.loadClass('java.time.ZoneId').of('Europe/Berlin')
const VdDailyZonedDateTime = Java.loadClass('java.time.ZonedDateTime')
const VD_DAILY_COUNT = 2
const VD_DAILY_KEY = 'vd_daily_crates'
let vdDailyLastDay = null

function vdDailyToday() {
  return String(VdDailyLocalDate.now(VdDailyZone).toString())
}

function vdDailyReady(p) {
  return String(p.persistentData.getString(VD_DAILY_KEY)) !== vdDailyToday()
}

// Zeit bis Mitternacht (Berlin) als "X Std. Y Min."
function vdDailyUntilMidnight() {
  let now = VdDailyZonedDateTime.now(VdDailyZone)
  let next = now.toLocalDate().plusDays(1).atStartOfDay(VdDailyZone)
  let min = Math.ceil((next.toEpochSecond() - now.toEpochSecond()) / 60)
  let h = Math.floor(min / 60)
  return (h > 0 ? h + ' Std. ' : '') + (min % 60) + ' Min.'
}

function vdDailyNotify(p) {
  p.tell(Text.of('[Void-Kiste] ').darkPurple()
    .append(Text.gray(`Deine ${VD_DAILY_COUNT} täglichen Void-Kisten sind bereit! `))
    .append(Text.of('[Abholen]').lightPurple().bold().clickRunCommand('/kiste').hover(Text.gray('Klicken oder /kiste eingeben'))))
}

function vdDailyClaim(p) {
  if (!vdDailyReady(p)) {
    p.tell(Text.of('[Void-Kiste] ').darkPurple().append(Text.gray(`Heute schon abgeholt. Neue Kisten in ${vdDailyUntilMidnight()}`)))
    return 0
  }
  p.persistentData.putString(VD_DAILY_KEY, vdDailyToday())
  p.give(Item.of('casesmod:case_item', VD_DAILY_COUNT, '{CaseID:1,CustomModelData:1}'))
  p.tell(Text.of('[Void-Kiste] ').darkPurple().append(Text.gray(`${VD_DAILY_COUNT} Void-Kisten erhalten – Rechtsklick zum Öffnen. Viel Glück!`)))
  try { p.playNotifySound('minecraft:entity.player.levelup', 'players', 0.6, 1.4) } catch (x) { }
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event
  event.register(Commands.literal('kiste').executes(ctx => vdDailyClaim(ctx.source.getPlayerOrException())))
})

PlayerEvents.loggedIn(e => {
  let p = e.player
  e.server.scheduleInTicks(200, () => {
    try { if (vdDailyReady(p)) vdDailyNotify(p) } catch (x) { }
  })
})

// Mitternacht: einmal pro Minute prüfen, ob ein neuer Tag begonnen hat
ServerEvents.tick(e => {
  if (e.server.tickCount % 1200 !== 0) return
  let today = vdDailyToday()
  if (vdDailyLastDay === null) { vdDailyLastDay = today; return }
  if (today === vdDailyLastDay) return
  vdDailyLastDay = today
  e.server.players.forEach(p => { try { if (vdDailyReady(p)) vdDailyNotify(p) } catch (x) { } })
})
