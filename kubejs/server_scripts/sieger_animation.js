// priority: 5
// Sieger-Animation (Easy NPC): Um den Gefeierten erscheinen die Top 3 (stman476, prexynation, byLapus2) als Figuren mit
// echtem Skin, schauen ihn an und ducken sich 20 s lang rhythmisch – danach Feuerwerk und sie verschwinden.
// Läuft bei der MA-Meisterung (ma_meister.js) und per /siegertest [Spieler] (nur OP, zum Testen oder Nachholen).
// Rhino: in Funktionen let statt const.
const VD_SIEGER_FIGUREN = [
  { name: 'stman476', uuid: 'bd84bd46-3360-43cc-9f4c-ff42e8f6356a' },
  { name: 'prexynation', uuid: 'c209b11e-56fa-4fb8-9051-1853443281cb' },
  { name: 'byLapus2', uuid: '0e3d4c7e-b0cd-4aa6-9100-19aabb3e4ecc' }
]
const VD_SIEGER_DAUER = 400   // Ticks (20 s)
const VD_SIEGER_TAKT = 6      // alle 6 Ticks Ducken/Aufstehen

// UUID-Text -> NBT-Int-Array [I;a,b,c,d]
function vdSiegerIntArray(u) {
  let h = String(u).replace(/-/g, '')
  let out = []
  for (let i = 0; i < 4; i++) {
    let v = parseInt(h.substr(i * 8, 8), 16)
    if (v > 0x7fffffff) v -= 0x100000000
    out.push(v)
  }
  return `[I;${out.join(',')}]`
}

function vdSiegerRandomUuid() {
  let h = ''
  for (let i = 0; i < 32; i++) h += Math.floor(Math.random() * 16).toString(16)
  return `${h.substr(0, 8)}-${h.substr(8, 4)}-4${h.substr(13, 3)}-a${h.substr(17, 3)}-${h.substr(20, 12)}`
}

function vdSiegerPlay(server, name) {
  let figs = []
  VD_SIEGER_FIGUREN.forEach((f, i) => {
    let a = (Math.PI * 2 / VD_SIEGER_FIGUREN.length) * i
    let dx = (Math.cos(a) * 2.5).toFixed(2), dz = (Math.sin(a) * 2.5).toFixed(2)
    let id = vdSiegerRandomUuid()
    server.runCommandSilent(`execute at ${name} run summon easy_npc:humanoid ~${dx} ~ ~${dz} ` +
      `{UUID:${vdSiegerIntArray(id)},Invulnerable:1b,Tags:["vd_sieger"],CustomName:'{"text":"${f.name}","color":"gold"}',` +
      `SkinData:{Name:"${f.name}",Type:"PLAYER_SKIN",UUID:${vdSiegerIntArray(f.uuid)}}}`)
    figs.push(id)
  })
  // alle zum Gefeierten drehen
  server.scheduleInTicks(2, () => server.runCommandSilent(`execute as @e[tag=vd_sieger] at @s run tp @s ~ ~ ~ facing entity ${name}`))
  let n = Math.floor(VD_SIEGER_DAUER / VD_SIEGER_TAKT)
  for (let k = 0; k < n; k++) {
    let pose = k % 2 === 0 ? 'minecraft:crouching' : 'minecraft:standing'
    server.scheduleInTicks(4 + k * VD_SIEGER_TAKT, () => {
      figs.forEach(id => server.runCommandSilent(`easy_npc pose set ${id} ${pose}`))
    })
  }
  server.scheduleInTicks(VD_SIEGER_DAUER + 10, () => {
    server.runCommandSilent(`execute as @e[tag=vd_sieger] at @s run summon minecraft:firework_rocket ~ ~1 ~ ` +
      `{LifeTime:20,FireworksItem:{id:"minecraft:firework_rocket",Count:1b,tag:{Fireworks:{Flight:1b,Explosions:[` +
      `{Type:0b,Flicker:1b,Colors:[I;11743532,16766720],FadeColors:[I;16777215]}]}}}}`)
    server.runCommandSilent('kill @e[tag=vd_sieger]')
  })
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('siegertest').requires(s => s.hasPermission(2))
    .executes(ctx => { vdSiegerPlay(ctx.source.server, String(ctx.source.getPlayerOrException().username)); return 1 })
    .then(Commands.argument('spieler', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => { vdSiegerPlay(ctx.source.server, String(Arguments.GREEDY_STRING.getResult(ctx, 'spieler')).trim()); return 1 })))
})

// Sicherheitsnetz: nach einem Neustart übrig gebliebene Figuren entfernen
ServerEvents.loaded(event => event.server.runCommandSilent('kill @e[tag=vd_sieger]'))
