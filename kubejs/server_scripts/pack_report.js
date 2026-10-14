// Pack-Stand der Spieler fürs Dashboard (Fenster „Updates“): 5 s nach dem Einloggen fragt der Server den Client,
// der antwortet mit dem Hash seiner pack.toml (client_scripts/pack_report.js). Ergebnis: vd-clients/<Name>.json,
// das liest der Dashboard-Sammler und vergleicht mit GitHub main und dem Server-Stand.
PlayerEvents.loggedIn(e => {
  let p = e.player
  e.server.scheduleInTicks(100, () => {
    try { p.sendData('vd_pack_q', {}) } catch (x) { }
  })
})

NetworkEvents.dataReceived('vd_pack', e => {
  let name = String(e.player.getGameProfile().getName())
  let hash = String(e.data.getString('hash'))
  if (!/^[A-Za-z0-9_]{1,16}$/.test(name)) return
  if (!/^[0-9a-f]{64}$/.test(hash)) hash = ''
  // Nur auf dem Server: im Einzelspieler fehlt der Ordner vd-clients (NoSuchFileException)
  try {
    if (!e.server.isDedicatedServer()) return
    JsonIO.write(`vd-clients/${name}.json`, { name: name, hash: hash, time: Date.now() })
  } catch (x) { console.warn('[Pack-Stand] ' + x) }
})
