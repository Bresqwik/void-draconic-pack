// Tab-Liste: Daten für die erweiterte Ansicht (Shift+Tab, siehe client_scripts/tab_stats.js).
// Alle 2 Sekunden: Tickzeit des Servers und je Dimension (Forge-Messwerte wie bei "forge tps"), Spieler und geladene Chunks.
// Rhino-Eigenheiten: level.dimension und level.players sind Eigenschaften (keine Methoden); const in Callbacks vermeiden.
const VdResourceKey = Java.loadClass('net.minecraft.resources.ResourceKey')
const VdRegistries = Java.loadClass('net.minecraft.core.registries.Registries')
let vdTabTick = 0

function vdDimStats(server, level) {
  let id = level.dimension
  let times = server.getTickTime(VdResourceKey.create(VdRegistries.DIMENSION, id))
  let sum = 0
  for (let i = 0; i < times.length; i++) sum += Number(times[i])
  let ms = times.length ? sum / times.length / 1e6 : 0
  return { id: String(id), ms: Math.round(ms * 10) / 10, p: level.players.size(), c: level.getChunkSource().getLoadedChunksCount() }
}

ServerEvents.tick(e => {
  if (++vdTabTick % 40 !== 0) return
  let server = e.server
  if (server.getPlayerCount() === 0) return
  let dims = []
  server.getAllLevels().forEach(level => {
    try { dims.push(vdDimStats(server, level)) } catch (x) { }
  })
  let data = { mspt: Math.round(server.getAverageTickTime() * 10) / 10, dims: JSON.stringify(dims) }
  server.getPlayerList().getPlayers().forEach(p => {
    try { p.sendData('vd_tab', data) } catch (x) { }
  })
})
