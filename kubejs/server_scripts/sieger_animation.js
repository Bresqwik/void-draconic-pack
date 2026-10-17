// priority: 5
// Sieger-Animation (Easy NPC): Um den Gefeierten erscheinen die Top 3 (stman476, prexynation, byLapus2) als Figuren mit
// echtem Skin, schauen ihn an und ducken sich 20 s lang im Takt (Easy-NPC-Pose humanoid/crouching) – danach Feuerwerk und sie verschwinden.
// Läuft bei der MA-Meisterung (ma_meister.js) und per /siegertest [Spieler] (nur OP, zum Testen oder Nachholen).
// Rhino: in Funktionen let statt const; Schleifen mit Index (forEach-Index auf const-Arrays war undefined → NaN).
const VD_SIEGER_FIGUREN = [
  { name: 'stman476', uuid: 'bd84bd46-3360-43cc-9f4c-ff42e8f6356a' },
  { name: 'prexynation', uuid: 'c209b11e-56fa-4fb8-9051-1853443281cb' },
  { name: 'byLapus2', uuid: '0e3d4c7e-b0cd-4aa6-9100-19aabb3e4ecc' }
]
const VD_SIEGER_DAUER = 400   // Ticks (20 s)
const VD_SIEGER_PI = 3.141592653589793   // Math.PI ist in KubeJS-Rhino undefined
const VdSiegerPose = Java.loadClass('net.minecraft.world.entity.Pose')
const VdSiegerUUID = Java.loadClass('java.util.UUID')
let VdSiegerModelPose = null, VdSiegerPoseAPI = null
try { VdSiegerModelPose = Java.loadClass('de.markusbordihn.easynpc.data.model.ModelPose') } catch (x) { }
try { VdSiegerPoseAPI = Java.loadClass('de.markusbordihn.easynpc.api.pose.ModelPoseAPI') } catch (x) { }
let VdSiegerPoseManager = null
try { VdSiegerPoseManager = Java.loadClass('de.markusbordihn.easynpc.client.pose.PoseManager') } catch (x) { }
// Pose-Schlüssel (echte ResourceLocations) für humanoid/crouching und humanoid/standing aus Easy NPCs Pose-Liste holen.
// Rhino kann setModelPose(npc, RL|Animation) nicht auseinanderhalten und java.lang.Class (Reflection) ist im KubeJS-Filter
// gesperrt. Daher: setModelPoseFromCache (nur eine Signatur) – der Cache entsteht aber erst durch setModelPose(npc, RL),
// das einmal über die explizite Rhino-Signatur bzw. mit dem echten RL-Objekt aufgerufen wird.
let vdSiegerPosen = null
function vdSiegerPosenLaden() {
  if (vdSiegerPosen) return vdSiegerPosen
  vdSiegerPosen = { duck: null, steh: null, keys: [] }
  try {
    let it = VdSiegerPoseManager.getPoseDataKeys().iterator()
    while (it.hasNext()) {
      let k = it.next(), t = String(k)
      vdSiegerPosen.keys.push(t)
      if (t.indexOf('humanoid') >= 0 && t.indexOf('humanoidslim') < 0) {
        if (/crouching$/.test(t)) vdSiegerPosen.duck = k
        if (/standing$/.test(t)) vdSiegerPosen.steh = k
      }
    }
  } catch (x) { console.warn('[Sieger] Pose-Liste: ' + x) }
  console.info(`[Sieger] Posen: duck=${vdSiegerPosen.duck ? 'ok' : 'fehlt'} steh=${vdSiegerPosen.steh ? 'ok' : 'fehlt'} (${vdSiegerPosen.keys.filter(t => t.indexOf('humanoid') >= 0).slice(0, 12).join(', ')})`)
  return vdSiegerPosen
}
const VD_SIEGER_SIG = 'setModelPose(de.markusbordihn.easynpc.entity.easynpc.EasyNPC,net.minecraft.resources.ResourceLocation)'
let vdSiegerWeg = {}   // welcher Aufrufweg schon gemeldet wurde
function vdSiegerPoseSetzen(e, rl) {
  let wege = [
    ['FromCache', () => VdSiegerPoseManager.setModelPoseFromCache(e, rl)],
    ['Signatur', () => VdSiegerPoseManager[VD_SIEGER_SIG](e, rl)],
    ['RL-Objekt', () => VdSiegerPoseManager.setModelPose(e, rl)]
  ]
  for (let i = 0; i < wege.length; i++) {
    try {
      if (wege[i][1]()) {
        if (!vdSiegerWeg[wege[i][0]]) { vdSiegerWeg[wege[i][0]] = 1; console.info('[Sieger] Pose gesetzt über ' + wege[i][0]) }
        return true
      }
    } catch (x) {
      if (!vdSiegerWeg['f' + i]) { vdSiegerWeg['f' + i] = 1; console.warn(`[Sieger] ${wege[i][0]}: ${x}`) }
    }
  }
  return false
}
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

let vdSiegerLog = 0
// Pose direkt am Entity setzen (Easy NPC: ModelPose VANILLA + DefaultPose → setPose, wird zum Client synchronisiert)
function vdSiegerSetPose(level, id, crouch) {
  // crouch: true = ducken, false = stehen
  try {
    let e = level.getEntity(VdSiegerUUID.fromString(id))
    if (!e) return
    let pose = crouch ? VdSiegerPose.CROUCHING : VdSiegerPose.STANDING   // nur für den Rückfall
    // Easy NPC zeichnet die Vanilla-Duckpose bei Menschenfiguren nicht – daher seine eigene Pose „humanoid/crouching“
    // (Daten aus data/easy_npc/poses, wird wie im Editor an alle Clients synchronisiert); Stehen = „standing“
    let ok = false
    try {
      let ps = vdSiegerPosenLaden(), rl = crouch ? ps.duck : ps.steh
      if (rl) ok = vdSiegerPoseSetzen(e, rl)
    } catch (x) { if (vdSiegerLog < 4) { vdSiegerLog++; console.warn('[Sieger] setModelPose: ' + x) } }
    if (!ok) {
      try { if (VdSiegerModelPose) e.setModelPose(VdSiegerModelPose.VANILLA) } catch (x) { }
      try { e.setDefaultPose(pose) } catch (x) { e.setPose(pose) }
    }
    if (vdSiegerLog < 2) { vdSiegerLog++; console.info(`[Sieger] Pose ${crouch ? 'crouching' : 'standing'} über ${ok ? 'Easy-NPC-Pose' : 'Fallback'}`) }
  } catch (x) { if (vdSiegerLog < 4) { vdSiegerLog++; console.warn('[Sieger] Pose-Fehler: ' + x) } }
}

function vdSiegerPlay(server, name) {
  let player = server.getPlayerList().getPlayerByName(name)
  if (!player) return
  let level = player.level
  let figs = []
  let anzahl = 3
  for (let i = 0; i < anzahl; i++) {
    let f = VD_SIEGER_FIGUREN[i]
    let a = (VD_SIEGER_PI * 2 / anzahl) * i
    let dx = (Math.cos(a) * 2.5).toFixed(2), dz = (Math.sin(a) * 2.5).toFixed(2)
    let id = vdSiegerRandomUuid()
    server.runCommandSilent(`execute at ${name} run summon easy_npc:humanoid ~${dx} ~ ~${dz} ` +
      `{UUID:${vdSiegerIntArray(id)},Invulnerable:1b,NoGravity:1b,Tags:["vd_sieger"],CustomName:'{"text":"${f.name}","color":"gold"}',` +
      `ModelData:{Pose:"VANILLA",DefaultPose:"STANDING"},` +
      `SkinData:{Name:"${f.name}",Type:"PLAYER_SKIN",UUID:${vdSiegerIntArray(f.uuid)}}}`)
    figs.push(id)
  }
  // alle zum Gefeierten drehen, Schwerkraft aus (Easy NPC ignoriert NoGravity aus dem summon-NBT) und Ausgangshöhe merken
  let base = {}
  server.scheduleInTicks(2, () => {
    server.runCommandSilent(`execute as @e[tag=vd_sieger] at @s run tp @s ~ ~ ~ facing entity ${name}`)
    for (let j = 0; j < figs.length; j++) {
      try {
        let e = level.getEntity(VdSiegerUUID.fromString(figs[j]))
        if (e) { e.setNoGravity(true); base[figs[j]] = [Number(e.getX()), Number(e.getY()), Number(e.getZ())] }
      } catch (x) { }
    }
  })
  let n = Math.floor(VD_SIEGER_DAUER / VD_SIEGER_TAKT)
  for (let k = 0; k < n; k++) {
    let crouch = k % 2 === 0
    server.scheduleInTicks(4 + k * VD_SIEGER_TAKT, () => {
      for (let j = 0; j < figs.length; j++) {
        vdSiegerSetPose(level, figs[j], crouch)
      }
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
