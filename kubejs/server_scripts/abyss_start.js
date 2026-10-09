// priority: 0
// Abyss-Start-Challenge: Spieler auf dieser Liste landen beim allerersten Join an einer zufälligen Stelle in The Abyss,
// ihr Spawnpunkt wird dorthin gesetzt. Der Tag "vd_abyss_start" merkt sich das, danach passiert beim Einloggen nichts mehr.
// Kein spreadplayers: das erzeugt Hunderte Chunks auf einmal und friert den Server minutenlang ein.
// Stattdessen wird je Versuch genau ein Chunk geladen und die Oberfläche über die Höhenkarte bestimmt.
const ABYSS_START = ['bylapus2']
const ABYSS_RANGE = 5000  // Zufallsbereich in Blöcken um 0/0
const $Heightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $BlockPos = Java.loadClass('net.minecraft.core.BlockPos')

function abyssSpot(level) {
  for (let i = 0; i < 8; i++) {
    const x = Math.floor(Math.random() * 2 * ABYSS_RANGE) - ABYSS_RANGE
    const z = Math.floor(Math.random() * 2 * ABYSS_RANGE) - ABYSS_RANGE
    const y = level.getHeight($Heightmap.MOTION_BLOCKING_NO_LEAVES, x, z)  // lädt genau diesen einen Chunk
    if (y <= level.getMinBuildHeight() + 1 || y >= 250) continue
    const ground = level.getBlockState(new $BlockPos(x, y - 1, z))
    if (!ground.getFluidState().isEmpty()) continue  // kein Lava- oder Wasserspawn
    return {x: x, y: y, z: z}
  }
  return null
}

PlayerEvents.loggedIn(event => {
  const p = event.player
  const name = String(p.username)
  if (!ABYSS_START.includes(name.toLowerCase()) || p.getTags().contains('vd_abyss_start')) return
  const server = event.server
  server.scheduleInTicks(40, () => {
    const level = server.getLevel('theabyss:the_abyss')
    const s = level ? abyssSpot(level) : null
    if (!s) {
      console.warn(`Abyss-Start: keine sichere Stelle für ${name} gefunden, nächster Versuch beim nächsten Join`)
      return
    }
    server.runCommandSilent(`execute in theabyss:the_abyss run tp ${name} ${s.x + 0.5} ${s.y} ${s.z + 0.5}`)
    server.scheduleInTicks(20, () => {
      if (String(p.level.dimension) !== 'theabyss:the_abyss') {
        console.warn(`Abyss-Start: ${name} ist nicht in der Abyss gelandet, nächster Versuch beim nächsten Join`)
        return
      }
      server.runCommandSilent(`execute in theabyss:the_abyss run spawnpoint ${name} ${s.x} ${s.y} ${s.z}`)
      p.addTag('vd_abyss_start')
      console.info(`Abyss-Start: ${name} bei ${s.x} ${s.y} ${s.z} in der Abyss gelandet`)
    })
  })
})
