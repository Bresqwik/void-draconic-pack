// Tab-Liste: Tab = normale Liste (Better Tab), Shift+Tab = zusätzlich Server-TPS und die Dimensionen mit der meisten Last.
// Die Daten schickt der Server alle 2 Sekunden (server_scripts/tab_stats.js). In Funktionen let statt const (Rhino).
const VdScreen = Java.loadClass('net.minecraft.client.gui.screens.Screen')
const VdComponent = Java.loadClass('net.minecraft.network.chat.Component')

const VD_DIM_NAMES = {
  'minecraft:overworld': 'Oberwelt', 'minecraft:the_nether': 'Nether', 'minecraft:the_end': 'End',
  'aether:the_aether': 'Aether', 'twilightforest:twilight_forest': 'Twilight Forest', 'deeperdarker:otherside': 'Otherside',
  'blue_skies:everbright': 'Everbright', 'blue_skies:everdawn': 'Everdawn', 'the_bumblezone:the_bumblezone': 'Bumblezone',
  'mythicbotany:alfheim': 'Alfheim', 'bloodmagic:dungeon': 'Blood-Magic-Dungeon', 'irons_spellbooks:pocket_dimension': "Iron's Taschendimension",
  'witherstormmod:bowels': 'Wither-Storm-Inneres', 'theabyss:the_abyss': 'The Abyss', 'theabyss:frost_world': 'Abyss-Frostwelt',
  'theabyss:spectral_world': 'Abyss-Geisterwelt', 'theabyss:pocket_dimension': 'Abyss-Taschendimension'
}
const VD_ALWAYS = ['minecraft:overworld', 'minecraft:the_nether', 'minecraft:the_end']
const VD_MAX_ROWS = 8

let vdTabData = null
let vdTabShown = false
let vdTabLogged = {}
// Fehler je Stelle einmal ins KubeJS-Client-Log (logs/kubejs/client.log), damit Probleme sichtbar werden
function vdTabLog(where, x) {
  if (vdTabLogged[where]) return
  vdTabLogged[where] = true
  console.warn('[Tab-Stats] ' + where + ': ' + x)
}

NetworkEvents.dataReceived('vd_tab', e => {
  try {
    vdTabData = { mspt: Number(e.data.getDouble('mspt')), dims: JSON.parse(String(e.data.getString('dims'))), t: Date.now() }
    if (!vdTabLogged.first) { vdTabLogged.first = true; console.info('[Tab-Stats] erste Daten vom Server: ' + vdTabData.dims.length + ' Dimensionen') }
  } catch (x) {
    vdTabData = null
    vdTabLog('Daten', x)
  }
})

function vdMsColor(ms) {
  return ms < 25 ? '§a' : ms < 40 ? '§e' : ms < 50 ? '§6' : '§c'
}

function vdDimName(id) {
  if (VD_DIM_NAMES[id]) return VD_DIM_NAMES[id]
  let s = id.split(':').pop().replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function vdFooter() {
  let d = vdTabData
  let tps = Math.min(20, 1000 / Math.max(50, d.mspt))
  let lines = [`§6Server: ${vdMsColor(d.mspt)}${tps.toFixed(1)} TPS §7· ${vdMsColor(d.mspt)}${d.mspt.toFixed(1)} ms`, '§8────────────────────']
  // Oberwelt, Nether und End immer, dazu die Dimensionen mit der meisten Last oder mit Spielern
  let sorted = d.dims.slice().sort((a, b) => b.ms - a.ms)
  let show = sorted.filter(x => VD_ALWAYS.indexOf(x.id) >= 0 || x.p > 0 || x.ms >= 0.5)
  let rows = show.slice(0, VD_MAX_ROWS)
  rows.forEach(x => {
    let who = x.p > 0 ? `§b${x.p} Spieler` : '§80 Spieler'
    lines.push(`§f${vdDimName(x.id)}  ${vdMsColor(x.ms)}${x.ms.toFixed(1)} ms §7· ${who} §7· §8${x.c} Chunks`)
  })
  let rest = d.dims.length - rows.length
  if (rest > 0) lines.push(`§8+${rest} weitere Dimensionen (ruhig)`)
  if (Date.now() - d.t > 10000) lines.push('§8(Daten veraltet)')
  return VdComponent.literal(lines.join('\n'))
}

ClientEvents.tick(e => {
  try {
    let mc = Client
    if (!mc.player || !mc.gui) return
    let tab = mc.gui.getTabList()
    let want = vdTabData && mc.options.keyPlayerList.isDown() && VdScreen.hasShiftDown()
    if (want) {
      tab.setFooter(vdFooter())
      vdTabShown = true
    } else if (vdTabShown) {
      tab.setFooter(null)
      vdTabShown = false
    }
  } catch (x) { vdTabLog('Anzeige', x) }
})
