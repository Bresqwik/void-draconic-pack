// priority: 0
// Prüfwerkzeug (Admin): Beim ersten Login eines Spielers OHNE Op-Rechte (nach jedem Server-Start) schreibt der Server,
// welche Befehle dieser Spieler nutzen kann, nach vd-cmds-spieler.json (Befehl -> erlaubte Unterbefehle, 2 Ebenen).
// Nur Lesen, ändert nichts. Für die Befehls-Prüfung vom 16.10.2026; kann danach wieder raus.
let vdCmdsDone = false
PlayerEvents.loggedIn(e => {
  if (vdCmdsDone) return
  let p = e.player, s = e.server
  s.scheduleInTicks(200, () => {
    try {
      if (vdCmdsDone || p.hasPermissions(2)) return
      vdCmdsDone = true
      let src = p.createCommandSourceStack(), out = {}
      s.getCommands().getDispatcher().getRoot().getChildren().forEach(n => {
        if (!n.canUse(src)) return
        let subs = []
        n.getChildren().forEach(c => { if (!c.canUse(src)) return; let deep = []; c.getChildren().forEach(d => { if (d.canUse(src)) deep.push(String(d.getName())) }); subs.push(String(c.getName()) + (deep.length ? '(' + deep.join('|') + ')' : '')) })
        out[String(n.getName())] = subs
      })
      JsonIO.write('vd-cmds-spieler.json', { player: String(p.username), time: Date.now(), commands: out })
      console.info('[Befehls-Prüfung] ' + Object.keys(out).length + ' Befehle für Nicht-Admins -> vd-cmds-spieler.json')
    } catch (x) { console.warn('[Befehls-Prüfung] ' + x) }
  })
})
