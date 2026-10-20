// priority: 0
// „Was ist neu“ beim Einloggen: Wer seit einem Update nicht online war, bekommt kurz die Änderungen der Versionen, die er
// verpasst hat (höchstens 3, neueste zuerst). Quelle: config/vd-changelog.json (player = alle, admin = nur Admins).
// Gesehen-Stand in den Spielerdaten (persistentData vd_changelog_seen). Wer den Schlüssel noch nicht hat (neu oder vor
// dieser Funktion zuletzt online), sieht nur die aktuelle Version. Rhino: in Funktionen let statt const.
const VD_CL_KEY = 'vd_changelog_seen'
const VD_CL_MAX = 3

function vdClLoad() {
  try {
    let d = JsonIO.read('config/vd-changelog.json')
    if (d && d.versions && d.versions.length) return d
  } catch (x) { console.warn('[Was ist neu] ' + x) }
  return null
}

function vdClIsAdmin(server, p) {
  try { return vdAdminInfo(server, p) } catch (x) { }
  try { return server.getPlayerList().isOp(p.getGameProfile()) } catch (x) { return false }
}

PlayerEvents.loggedIn(e => {
  let p = e.player
  let server = e.server
  server.scheduleInTicks(140, () => {
    try {
      let d = vdClLoad()
      if (!d) return
      let current = String(d.versions[0].version)
      let seen = String(p.persistentData.getString(VD_CL_KEY) || '')
      if (seen === current) return
      let admin = vdClIsAdmin(server, p)
      // verpasste Versionen bis zur zuletzt gesehenen (unbekannt → nur die aktuelle)
      let list = []
      for (let i = 0; i < d.versions.length; i++) {
        let v = d.versions[i]
        if (String(v.version) === seen) break
        list.push(v)
        if (!seen) break
      }
      let more = list.length > VD_CL_MAX
      list = list.slice(0, VD_CL_MAX)
      let lines = 0
      p.tell(Text.of('[Update] ').gold().append(Text.white('Was ist neu seit deinem letzten Besuch:')))
      for (let i = 0; i < list.length; i++) {
        let v = list[i]
        let items = []
        if (v.player) for (let j = 0; j < v.player.length; j++) items.push([String(v.player[j]), false])
        if (admin && v.admin) for (let j = 0; j < v.admin.length; j++) items.push([String(v.admin[j]), true])
        if (!items.length) continue
        p.tell(Text.of(`  ${v.version}`).yellow())
        for (let j = 0; j < items.length; j++) {
          p.tell(Text.of('   • ').gold().append(items[j][1] ? Text.of('[Admin] ').darkGray().append(Text.gray(items[j][0])) : Text.gray(items[j][0])))
          lines++
        }
      }
      if (d.releases) {
        p.tell(Text.of(more ? '  … und ältere Updates ' : '  ').gray()
          .append(Text.of('[Alle Änderungen]').aqua().clickOpenUrl(String(d.releases)).hover(Text.gray('Änderungslisten auf GitHub öffnen'))))
      }
      p.persistentData.putString(VD_CL_KEY, current)
      console.info(`[Was ist neu] ${p.username}: ${list.length} Version(en), ${lines} Zeilen (gesehen vorher: ${seen || '–'})`)
    } catch (x) { console.warn('[Was ist neu] ' + x) }
  })
})
