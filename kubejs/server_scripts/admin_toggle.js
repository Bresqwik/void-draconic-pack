// priority: 0
// /admin schaltet OP für die hier eingetragenen Spieler an und aus: normal spielen ohne OP-Vorteile,
// bei Bedarf kurz Admin werden. Berechtigt ist nur, wer per UUID eingetragen ist (Namen lassen sich ändern).
const ADMIN_TOGGLE = ['bd84bd46-3360-43cc-9f4c-ff42e8f6356a']  // stman476

// UUID der Befehlsquelle; getStringUUID gibt es unter KubeJS nicht. Fehler hier dürfen nie den Reload blockieren.
function adminUuid(e) {
  try { return e ? String(e.getGameProfile ? e.getGameProfile().getId() : e.uuid) : '' } catch (x) { return '' }
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands } = event
  event.register(Commands.literal('admin')
    .requires(src => ADMIN_TOGGLE.includes(adminUuid(src.getEntity())))
    .executes(ctx => {
      const p = ctx.source.getPlayerOrException()
      const server = ctx.source.getServer()
      const profile = p.getGameProfile()
      const name = String(profile.getName())
      const wasOp = server.getPlayerList().isOp(profile)
      server.runCommandSilent(`${wasOp ? 'deop' : 'op'} ${name}`)
      p.tell(wasOp ? Text.gray('Admin-Modus aus: du spielst jetzt ohne OP.') : Text.gold('Admin-Modus an: OP aktiv. /admin schaltet wieder aus.'))
      console.info(`/admin: ${name} ${wasOp ? 'ohne' : 'mit'} OP`)
      return 1
    }))
})
