// priority: 0
// Xpetrified Orb (Forbidden & Arcanus): Schleichen + Rechtsklick löst den ganzen Stapel auf einmal ein (Stefans Wunsch).
// Die Mod gibt pro Klick nur einen Orb ab (91 XP, config/forbidden_arcanus-common.toml experience_points). Ohne Schleichen
// bleibt alles wie in der Mod.
const VD_ORB_XP = 91  // = [items.xpetrified_orb] experience_points – bei Config-Änderung hier mitziehen

ItemEvents.rightClicked('forbidden_arcanus:xpetrified_orb', event => {
  const p = event.player
  if (!p || !p.isShiftKeyDown()) return
  const stack = event.item
  const n = stack.count
  if (n <= 1) return  // ein einzelner Orb: Verhalten der Mod
  p.giveExperiencePoints(n * VD_ORB_XP)
  stack.count = 0
  p.level.playSound(null, p.x, p.y, p.z, 'minecraft:entity.player.levelup', 'players', 0.6, 1.0)
  event.cancel()
})
