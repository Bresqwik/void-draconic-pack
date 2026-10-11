// priority: 0
// Void-Kisten für jedes abgeschlossene Questkapitel: jedes Teammitglied bekommt 2 Kisten,
// bei deutlich schwereren Kapiteln (Endgame, Herausforderungen, späte Ären, Boss-Dimensionen, lange Mod-Kapitel) 5.
// Wer gerade offline ist, bekommt sie beim nächsten Einloggen. Jedes Kapitel zählt pro Team nur einmal
// (auch wenn der Fortschritt zurückgesetzt und neu erspielt wird). Gespeichert in server.persistentData.
// Braucht FTB XMod Compat (FTBQuestsEvents). Rhino: in Funktionen let statt const.
const VdCrateTeams = Java.loadClass('dev.ftb.mods.ftbteams.api.FTBTeamsAPI')
const VD_CRATE_DONE = 'vd_chapter_crates'      // Liste "teamId|kapitelId"
const VD_CRATE_PENDING = 'vd_crates_pending'   // {uuid: anzahl} für Offline-Mitglieder
const VD_CRATES_NORMAL = 2
const VD_CRATES_HARD = 5
// Dateinamen der schweren Kapitel (config/ftbquests/quests/chapters/<name>.snbt)
const VD_HARD_CHAPTERS = [
  'era_4', 'era_5', 'era_6', 'era_7',                                   // Hauptpfad ab Industrie
  'draconic', 'jenseits', 'void_kern', 'void_miner',                    // Endgame
  'bosse', 'geheimnisse', 'kopfgeld',                                   // Herausforderungen
  'cataclysm', 'wither_storm', 'the_abyss', 'twilight_forest', 'deeper_darker',
  'blood_magic', 'botania_addons', 'mekanism_ausbau', 'mystical_agriculture'
]

function vdCrateItem(n) {
  return Item.of('casesmod:case_item', n, '{CaseID:1,CustomModelData:1}')
}

function vdCrateGive(p, n, why) {
  p.give(vdCrateItem(n))
  p.tell(Text.of('[Void-Kiste] ').darkPurple().append(Text.gray(`${why} – ${n} Void-Kiste${n > 1 ? 'n' : ''} für dich! Rechtsklick zum Öffnen.`)))
  try { p.playNotifySound('minecraft:entity.player.levelup', 'players', 0.6, 1.2) } catch (x) { }
}

FTBQuestsEvents.completed(event => {
  let obj = event.object
  if (String(obj.getClass().getSimpleName()) !== 'Chapter') return
  let server = event.server
  let teamId = String(event.event.getData().getTeamId())
  let key = teamId + '|' + String(obj.codeString || obj.getCodeString())
  let pd = server.persistentData
  let done = pd.getList(VD_CRATE_DONE, 8)
  for (let i = 0; i < done.size(); i++) if (String(done.getString(i)) === key) return
  done.add(NBT.stringTag(key))
  pd.put(VD_CRATE_DONE, done)

  let title = String(obj.getTitle().getString())
  let file = ''
  try { file = String(obj.getFilename()) } catch (x) { }
  let n = VD_HARD_CHAPTERS.indexOf(file) >= 0 ? VD_CRATES_HARD : VD_CRATES_NORMAL
  let why = `Kapitel „${title}“ abgeschlossen`
  let online = {}
  event.onlineMembers.forEach(p => { online[String(p.uuid)] = true; vdCrateGive(p, n, why) })
  // Offline-Mitglieder vormerken
  try {
    let team = VdCrateTeams.api().getManager().getTeamByID(event.event.getData().getTeamId()).orElse(null)
    if (team) {
      let pending = pd.getCompound(VD_CRATE_PENDING)
      team.getMembers().forEach(u => {
        let id = String(u)
        if (!online[id]) pending.putInt(id, pending.getInt(id) + n)
      })
      pd.put(VD_CRATE_PENDING, pending)
    }
  } catch (x) { console.warn('[Kapitel-Kisten] Team nicht gefunden: ' + x) }
})

PlayerEvents.loggedIn(e => {
  let p = e.player
  let pd = e.server.persistentData
  let pending = pd.getCompound(VD_CRATE_PENDING)
  let id = String(p.uuid)
  let n = pending.getInt(id)
  if (n <= 0) return
  pending.remove(id)
  pd.put(VD_CRATE_PENDING, pending)
  e.server.scheduleInTicks(240, () => vdCrateGive(p, n, 'Während du weg warst, hat dein Team Kapitel abgeschlossen'))
})
