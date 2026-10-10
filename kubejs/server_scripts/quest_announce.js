// priority: 0
// Questbuch 2.0: Ära-Abschluss und Void-Kern als großes Ereignis – Titel-Einblendung beim Team, Server-Ansage, Klang.
// Braucht FTB XMod Compat (FTBQuestsEvents). Quest-IDs = Hash aus Kapitel + Key (siehe quests-plan/make_eras.py).
const VD_ERA_QUESTS = {
  'F4D4923D2C391971': ['I', 'Ankunft', 'Das Überleben'],
  'B2E36F294046B7AB': ['II', 'Grundlagen', 'Zahnrad & Blüte'],
  'A9203ACE14E6F567': ['III', 'Neue Welten', 'Die Pfade'],
  '61F606979A64D950': ['IV', 'Industrie', 'Die Schmiede'],
  'BECABDB3F887F88B': ['V', 'Tiefe Magie', 'Das Blut'],
  '8A8567A62B57D666': ['VI', 'Wyvern', 'Das Drachenherz']
}
const VD_CORE_QUEST = '3E2D9C988EA136A4'

function vdAnnounce(event, title, subtitle, chat, sound) {
  let server = event.server
  let player = event.player
  let who = player ? String(player.getGameProfile().getName()) : 'Ein Hüter'
  let members = []
  try { event.onlineMembers.forEach(p => members.push(p)) } catch (x) { if (player) members.push(player) }
  members.forEach(p => {
    try {
      server.runCommandSilent(`title ${p.getGameProfile().getName()} times 10 70 20`)
      server.runCommandSilent(`title ${p.getGameProfile().getName()} subtitle ${JSON.stringify({ text: subtitle, color: 'light_purple' })}`)
      server.runCommandSilent(`title ${p.getGameProfile().getName()} title ${JSON.stringify({ text: title, color: 'gold', bold: true })}`)
      server.runCommandSilent(`playsound ${sound} master ${p.getGameProfile().getName()} ~ ~ ~ 1 1`)
    } catch (x) { }
  })
  server.tell(Text.of('[Chronik] ').gold().append(Text.lightPurple(chat.replace('%s', who))))
}

FTBQuestsEvents.completed(event => {
  let id = String(event.object.codeString || event.object.getCodeString())
  if (VD_ERA_QUESTS[id]) {
    let e = VD_ERA_QUESTS[id]
    vdAnnounce(event, `Ära ${e[0]} abgeschlossen`, `${e[1]} – ${e[2]}`, `%s hat Ära ${e[0]} (${e[1]}) abgeschlossen. Die Chronik der Hüter wächst.`,
      'minecraft:ui.toast.challenge_complete')
  } else if (id == VD_CORE_QUEST) {
    vdAnnounce(event, 'Der Void-Kern', 'Drachen und Leere sind vereint', '%s hat den Void-Kern geschmiedet! Die letzten Hüter haben ihr Ziel erreicht.',
      'minecraft:entity.ender_dragon.death')
  }
})
