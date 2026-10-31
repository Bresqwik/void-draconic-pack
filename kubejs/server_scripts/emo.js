// priority: 0
// /emo tötet den eigenen Charakter. Es passiert erst nach der Bestätigung: Klick im Chat oder /emo ja innerhalb von 30 Sekunden.
const VD_EMO_WAIT = 30000
const vdEmoPending = {}

ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event
  event.register(Commands.literal('emo')
    .executes(ctx => {
      const p = ctx.source.getPlayerOrException()
      vdEmoPending[String(p.getGameProfile().getId())] = Date.now() + VD_EMO_WAIT
      p.tell(Text.red('Willst du deinen Charakter wirklich töten? Deine Sachen bleiben im Grabstein.'))
      p.tell(Text.gold('[Ja, töten]').clickRunCommand('/emo ja').hover('Bestätigen (30 Sekunden gültig)'))
      return 1
    })
    .then(Commands.literal('ja').executes(ctx => {
      const p = ctx.source.getPlayerOrException()
      const id = String(p.getGameProfile().getId())
      const until = vdEmoPending[id]
      delete vdEmoPending[id]
      if (!until || Date.now() > until) {
        p.tell(Text.gray('Keine offene Bestätigung. Gib zuerst /emo ein.'))
        return 0
      }
      p.kill()
      return 1
    })))
})
