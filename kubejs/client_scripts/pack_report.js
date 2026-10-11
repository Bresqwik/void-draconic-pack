// Antwort auf die Frage des Servers nach dem Pack-Stand (server_scripts/pack_report.js): Hash der pack.toml aus
// packwiz.json (schreibt der Packwiz-Installer bei jedem Spielstart in den Spielordner).
NetworkEvents.dataReceived('vd_pack_q', e => {
  let hash = ''
  try {
    let j = JsonIO.read('packwiz.json')
    hash = String(j.get('packFileHash').get('value'))
  } catch (x) {
    console.warn('[Pack-Stand] packwiz.json nicht lesbar: ' + x)
  }
  try { Client.player.sendData('vd_pack', { hash: hash }) } catch (x) { console.warn('[Pack-Stand] senden: ' + x) }
})
