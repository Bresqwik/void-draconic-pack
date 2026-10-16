// priority: 0
// „Mystischer Meister“: Schafft ein Team ALLE Quests des Kapitels Mystical Agriculture (auch die optionalen), feiert der
// Server das einmalig für alle – Titel, Chat, Sound, Feuerwerk um die Team-Mitglieder, dazu 20 Void-Kisten pro Mitglied und der
// dauerhafte Titel „Mystischer Meister“ (FTB-Ranks-Rang mystischer_meister in ranks.snbt, auch für Offline-Mitglieder). Danach folgt (nach Abstimmung mit
// Stefan) das Update, das Mystical Agriculture von den anderen Mods abkapselt. Merker in server.persistentData,
// zusätzlich vd-ma-meister.json für Dashboard/Claude. Rhino: in Funktionen let statt const.
const VdMaTeams = Java.loadClass('dev.ftb.mods.ftbteams.api.FTBTeamsAPI')
const VD_MA_CHAPTER = 'mystical_agriculture'
const VD_MA_DONE = 'vd_ma_meister'   // Liste der Team-IDs, die schon gefeiert wurden
const VD_MA_CRATES = 20              // Void-Kisten pro Teammitglied für die Meisterung (Offline-Mitglieder beim nächsten Login)

function vdMaFirework(server, p, delay, color) {
  server.scheduleInTicks(delay, () => {
    try {
      let dx = (Math.random() * 6 - 3).toFixed(1), dz = (Math.random() * 6 - 3).toFixed(1)
      server.runCommandSilent(`execute at ${p.username} run summon minecraft:firework_rocket ~${dx} ~1 ~${dz} ` +
        `{LifeTime:30,FireworksItem:{id:"minecraft:firework_rocket",Count:1b,tag:{Fireworks:{Flight:2b,Explosions:[` +
        `{Type:1b,Flicker:1b,Trail:1b,Colors:[I;${color}],FadeColors:[I;16766720]}]}}}}`)
    } catch (x) { }
  })
}

function vdMaCelebrate(server, teamName, names) {
  let who = names.length ? names.join(', ') : teamName
  server.runCommandSilent(`title @a times 10 100 30`)
  server.runCommandSilent(`title @a title {"text":"✦ MYSTISCHER MEISTER ✦","color":"dark_purple","bold":true}`)
  server.runCommandSilent(`title @a subtitle {"text":"${who.replace(/"/g, '')} hat Mystical Agriculture gemeistert","color":"gold"}`)
  server.runCommandSilent(`execute as @a at @s run playsound minecraft:ui.toast.challenge_complete master @s ~ ~ ~ 1 1`)
  server.scheduleInTicks(40, () => server.runCommandSilent(`execute as @a at @s run playsound minecraft:entity.ender_dragon.growl master @s ~ ~ ~ 0.6 1.2`))
  let line = Text.of('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━').darkPurple()
  server.tell(line)
  server.tell(Text.of('  ✦ ').gold().append(Text.of('MYSTISCHER MEISTER').darkPurple().bold()).append(Text.of(' ✦').gold()))
  server.tell(Text.of('  ').append(Text.of(who).gold().bold())
    .append(Text.of(' hat alle Quests von ').gray()).append(Text.of('Mystical Agriculture').green())
    .append(Text.of(' abgeschlossen – vom ersten Inferium-Krümel bis zum Erweckten Draconium!').gray()))
  server.tell(Text.of('  Die Felder verneigen sich. Glückwunsch vom ganzen Server! ').gray().append(Text.of('GG').gold().bold()))
  server.tell(Text.of('  ').append(Text.of(who).gold()).append(Text.of(' trägt ab jetzt den Titel ').gray())
    .append(Text.of('Mystischer Meister').darkPurple().bold()).append(Text.of('.').gray()))
  server.tell(line)
}

FTBQuestsEvents.completed(event => {
  let obj = event.object
  if (String(obj.getClass().getSimpleName()) !== 'Quest') return
  let chapter = obj.getChapter()
  if (String(chapter.getFilename()) !== VD_MA_CHAPTER) return
  let data = event.event.getData()
  let all = true
  chapter.getQuests().forEach(q => { if (!data.isCompleted(q)) all = false })
  if (!all) return

  let server = event.server
  let teamId = String(data.getTeamId())
  let pd = server.persistentData
  let done = pd.getList(VD_MA_DONE, 8)
  for (let i = 0; i < done.size(); i++) if (String(done.getString(i)) === teamId) return
  done.add(NBT.stringTag(teamId))
  pd.put(VD_MA_DONE, done)

  let teamName = 'Ein Team'
  try {
    let team = VdMaTeams.api().getManager().getTeamByID(data.getTeamId()).orElse(null)
    if (team) teamName = String(team.getName().getString())
  } catch (x) { }
  let names = []
  let colors = [11743532, 14602026, 6719955, 15435844]
  event.onlineMembers.forEach(p => {
    names.push(String(p.username))
    for (let k = 0; k < 8; k++) vdMaFirework(server, p, 10 + k * 12, colors[k % colors.length])
  })
  vdMaCelebrate(server, teamName, names)
  // Dauerhafter Titel für alle Mitglieder (offline: Name über das eigene Spieler-Team von FTB Teams)
  try {
    let titled = {}
    names.forEach(n => { titled[n.toLowerCase()] = true; server.runCommandSilent(`ftbranks add ${n} mystischer_meister`) })
    let team = VdMaTeams.api().getManager().getTeamByID(data.getTeamId()).orElse(null)
    if (team) team.getMembers().forEach(u => {
      try {
        let pt = VdMaTeams.api().getManager().getTeamByID(u).orElse(null)   // Spielerteam: Team-ID = Spieler-UUID, Name = Spielername
        let n = pt ? String(pt.getName().getString()) : ''
        if (n && !titled[n.toLowerCase()]) { titled[n.toLowerCase()] = true; server.runCommandSilent(`ftbranks add ${n} mystischer_meister`) }
      } catch (x) { }
    })
  } catch (x) { console.warn('[Mystischer Meister] Titel: ' + x) }
  // 10 Void-Kisten für jedes Teammitglied – Funktion und Merker aus chapter_crates.js (Offline-Mitglieder bekommen sie beim Login)
  server.scheduleInTicks(140, () => {
    try {
      let online = {}
      names.forEach(n => { let p = server.getPlayerList().getPlayerByName(n); if (p) { online[String(p.uuid)] = true; vdCrateGive(p, VD_MA_CRATES, 'Mystischer Meister') } })
      let team = VdMaTeams.api().getManager().getTeamByID(data.getTeamId()).orElse(null)
      if (team) {
        let pending = pd.getCompound(VD_CRATE_PENDING)
        team.getMembers().forEach(u => { let id = String(u); if (!online[id]) pending.putInt(id, pending.getInt(id) + VD_MA_CRATES) })
        pd.put(VD_CRATE_PENDING, pending)
      }
    } catch (x) { console.warn('[Mystischer Meister] Kisten: ' + x) }
  })
  console.info(`[Mystischer Meister] ${teamName} (${names.join(', ')}) hat alle Mystical-Quests abgeschlossen`)
  try { JsonIO.write('vd-ma-meister.json', { team: teamName, teamId: teamId, players: names, time: Date.now() }) } catch (x) { }
})
