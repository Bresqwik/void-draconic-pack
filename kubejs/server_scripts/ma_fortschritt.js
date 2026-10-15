// priority: 0
// VORÜBERGEHEND (bis „MA abgekapselt“ live ist): /mafortschritt [Spieler] zeigt NUR dem Aufrufer den Stand im Questkapitel
// Mystical Agriculture – ohne Namen den von byLapus2. Gleiche Nummern/Reihenfolge wie die Dashboard-Karte
// (Abhängigkeiten zuerst, sonst Position im Questbuch). Offene Quests mit Aufgaben-Fortschritt und kurzer Beschreibung.
// Rhino: in Funktionen let statt const.
const VdMafQuests = Java.loadClass('dev.ftb.mods.ftbquests.quest.ServerQuestFile')
const VdMafTeams = Java.loadClass('dev.ftb.mods.ftbteams.api.FTBTeamsAPI')
const VdMafUUID = Java.loadClass('java.util.UUID')
const VD_MAF_CHAPTER = 'mystical_agriculture'
const VD_MAF_DEFAULT = 'byLapus2'
const VD_MAF_DEFAULT_TEAM = '83fa4a35-d482-4e79-ba6b-5345847bf837'

function vdMafPlain(s) { return String(s || '').replace(/[&§][0-9a-fk-or]/gi, '').trim() }

function vdMafShort(q) {
  let lines = []
  try {
    q.getRawDescription().forEach(l => {
      l = String(l)
      if (l && l.trim().indexOf('&5&o') !== 0 && l.indexOf('{') !== 0) lines.push(vdMafPlain(l))
    })
  } catch (x) { }
  let t = lines.filter(l => l).join(' ')
  if (t.length > 170) {
    let cut = t.slice(0, 170), dot = cut.lastIndexOf('. ')
    t = dot > 80 ? cut.slice(0, dot + 1) : cut.slice(0, cut.lastIndexOf(' ')) + ' …'
  }
  return t
}

// Reihenfolge wie im Dashboard (Abhängigkeiten zuerst, dann Position). Fest hinterlegt, weil streamDependencies() aus
// KubeJS heraus keine Abhängigkeiten liefert; neue/unbekannte Quests hängen nach Position (y, x) hinten an.
const VD_MAF_ORDER = ['3AED65E8A5FD6A93', '6BDAA41A61791CA9', '3B3588BE6DDBF853', '6DFB55FD5F6EBCF7', '54BE7A3C33B1AD1D',
  '75A0305DC6016DB5', '5109A451DC4A3AEA', '60AFF87E72420500', '4C661C535196D3B3', '74FBD7FA43D3CD02', '2A9ABC50AF36E7D5',
  '120D6AF202550FBD', '3FB68B1B3B423309', '3245C504FF67CD6B', '66AB1A58130DA455', '6AAE21D265504A07', '216867CAFD894499',
  '0F1A02BD49D512A5', '648637316C587EAC', '048B1D033E315B3D', '105582A7857EC202', '289F0B32F0198242', '15B657263A42B625',
  '0EE2A46669434042', '50C6C2F10F96A129', '361AB8AAD2568FCB', '49345A7D940BE97A', '07995D94255A0E26', '2106C75CB1BFB8C0',
  '3B9ACD6E483AF25A', '081F34402B536745', '10500AE442C31D5F', '58DDFCD0BA14103B', '309191C6B74D327A', '00E08C85F4D315F5',
  '3238EC99007DC329', '1A3C0187E2F0E8BF']

function vdMafOrder(chapter) {
  let qs = []
  chapter.getQuests().forEach(q => qs.push(q))
  let rank = q => {
    let k = VD_MAF_ORDER.indexOf(String(q.getCodeString()).toUpperCase())
    return k < 0 ? 1000 : k
  }
  qs.sort((a, b) => (rank(a) - rank(b)) || (Number(a.getY()) - Number(b.getY())) || (Number(a.getX()) - Number(b.getX())))
  return qs
}

function vdMafTeam(server, name) {
  let mgr = VdMafTeams.api().getManager()
  if (!name) return { label: VD_MAF_DEFAULT, team: VdMafUUID.fromString(VD_MAF_DEFAULT_TEAM) }
  let uuid = null, label = name
  let p = server.getPlayerList().getPlayerByName(name)
  if (p) { uuid = p.getGameProfile().getId(); label = String(p.getGameProfile().getName()) }
  else {
    // Offline: das Spieler-Team (FTB Teams) trägt den Spielernamen; ProfileCache.get ist aus KubeJS nicht erreichbar
    let want = String(name).toLowerCase()
    mgr.getTeams().forEach(t => {
      if (uuid || !t.isPlayerTeam()) return
      let n = String(t.getName().getString())
      if (n.toLowerCase() === want) { uuid = t.getId(); label = n }   // Spielerteam: Team-ID = Spieler-UUID (getOwner() ist dort leer)
    })
  }
  if (!uuid) return null
  let team = mgr.getTeamForPlayerID(uuid).orElse(null)
  return team ? { label: label, team: team.getId() } : null
}

function vdMafShow(ctx, name) {
  let src = ctx.source, server = src.server
  let say = t => src.sendSystemMessage(t)
  let qf = VdMafQuests.INSTANCE
  let chapter = null
  qf.getAllChapters().forEach(c => { if (String(c.getFilename()) === VD_MAF_CHAPTER) chapter = c })
  let who = vdMafTeam(server, name)
  if (!chapter || !who) { say(Text.of('[MA] ').darkGreen().append(Text.gray(who ? 'Kapitel nicht gefunden.' : `Spieler „${name}“ unbekannt oder ohne Team.`))); return 0 }
  let data = qf.getNullableTeamData(who.team)
  if (!data) { say(Text.of('[MA] ').darkGreen().append(Text.gray(`Für ${who.label} gibt es noch keinen Quest-Stand.`))); return 0 }
  let order = vdMafOrder(chapter)
  let total = order.length, done = 0
  order.forEach(q => { if (data.isCompleted(q)) done++ })
  let pct = total ? Math.round(done / total * 100) : 0
  let filled = Math.round(pct / 5)
  let line = Text.of('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━').darkGreen()
  say(line)
  say(Text.of(' Mystical Agriculture – ').green().append(Text.of(who.label).gold().bold()).append(Text.gray('  (nur für dich sichtbar)')))
  say(Text.of(' ').append(Text.of('█'.repeat(filled)).green()).append(Text.of('█'.repeat(20 - filled)).darkGray())
    .append(Text.of(`  ${done}/${total}`).white().bold()).append(Text.gray(` · ${pct} %`)))
  if (done >= total) {
    say(Text.of(' Alle Quests geschafft – Mystischer Meister! ✦').gold())
  } else {
    say(Text.of(' Noch offen:').yellow())
    order.forEach((q, i) => {
      if (data.isCompleted(q)) return
      say(Text.of(` ${i + 1}. `).gray().append(Text.of(vdMafPlain(q.getRawTitle())).gold().bold()).append(Text.gray(q.isOptional() ? ' (optional)' : '')))
      q.getTasksAsList().forEach(t => {
        let need = Number(t.getMaxProgress()), have = Math.min(Number(data.getProgress(t)), need)
        let label = null
        try { if (String(t.getClass().getSimpleName()) === 'ItemTask') label = t.getItemStack().getHoverName() } catch (x) { }
        if (!label) label = vdMafPlain(t.getRawTitle()) || 'Aufgabe'
        let ok = have >= need
        say(ok ? Text.of('    ✓ ').green().append(Text.of(label).green()).append(Text.of(` ${have}/${need}`).green())
               : Text.of('    • ').gray().append(Text.of(label).white()).append(Text.of(` ${have}/${need}`).yellow()))
      })
      let s = vdMafShort(q)
      if (s) say(Text.of('    ' + s).darkGray().italic())
    })
  }
  say(line)
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('mafortschritt')
    .executes(ctx => vdMafShow(ctx, null))
    .then(Commands.argument('spieler', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => vdMafShow(ctx, String(Arguments.GREEDY_STRING.getResult(ctx, 'spieler')).trim()))))
})
