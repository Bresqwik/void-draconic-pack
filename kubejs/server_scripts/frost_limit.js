// priority: 0
// Frost-Obergrenze für Spieler: PneumaticCraft-Frostmunition gibt pro Treffer +35 Frost-Ticks ohne Grenze (Stefan 15.10.:
// 738 nach einer Minigun-Salve, taute nicht mehr ab, Totem verbraucht). Spieler bleiben bei höchstens 140 Ticks – so viel wie
// voller Pulverschnee: Frostschaden und Verlangsamung wirken weiter, aber man taut normal ab. Mobs sind nicht betroffen.
const VD_FROST_MAX = 140

PlayerEvents.tick(e => {
  let p = e.player
  if (p.level.isClientSide() || p.age % 10 !== 0) return
  try {
    if (p.getTicksFrozen() > VD_FROST_MAX) p.setTicksFrozen(VD_FROST_MAX)
  } catch (x) { }
})
