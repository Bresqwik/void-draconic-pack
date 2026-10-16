// priority: 0
// „Sprungkönig“: Ziel für prexynation – 100.000 Sprünge (Statistik minecraft:jump), Meilenstein bei 50.000.
// 50.000: Känguru-Nachricht an alle + 5 Void-Kisten. 100.000: Leertasten-Nachricht an alle + 20 Void-Kisten + FTB-Ranks-Titel
// „Sprungkönig“ (Rang sprungkoenig in world/serverconfig/ftbranks/ranks.snbt). Jeweils einmalig (Merker in server.persistentData).
// Sprünge zählen nur, wenn er online ist – daher keine Offline-Nachlieferung nötig.
// Stand für Dashboard/Claude: vd-sprung.json (jede Minute, solange er online ist). /sprungfortschritt [Spieler] zeigt ihn privat.
// /sprungkoenig test 50k|100k (nur OP): Belohnung für sich selbst auslösen, ohne Merker – für Tests.
// Rhino: in Funktionen let statt const.
const VD_SPRUNG_PLAYER = 'prexynation'
const VD_SPRUNG_MILESTONE = 50000
const VD_SPRUNG_GOAL = 100000
const VD_SPRUNG_DONE = 'vd_sprung_done'   // Liste: '50k', '100k'
const VdSprungStats = Java.loadClass('net.minecraft.stats.Stats')

function vdSprungCount(p) {
  try { let n = Number(p.stats.jumps); if (!isNaN(n)) return n } catch (x) { }
  try { return Number(p.getStats().getValue(VdSprungStats.CUSTOM.get(VdSprungStats.JUMP))) } catch (x) { }
  return -1
}

function vdSprungPlayTicks(p) {
  try { let n = Number(p.stats.playTime); if (!isNaN(n)) return n } catch (x) { }
  try { return Number(p.getStats().getValue(VdSprungStats.CUSTOM.get(VdSprungStats.PLAY_TIME))) } catch (x) { }
  return 0
}

function vdSprungDone(server, key) {
  let done = server.persistentData.getList(VD_SPRUNG_DONE, 8)
  for (let i = 0; i < done.size(); i++) if (String(done.getString(i)) === key) return true
  return false
}

function vdSprungMark(server, key) {
  let pd = server.persistentData
  let done = pd.getList(VD_SPRUNG_DONE, 8)
  done.add(NBT.stringTag(key))
  pd.put(VD_SPRUNG_DONE, done)
}

function vdSprungFirework(server, name, delay) {
  server.scheduleInTicks(delay, () => {
    try {
      let dx = (Math.random() * 6 - 3).toFixed(1), dz = (Math.random() * 6 - 3).toFixed(1)
      server.runCommandSilent(`execute at ${name} run summon minecraft:firework_rocket ~${dx} ~1 ~${dz} ` +
        `{LifeTime:30,FireworksItem:{id:"minecraft:firework_rocket",Count:1b,tag:{Fireworks:{Flight:2b,Explosions:[` +
        `{Type:4b,Flicker:1b,Trail:1b,Colors:[I;16766720,6719955],FadeColors:[I;16777215]}]}}}}`)
    } catch (x) { }
  })
}

function vdSprungReward(server, p, key) {
  let name = String(p.username)
  let line = Text.of('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━').gold()
  if (key === '50k') {
    server.tell(line)
    server.tell(Text.of('  ').append(Text.of(name).gold().bold())
      .append(Text.of(' ist jetzt offiziell öfter gesprungen als ein Känguru in drei Wochen. ').yellow())
      .append(Text.of('50.000 Sprünge').gold().bold()).append(Text.of(' – weiter so!').yellow()))
    server.tell(line)
    p.tell(Text.of('[Sprungkönig] ').gold().append(Text.of('Meilenstein erreicht! Noch 50.000 bis zum Titel „Sprungkönig“.').gray()))
    server.runCommandSilent(`execute as @a at @s run playsound minecraft:entity.player.levelup master @s ~ ~ ~ 1 1.2`)
    for (let k = 0; k < 4; k++) vdSprungFirework(server, name, 10 + k * 12)
    server.scheduleInTicks(80, () => { try { vdCrateGive(p, 5, '50.000 Sprünge') } catch (x) { console.warn('[Sprungkönig] Kisten: ' + x) } })
  } else {
    server.tell(line)
    server.tell(Text.of('  100.000 Sprünge! ').gold().bold()
      .append(Text.of('Die Leertaste von ').yellow()).append(Text.of(name).gold().bold())
      .append(Text.of(' hat offiziell Rente beantragt.').yellow()))
    server.tell(Text.of('  ').append(Text.of(name).gold()).append(Text.of(' trägt ab jetzt den Titel ').gray())
      .append(Text.of('Sprungkönig').gold().bold()).append(Text.of('.').gray()))
    server.tell(line)
    server.runCommandSilent(`execute as @a at @s run playsound minecraft:ui.toast.challenge_complete master @s ~ ~ ~ 1 1`)
    for (let k = 0; k < 8; k++) vdSprungFirework(server, name, 10 + k * 12)
    server.runCommandSilent(`ftbranks add ${name} sprungkoenig`)
    server.scheduleInTicks(80, () => { try { vdCrateGive(p, 20, '100.000 Sprünge – Sprungkönig') } catch (x) { console.warn('[Sprungkönig] Kisten: ' + x) } })
  }
  console.info(`[Sprungkönig] ${name}: Belohnung ${key} vergeben`)
}

function vdSprungState(server, p, jumps) {
  let ticks = vdSprungPlayTicks(p)
  let hours = ticks / 72000
  return {
    player: String(p.username), jumps: jumps, play_hours: Math.round(hours * 10) / 10,
    per_hour: hours > 0 ? Math.round(jumps / hours) : null,
    milestone: VD_SPRUNG_MILESTONE, goal: VD_SPRUNG_GOAL,
    done_50k: vdSprungDone(server, '50k'), done_100k: vdSprungDone(server, '100k'), time: Date.now()
  }
}

let vdSprungLastWrite = 0
ServerEvents.tick(event => {
  let server = event.server
  if (server.tickCount % 100 !== 0) return
  let p = server.getPlayerList().getPlayerByName(VD_SPRUNG_PLAYER)
  if (!p) return
  let jumps = vdSprungCount(p)
  if (jumps < 0) return
  if (jumps >= VD_SPRUNG_MILESTONE && !vdSprungDone(server, '50k')) { vdSprungMark(server, '50k'); vdSprungReward(server, p, '50k') }
  if (jumps >= VD_SPRUNG_GOAL && !vdSprungDone(server, '100k')) { vdSprungMark(server, '100k'); vdSprungReward(server, p, '100k') }
  let now = Date.now()
  if (now - vdSprungLastWrite >= 60000) {
    vdSprungLastWrite = now
    try { JsonIO.write('vd-sprung.json', vdSprungState(server, p, jumps)) } catch (x) { }
  }
})

PlayerEvents.loggedOut(event => {
  if (String(event.player.username) !== VD_SPRUNG_PLAYER) return
  let j = vdSprungCount(event.player)
  if (j >= 0) try { JsonIO.write('vd-sprung.json', vdSprungState(event.server, event.player, j)) } catch (x) { }
})

function vdSprungBar(jumps) {
  let n = 20, full = Math.max(0, Math.min(n, Math.floor(jumps / VD_SPRUNG_GOAL * n)))
  let s = ''
  for (let i = 0; i < n; i++) s += (i === n / 2 ? '|' : '') + (i < full ? '█' : '░')
  return s
}

function vdSprungShow(ctx, who) {
  let src = ctx.source, server = src.server
  let name = who || VD_SPRUNG_PLAYER
  let p = server.getPlayerList().getPlayerByName(name)
  let st = null
  if (p) st = vdSprungState(server, p, vdSprungCount(p))
  else if (name.toLowerCase() === VD_SPRUNG_PLAYER.toLowerCase()) { try { st = JsonIO.read('vd-sprung.json') } catch (x) { } }
  if (!st || st.jumps == null || st.jumps < 0) { src.sendSystemMessage(Text.of(`Keine Sprungdaten für ${name}.`).red()); return 0 }
  let jumps = Number(st.jumps), pct = Math.min(100, jumps / VD_SPRUNG_GOAL * 100)
  let fmt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  src.sendSystemMessage(Text.of('[Sprungkönig] ').gold().append(Text.of(`${st.player}: `).yellow())
    .append(Text.of(`${fmt(jumps)} / ${fmt(VD_SPRUNG_GOAL)} Sprünge (${pct.toFixed(1).replace('.', ',')} %)`).white()))
  src.sendSystemMessage(Text.of('  ' + vdSprungBar(jumps)).gold().append(Text.of('  | = Meilenstein 50.000').darkGray()))
  let next = jumps < VD_SPRUNG_MILESTONE ? VD_SPRUNG_MILESTONE : VD_SPRUNG_GOAL
  if (jumps < VD_SPRUNG_GOAL) {
    let rest = next - jumps, eta = st.per_hour ? rest / st.per_hour : null
    src.sendSystemMessage(Text.of(`  Noch ${fmt(rest)} bis ${next === VD_SPRUNG_MILESTONE ? 'zum Meilenstein' : 'zum Sprungkönig'}`).gray()
      .append(Text.of(st.per_hour ? ` · ca. ${fmt(st.per_hour)} Sprünge pro Spielstunde · noch ~${fmt(Math.ceil(eta))} Std.` : '').darkGray()))
  } else src.sendSystemMessage(Text.of('  Sprungkönig erreicht!').gold().bold())
  if (!p) src.sendSystemMessage(Text.of(`  (Stand vom letzten Online-Zeitpunkt)`).darkGray())
  return 1
}

ServerEvents.commandRegistry(event => {
  const { commands: Commands, arguments: Arguments } = event
  event.register(Commands.literal('sprungfortschritt')
    .executes(ctx => vdSprungShow(ctx, null))
    .then(Commands.argument('spieler', Arguments.GREEDY_STRING.create(event))
      .executes(ctx => vdSprungShow(ctx, String(Arguments.GREEDY_STRING.getResult(ctx, 'spieler')).trim()))))
  event.register(Commands.literal('sprungkoenig').requires(s => s.hasPermission(2))
    .then(Commands.literal('test')
      .then(Commands.literal('50k').executes(ctx => { vdSprungReward(ctx.source.server, ctx.source.getPlayerOrException(), '50k'); return 1 }))
      .then(Commands.literal('100k').executes(ctx => { vdSprungReward(ctx.source.server, ctx.source.getPlayerOrException(), '100k'); return 1 }))))
})
