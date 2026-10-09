// priority: 0
// /claude <text>: Fragen an Claude und Aufgabenliste direkt aus dem Spiel. Nur für die hier eingetragenen UUIDs
// (läuft über Stefans Claude-Abo). Der Befehl legt nur eine Anfrage-Datei ab; der Dienst mc-claude-bridge auf dem
// Server beantwortet sie und schreibt die Antwort per tellraw in den Chat.
//   /claude <frage>              Frage stellen
//   /claude status               Serverstatus
//   /claude aufgabe add <text>   Aufgabe anlegen
//   /claude aufgabe list         offene Aufgaben
//   /claude aufgabe done <nr>    Aufgabe abhaken
const CLAUDE_USERS = ['bd84bd46-3360-43cc-9f4c-ff42e8f6356a']  // stman476

// UUID der Befehlsquelle; getStringUUID gibt es unter KubeJS nicht. Fehler hier dürfen nie den Reload blockieren.
function claudeUuid(e) {
  try { return e ? String(e.getGameProfile ? e.getGameProfile().getId() : e.uuid) : '' } catch (x) { return '' }
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('claude')
    .requires(src => CLAUDE_USERS.includes(claudeUuid(src.getEntity())))
    .then(Commands.argument('text', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => {
        const p = ctx.source.getPlayerOrException()
        const text = String(Arguments.GREEDY_STRING.getResult(ctx, 'text')).slice(0, 600)
        const now = Date.now()
        JsonIO.write(`claude-bridge/inbox/${now}-${Math.floor(Math.random() * 1e6)}.json`, {
          player: String(p.getGameProfile().getName()), uuid: claudeUuid(p), text: text, time: now,
          dim: String(p.level.dimension), pos: [Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)]
        })
        p.tell(Text.of('[Claude] ').lightPurple().append(Text.gray('… denkt nach')))
        return 1
      })))
})
